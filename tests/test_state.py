"""Tests for per-adapter state isolation and chat token mapping."""

import pytest
from adapter import DeltaChatPluginState


def test_state_is_independent():
    s1 = DeltaChatPluginState()
    s2 = DeltaChatPluginState()
    s1.chat_tokens.chat_id_to_token[1] = "abc"
    assert "abc" not in s2.chat_tokens.chat_id_to_token.values()


def test_state_defaults_are_isolated():
    s1 = DeltaChatPluginState()
    s2 = DeltaChatPluginState()
    s1.chat_tokens.chat_token_to_id["x"] = 99
    assert "x" not in s2.chat_tokens.chat_token_to_id


@pytest.mark.asyncio
async def test_token_round_trip():
    from chat_tokens import get_or_create_chat_token, resolve_chat_token

    class FakeRpc:
        def __init__(self):
            self.config = {}

        async def get_config(self, account_id, key):
            return self.config.get(key)

        async def set_config(self, account_id, key, value):
            self.config[key] = value

    state = DeltaChatPluginState()
    rpc = FakeRpc()
    token = await get_or_create_chat_token(state.chat_tokens, rpc, account_id=1, chat_id=42)
    assert isinstance(token, str)
    assert state.chat_tokens.chat_id_to_token[42] == token
    resolved = await resolve_chat_token(state.chat_tokens, rpc, account_id=1, token=token)
    assert resolved == 42


@pytest.mark.asyncio
async def test_token_persists_via_dc_config():
    from chat_tokens import get_or_create_chat_token, resolve_chat_token

    class FakeRpc:
        def __init__(self):
            self.config = {}

        async def get_config(self, account_id, key):
            return self.config.get(key)

        async def set_config(self, account_id, key, value):
            self.config[key] = value

    state1 = DeltaChatPluginState()
    state2 = DeltaChatPluginState()
    rpc = FakeRpc()
    token = await get_or_create_chat_token(state1.chat_tokens, rpc, account_id=1, chat_id=42)
    # Simulate a new process/session: state2 should resolve the same token from DC config
    resolved = await resolve_chat_token(state2.chat_tokens, rpc, account_id=1, token=token)
    assert resolved == 42
