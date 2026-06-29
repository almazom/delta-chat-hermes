# TC-003: Replace global token maps with per-adapter token store

**Epic:** 01 — State & Boundaries
**Story Points:** 2
**Priority:** P0
**Status:** TODO
**Dependencies:** TC-001

## User Story

As a multi-profile Hermes user, I want opaque chat tokens to be scoped per adapter, so that a token from one profile cannot be resolved against another profile's chats.

## Story Points: 2

## Description

`adapter.py:150-151` stores `_chat_id_to_token` and `_chat_token_to_id` at module scope. This ticket moves them into `DeltaChatPluginState` and updates `_get_or_create_chat_token` / `_resolve_chat_token` to accept the state object.

## Prerequisites

- [ ] TC-001 complete

## Implementation Steps

### Step 1: Move token maps into state

**File:** `adapter.py`

Already added in TC-001; ensure `DeltaChatPluginState` has:
```python
chat_id_to_token: Dict[int, str] = field(default_factory=dict)
chat_token_to_id: Dict[str, int] = field(default_factory=dict)
```

### Step 2: Refactor token helpers to take state

**File:** `adapter.py:167-218`

Change signatures:
```python
async def _get_or_create_chat_token(state, rpc, account_id: int, chat_id: int) -> str:
    if chat_id in state.chat_id_to_token:
        return state.chat_id_to_token[chat_id]
    ...
    state.chat_id_to_token[chat_id] = token
    state.chat_token_to_id[token] = chat_id
    return token

async def _resolve_chat_token(state, rpc, account_id: int, token: str) -> Optional[int]:
    if token in state.chat_token_to_id:
        return state.chat_token_to_id[token]
    ...
    state.chat_token_to_id[token] = chat_id
    state.chat_id_to_token[chat_id] = token
    return chat_id
```

### Step 3: Update callers

**File:** `adapter.py:1081`, `adapter.py:1200`, `adapter.py:1674`, `adapter.py:1737`

Pass `self.state` (or the relevant state object) to the helpers.

### Step 4: Remove module-level token maps

**File:** `adapter.py:150-151`

Delete the global declarations.

### Step 5: Verify

```bash
python3 -m py_compile adapter.py
```

**Expected:** No syntax errors.

## Acceptance Criteria

- [ ] No module-level token maps remain.
- [ ] Token helpers are pure-ish (state passed explicitly).
- [ ] Callers pass the adapter's state.

## Definition of Done

- Chat token mapping is scoped per adapter instance.

## Dependencies
TC-001

## What this is NOT
- It does not change the persistence mechanism (still DC config `ui.hermes.chat_token.*`).
- It does not encrypt tokens at rest.

## Workflow lane evidence
- Review: grep confirms `_chat_id_to_token` and `_chat_token_to_id` globals are gone.
- Acceptance: `python3 -m py_compile adapter.py` passes.
- Commit: `git add -A && git commit -m "TC-003: scope chat token maps to adapter state"`
