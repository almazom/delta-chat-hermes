# TC-009: Extract chat token functions to chat_tokens.py

**Epic:** 03 — Module Refactor
**Story Points:** 2
**Priority:** P1
**Status:** TODO
**Dependencies:** TC-003

## User Story

As a maintainer, I want chat token logic isolated in its own module, so that `adapter.py` stays focused on the platform interface.

## Story Points:** 2

## Description

Move `_get_or_create_chat_token` and `_resolve_chat_token` (and the destructive-methods set if only used for safe RPC) into a new `chat_tokens.py` module.

## Prerequisites

- [ ] TC-003 complete

## Implementation Steps

### Step 1: Create `chat_tokens.py`

**File:** `chat_tokens.py`

```python
import secrets
import logging
from typing import Optional

logger = logging.getLogger("hermes_plugins.deltachat.tokens")

DESTRUCTIVE_METHODS = frozenset({
    "delete_chat",
    "delete_messages",
    "delete_messages_for_all",
    "remove_contact_from_chat",
    "remove_draft",
    "leave_group",
})

async def get_or_create_chat_token(state, rpc, account_id: int, chat_id: int) -> str:
    if chat_id in state.chat_id_to_token:
        return state.chat_id_to_token[chat_id]
    dc_key = f"ui.hermes.chat_token.{chat_id}"
    try:
        existing = await rpc.get_config(account_id, dc_key)
    except Exception:
        existing = None
    if existing:
        token = existing
    else:
        token = secrets.token_hex(8)
        try:
            await rpc.set_config(account_id, dc_key, token)
            await rpc.set_config(account_id, f"ui.hermes.token_chat.{token}", str(chat_id))
        except Exception as e:
            logger.warning(f"Could not persist chat token to DC config: {e}")
    state.chat_id_to_token[chat_id] = token
    state.chat_token_to_id[token] = chat_id
    return token

async def resolve_chat_token(state, rpc, account_id: int, token: str) -> Optional[int]:
    if token in state.chat_token_to_id:
        return state.chat_token_to_id[token]
    dc_key = f"ui.hermes.token_chat.{token}"
    try:
        chat_id_str = await rpc.get_config(account_id, dc_key)
    except Exception:
        chat_id_str = None
    if chat_id_str:
        chat_id = int(chat_id_str)
        state.chat_token_to_id[token] = chat_id
        state.chat_id_to_token[chat_id] = token
        return chat_id
    return None
```

### Step 2: Update `adapter.py` imports

**File:** `adapter.py`

```python
from chat_tokens import get_or_create_chat_token, resolve_chat_token, DESTRUCTIVE_METHODS
```

### Step 3: Remove old helpers and `_DESTRUCTIVE_METHODS`

**File:** `adapter.py:153-161`, `adapter.py:167-218`

Delete the old definitions.

### Step 4: Update callers

**File:** `adapter.py`

Replace `_get_or_create_chat_token(...)` with `get_or_create_chat_token(self.state, ...)` and `_resolve_chat_token(...)` with `resolve_chat_token(self.state, ...)`.

### Step 5: Verify

```bash
python3 -m py_compile adapter.py chat_tokens.py
```

**Expected:** No syntax errors.

## Acceptance Criteria

- [ ] `chat_tokens.py` exists and exports `get_or_create_chat_token`, `resolve_chat_token`, `DESTRUCTIVE_METHODS`.
- [ ] `adapter.py` no longer defines these helpers.
- [ ] Behavior is unchanged.

## Definition of Done

- Chat token logic lives in its own module.

## Dependencies
TC-003

## What this is NOT
- It does not change the token persistence format.
- It does not move the RPC tools yet (TC-010).

## Workflow lane evidence
- Review: inspect `chat_tokens.py` and grep for old helper names in `adapter.py`.
- Acceptance: `python3 -m py_compile adapter.py chat_tokens.py` passes.
- Commit: `git add -A && git commit -m "TC-009: extract chat token logic to chat_tokens.py"`
