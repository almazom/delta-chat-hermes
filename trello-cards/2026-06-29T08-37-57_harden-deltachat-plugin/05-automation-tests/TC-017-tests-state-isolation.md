# TC-017: Add tests for state isolation and token round-trip

**Epic:** 05 — Automation & Tests
**Story Points:** 2
**Priority:** P1
**Status:** TODO
**Dependencies:** TC-001, TC-003

## User Story

As a developer, I want tests proving that per-adapter state isolation works, so that regressions in multi-profile support are caught automatically.

## Story Points:** 2

## Description

Add unit tests for `DeltaChatPluginState`, token creation/resolution, and adapter separation.

## Prerequisites

- [ ] TC-001 complete
- [ ] TC-003 complete

## Implementation Steps

### Step 1: Create `tests/test_state.py`

**File:** `tests/test_state.py`

```python
import pytest
from adapter import DeltaChatPluginState


def test_state_is_independent():
    s1 = DeltaChatPluginState()
    s2 = DeltaChatPluginState()
    s1.chat_id_to_token[1] = "abc"
    assert "abc" not in s2.chat_id_to_token.values()


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
    token = await get_or_create_chat_token(state, rpc, account_id=1, chat_id=42)
    assert isinstance(token, str)
    assert state.chat_id_to_token[42] == token
    resolved = await resolve_chat_token(state, rpc, account_id=1, token=token)
    assert resolved == 42
```

### Step 2: Add adapter isolation test

```python
def test_two_adapters_do_not_share_state():
    # Requires DeltaChatAdapter to be importable without heavy deps.
    # Mock BasePlatformAdapter if needed.
    pass
```

### Step 3: Run tests

```bash
pytest tests/test_state.py -q
```

**Expected:** Tests pass.

## Acceptance Criteria

- [ ] `tests/test_state.py` exists and passes.
- [ ] Token round-trip is tested.
- [ ] State independence is tested.

## Definition of Done

- Core state logic has automated coverage.

## Dependencies
TC-001, TC-003

## What this is NOT
- It does not test the full gateway with real Delta Chat.
- It does not test voice calls.

## Workflow lane evidence
- Review: inspect `tests/test_state.py`.
- Acceptance: `pytest tests/test_state.py -q` passes.
- Commit: `git add -A && git commit -m "TC-017: add state isolation and token tests"`
