"""Tests for Delta Chat RPC tool registration and safe-call guards."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock


def _fake_adapter():
    """Build a minimal fake adapter for rpc_tools tests."""
    adapter = MagicMock()
    adapter.account_id = 1
    adapter.state = MagicMock()
    adapter.state.chat_tokens = MagicMock()
    adapter.state.spec_cache = None
    adapter.rpc = MagicMock()
    adapter.rpc.get_config = AsyncMock(return_value=None)
    adapter.rpc.set_config = AsyncMock()
    adapter._get_rpc_server_path.return_value = "deltachat-rpc-server"
    adapter._call_manager = None
    return adapter


class FakeCtx:
    """Capture tool registrations."""

    def __init__(self):
        self.tools = {}

    def register_tool(self, name, toolset, schema, handler, is_async=False, emoji=None):
        self.tools[name] = {
            "toolset": toolset,
            "schema": schema,
            "handler": handler,
            "is_async": is_async,
            "emoji": emoji,
        }


@pytest.fixture
def fake_adapter():
    return _fake_adapter()


@pytest.fixture
def fake_ctx():
    return FakeCtx()


@pytest.mark.asyncio
async def test_register_rpc_tools_default_set(fake_ctx, fake_adapter):
    """Default registration includes spec and safe-call tools."""
    import rpc_tools

    rpc_tools.register_rpc_tools(fake_ctx, fake_adapter)

    assert "dc_rpc_spec" in fake_ctx.tools
    assert "dc_chat_rpc_spec" in fake_ctx.tools
    assert "dc_safe_rpc_call" in fake_ctx.tools
    assert "dc_start_call" in fake_ctx.tools
    assert "dc_end_call" in fake_ctx.tools
    # Raw RPC tool is absent without the env var.
    assert "dc_rpc_call" not in fake_ctx.tools


@pytest.mark.asyncio
async def test_dc_safe_rpc_call_blocks_mutating_method(fake_ctx, fake_adapter):
    """Methods not in the read-only allowlist are rejected."""
    import rpc_tools

    rpc_tools.register_rpc_tools(fake_ctx, fake_adapter)
    handler = fake_ctx.tools["dc_safe_rpc_call"]["handler"]

    result = await handler({"method": "send_msg", "chat_token": "token123", "params": []})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "not allowed" in parsed["error"]


@pytest.mark.asyncio
async def test_dc_safe_rpc_call_blocks_destructive_method(fake_ctx, fake_adapter):
    """Destructive methods are rejected even if they accept chatId."""
    import rpc_tools

    rpc_tools.register_rpc_tools(fake_ctx, fake_adapter)
    handler = fake_ctx.tools["dc_safe_rpc_call"]["handler"]

    result = await handler({"method": "delete_chat", "chat_token": "token123", "params": []})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "not allowed" in parsed["error"]


@pytest.mark.asyncio
async def test_dc_safe_rpc_call_unknown_token(fake_ctx, fake_adapter):
    """An unknown chat_token returns a clear error."""
    import rpc_tools

    rpc_tools.register_rpc_tools(fake_ctx, fake_adapter)
    handler = fake_ctx.tools["dc_safe_rpc_call"]["handler"]

    fake_adapter.rpc.get_config.return_value = None
    result = await handler({"method": "get_basic_chat_info", "chat_token": "nope", "params": []})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "Unknown chat_token" in parsed["error"]
    fake_adapter.rpc.get_config.return_value = None  # reset for other tests


@pytest.mark.asyncio
async def test_dc_safe_rpc_call_injects_account_and_chat(fake_ctx, fake_adapter, monkeypatch):
    """Allowed method receives account_id and resolved chat_id automatically."""
    import rpc_tools

    rpc_tools.register_rpc_tools(fake_ctx, fake_adapter)
    handler = fake_ctx.tools["dc_safe_rpc_call"]["handler"]

    fake_adapter.rpc.get_config.return_value = "42"
    fake_adapter.rpc.get_basic_chat_info = AsyncMock(return_value={"id": 42, "name": "Test"})
    fake_adapter.state.spec_cache = {
        "methods": [
            {
                "name": "get_basic_chat_info",
                "params": [{"name": "accountId"}, {"name": "chatId"}],
            },
        ]
    }

    result = await handler({"method": "get_basic_chat_info", "chat_token": "token123", "params": []})
    parsed = json.loads(result)
    assert "error" not in parsed
    fake_adapter.rpc.get_basic_chat_info.assert_awaited_once_with(1, 42)


@pytest.mark.asyncio
async def test_dc_chat_rpc_spec_only_lists_allowed_methods(fake_ctx, fake_adapter):
    """dc_chat_rpc_spec returns only SAFE_CHAT_METHODS with a chatId param."""
    import rpc_tools

    rpc_tools.register_rpc_tools(fake_ctx, fake_adapter)
    handler = fake_ctx.tools["dc_chat_rpc_spec"]["handler"]

    # Minimal fake spec containing one allowed and one disallowed chat-scoped method.
    fake_spec = {
        "methods": [
            {
                "name": "get_basic_chat_info",
                "params": [{"name": "accountId"}, {"name": "chatId"}],
            },
            {"name": "send_msg", "params": [{"name": "accountId"}, {"name": "chatId"}]},
        ]
    }
    fake_adapter.state.spec_cache = fake_spec

    result = await handler()
    parsed = json.loads(result)
    names = [m["name"] for m in parsed["methods"]]
    assert "get_basic_chat_info" in names
    assert "send_msg" not in names
