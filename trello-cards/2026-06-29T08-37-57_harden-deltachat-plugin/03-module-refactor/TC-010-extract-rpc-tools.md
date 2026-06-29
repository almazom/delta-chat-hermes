# TC-010: Extract RPC tools to rpc_tools.py

**Epic:** 03 — Module Refactor
**Story Points:** 3
**Priority:** P1
**Status:** TODO
**Dependencies:** TC-002, TC-009

## User Story

As a maintainer, I want the `dc_*` tool registration and handlers in a separate module, so that `adapter.py` only contains the platform adapter interface.

## Story Points:** 3

## Description

Move `register_rpc_tools` and all tool handler functions (`_spec_handler`, `_call_handler`, `_chat_spec_handler`, `_safe_call_handler`, etc.) from `adapter.py:1617-1928` to a new `rpc_tools.py`.

## Prerequisites

- [ ] TC-002 complete
- [ ] TC-009 complete

## Implementation Steps

### Step 1: Create `rpc_tools.py`

**File:** `rpc_tools.py`

- Import `json`, `os`, `asyncio`, `logging`, `typing.Any`.
- Import `DESTRUCTIVE_METHODS`, `resolve_chat_token` from `chat_tokens`.
- Import `_fetch_spec` (or create a lightweight version that uses adapter state).
- Move all `register_rpc_tools` code here.
- Signature: `def register_rpc_tools(ctx, adapter) -> None:`.
- Close over `adapter` and `adapter.state` in handlers.

### Step 2: Remove `register_rpc_tools` from `adapter.py`

**File:** `adapter.py:1617-1928`

Delete the function.

### Step 3: Update `__init__.py`

**File:** `__init__.py`

```python
from .adapter import DeltaChatAdapter, register_platform
from .rpc_tools import register_rpc_tools


def register(ctx):
    register_platform(ctx)
    # NOTE: register_rpc_tools is called by the gateway for each adapter instance.
```

If the gateway calls `register_rpc_tools(ctx)` without an adapter argument, add a thin shim:
```python
_adapter_for_tools = None

def register(ctx):
    register_platform(ctx)
    # The gateway calls this once; actual tool handlers are bound per adapter.
```

But prefer passing the adapter instance explicitly (update gateway contract if needed).

### Step 4: Verify

```bash
python3 -m py_compile adapter.py rpc_tools.py __init__.py
```

**Expected:** No syntax errors.

## Acceptance Criteria

- [ ] `rpc_tools.py` exists and exports `register_rpc_tools`.
- [ ] `adapter.py` no longer contains tool handlers.
- [ ] Tool handlers close over the correct adapter instance.

## Definition of Done

- RPC tool registration is isolated from the adapter class.

## Dependencies
TC-002, TC-009

## What this is NOT
- It does not redesign the tool schema; schemas remain identical.
- It does not move media handling (TC-011).

## Workflow lane evidence
- Review: inspect `rpc_tools.py` and grep for `register_rpc_tools` in `adapter.py`.
- Acceptance: `python3 -m py_compile adapter.py rpc_tools.py __init__.py` passes.
- Commit: `git add -A && git commit -m "TC-010: extract RPC tools to rpc_tools.py"`
