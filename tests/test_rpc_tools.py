"""Tests for Delta Chat RPC tool registration and safe-call guards."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock


def _fake_adapter():
    """Build a minimal fake adapter for rpc_tools tests."""
    from chat_tokens import ChatTokenStore

    adapter = MagicMock()
    adapter.account_id = 1
    adapter.state = MagicMock()
    adapter.state.chat_tokens = ChatTokenStore()
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


@pytest.fixture
def registry():
    """Token-to-adapter mapping used by multi-profile dispatch tests."""
    return {}


def _register(fake_ctx, fake_adapter, registry):
    """Register tools using the new dispatch signature."""
    import rpc_tools

    rpc_tools.register_rpc_tools(
        fake_ctx,
        resolve_adapter=lambda token: registry.get(token),
        get_default_adapter=lambda: fake_adapter,
    )


@pytest.mark.asyncio
async def test_register_rpc_tools_default_set(fake_ctx, fake_adapter, registry):
    """Default registration includes spec and safe-call tools."""
    _register(fake_ctx, fake_adapter, registry)

    assert "dc_rpc_spec" in fake_ctx.tools
    assert "dc_chat_rpc_spec" in fake_ctx.tools
    assert "dc_safe_rpc_call" in fake_ctx.tools
    assert "dc_start_call" in fake_ctx.tools
    assert "dc_end_call" in fake_ctx.tools
    # Raw RPC tool is absent without the env var.
    assert "dc_rpc_call" not in fake_ctx.tools


@pytest.mark.asyncio
async def test_dc_safe_rpc_call_blocks_mutating_method(fake_ctx, fake_adapter, registry):
    """Methods not in the read-only allowlist are rejected."""
    registry["token123"] = fake_adapter
    _register(fake_ctx, fake_adapter, registry)
    handler = fake_ctx.tools["dc_safe_rpc_call"]["handler"]

    result = await handler({"method": "send_msg", "chat_token": "token123", "params": []})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "not allowed" in parsed["error"]


@pytest.mark.asyncio
async def test_dc_safe_rpc_call_blocks_destructive_method(fake_ctx, fake_adapter, registry):
    """Destructive methods are rejected even if they accept chatId."""
    registry["token123"] = fake_adapter
    _register(fake_ctx, fake_adapter, registry)
    handler = fake_ctx.tools["dc_safe_rpc_call"]["handler"]

    result = await handler({"method": "delete_chat", "chat_token": "token123", "params": []})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "not allowed" in parsed["error"]


@pytest.mark.asyncio
async def test_dc_safe_rpc_call_unknown_token(fake_ctx, fake_adapter, registry):
    """An unknown chat_token returns a clear error."""
    _register(fake_ctx, fake_adapter, registry)
    handler = fake_ctx.tools["dc_safe_rpc_call"]["handler"]

    fake_adapter.rpc.get_config.return_value = None
    result = await handler({"method": "get_basic_chat_info", "chat_token": "nope", "params": []})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "Unknown chat_token" in parsed["error"]
    fake_adapter.rpc.get_config.return_value = None  # reset for other tests


@pytest.mark.asyncio
async def test_dc_safe_rpc_call_injects_account_and_chat(fake_ctx, fake_adapter, registry, monkeypatch):
    """Allowed method receives account_id and resolved chat_id automatically."""
    registry["token123"] = fake_adapter
    _register(fake_ctx, fake_adapter, registry)
    handler = fake_ctx.tools["dc_safe_rpc_call"]["handler"]

    fake_adapter.state.chat_tokens.chat_token_to_id["token123"] = 42
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
async def test_dc_chat_rpc_spec_only_lists_allowed_methods(fake_ctx, fake_adapter, registry):
    """dc_chat_rpc_spec returns only SAFE_CHAT_METHODS with a chatId param."""
    _register(fake_ctx, fake_adapter, registry)
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


@pytest.mark.asyncio
async def test_dc_end_call_unknown_token(fake_ctx, fake_adapter, registry):
    """Ending a call with an unknown token fails cleanly."""
    _register(fake_ctx, fake_adapter, registry)
    handler = fake_ctx.tools["dc_end_call"]["handler"]

    fake_adapter._call_manager = MagicMock()
    result = await handler({"chat_token": "nope"})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "Unknown chat_token" in parsed["error"]


@pytest.mark.asyncio
async def test_dc_end_call_rejects_inactive_chat(fake_ctx, fake_adapter, registry):
    """Ending a call for a chat with no active call returns a clear error."""
    registry["token123"] = fake_adapter
    _register(fake_ctx, fake_adapter, registry)
    handler = fake_ctx.tools["dc_end_call"]["handler"]

    fake_adapter.state.chat_tokens.chat_token_to_id["token123"] = 42
    fake_adapter._call_manager = MagicMock()
    fake_adapter._call_manager.active_chat_ids.return_value = ["99"]

    result = await handler({"chat_token": "token123"})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "No active call for this chat" in parsed["error"]


@pytest.mark.asyncio
async def test_dc_end_call_success(fake_ctx, fake_adapter, registry):
    """Ending a call for an active chat requests hangup."""
    registry["token123"] = fake_adapter
    _register(fake_ctx, fake_adapter, registry)
    handler = fake_ctx.tools["dc_end_call"]["handler"]

    fake_adapter.state.chat_tokens.chat_token_to_id["token123"] = 42
    fake_adapter._call_manager = MagicMock()
    fake_adapter._call_manager.active_chat_ids.return_value = ["42"]
    fake_adapter._call_manager.request_hangup = AsyncMock(return_value=True)

    result = await handler({"chat_token": "token123"})
    parsed = json.loads(result)
    assert parsed.get("success") is True
    fake_adapter._call_manager.request_hangup.assert_awaited_once_with("42")


@pytest.mark.asyncio
async def test_dc_start_call_requires_opening(fake_ctx, fake_adapter, registry):
    """Starting a call without an opening line is rejected."""
    registry["token123"] = fake_adapter
    _register(fake_ctx, fake_adapter, registry)
    handler = fake_ctx.tools["dc_start_call"]["handler"]

    fake_adapter._call_manager = MagicMock()
    result = await handler({"chat_token": "token123"})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "opening" in parsed["error"]


@pytest.mark.asyncio
async def test_dc_start_call_success(fake_ctx, fake_adapter, registry):
    """Starting a call resolves the token and delegates to the call manager."""
    registry["token123"] = fake_adapter
    _register(fake_ctx, fake_adapter, registry)
    handler = fake_ctx.tools["dc_start_call"]["handler"]

    fake_adapter.state.chat_tokens.chat_token_to_id["token123"] = 7
    fake_adapter._call_manager = MagicMock()
    fake_adapter._call_manager.start_call = AsyncMock(return_value=123)

    result = await handler({"chat_token": "token123", "opening": "Hello!"})
    parsed = json.loads(result)
    assert parsed.get("success") is True
    assert parsed.get("msg_id") == 123
    fake_adapter._call_manager.start_call.assert_awaited_once_with("7", opening="Hello!")


@pytest.mark.asyncio
async def test_dc_start_call_timeout(fake_ctx, fake_adapter, registry):
    """An unanswered call surfaces a timeout error."""
    import asyncio

    registry["token123"] = fake_adapter
    _register(fake_ctx, fake_adapter, registry)
    handler = fake_ctx.tools["dc_start_call"]["handler"]

    fake_adapter.state.chat_tokens.chat_token_to_id["token123"] = 7
    fake_adapter._call_manager = MagicMock()
    fake_adapter._call_manager.start_call = AsyncMock(side_effect=asyncio.TimeoutError)

    result = await handler({"chat_token": "token123", "opening": "Hi"})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "not answered" in parsed["error"]


@pytest.mark.asyncio
async def test_dc_safe_rpc_call_dispatches_by_chat_token(fake_ctx, fake_adapter, registry):
    """The same global tool routes calls to different adapters based on token."""
    adapter_a = fake_adapter
    adapter_b = _fake_adapter()
    adapter_b.account_id = 2
    adapter_b.state.chat_tokens.chat_token_to_id["token-b"] = 99
    adapter_b.rpc.get_basic_chat_info = AsyncMock(return_value={"id": 99, "name": "Other"})
    adapter_b.state.spec_cache = {
        "methods": [
            {
                "name": "get_basic_chat_info",
                "params": [{"name": "accountId"}, {"name": "chatId"}],
            },
        ]
    }

    adapter_a.state.chat_tokens.chat_token_to_id["token-a"] = 42
    adapter_a.rpc.get_basic_chat_info = AsyncMock(return_value={"id": 42, "name": "Test"})
    adapter_a.state.spec_cache = adapter_b.state.spec_cache

    registry["token-a"] = adapter_a
    registry["token-b"] = adapter_b
    _register(fake_ctx, adapter_a, registry)
    handler = fake_ctx.tools["dc_safe_rpc_call"]["handler"]

    await handler({"method": "get_basic_chat_info", "chat_token": "token-b", "params": []})
    adapter_b.rpc.get_basic_chat_info.assert_awaited_once_with(2, 99)
    adapter_a.rpc.get_basic_chat_info.assert_not_awaited()
