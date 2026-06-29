# TC-004: Move OpenRPC spec cache into state object

**Epic:** 01 — State & Boundaries
**Story Points:** 1
**Priority:** P1
**Status:** TODO
**Dependencies:** TC-001

## User Story

As a Hermes operator, I want the Delta Chat OpenRPC spec cache to be scoped per adapter, so that different profiles with different RPC server versions do not share a stale spec.

## Story Points: 1

## Description

`adapter.py:164` stores `_spec_cache` at module scope. This ticket moves it into `DeltaChatPluginState` and updates `_fetch_spec` to use the adapter's state.

## Prerequisites

- [ ] TC-001 complete

## Implementation Steps

### Step 1: Update `_fetch_spec`

**File:** `adapter.py:221-239`

Change signature to accept state:
```python
async def _fetch_spec(state) -> dict:
    if state.spec_cache is None:
        rpc_server = ...
        ...
        state.spec_cache = json.loads(stdout.decode())
    return state.spec_cache
```

### Step 2: Update callers

**File:** `adapter.py:1630`, `adapter.py:1648`, `adapter.py:1688`

Pass `state` to `_fetch_spec`.

### Step 3: Remove module-level `_spec_cache`

**File:** `adapter.py:164`

Delete the global declaration.

### Step 4: Verify

```bash
python3 -m py_compile adapter.py
```

**Expected:** No syntax errors.

## Acceptance Criteria

- [ ] No module-level `_spec_cache` remains.
- [ ] `_fetch_spec` uses per-adapter state.
- [ ] Callers pass state.

## Definition of Done

- Each adapter caches its own OpenRPC spec independently.

## Dependencies
TC-001

## What this is NOT
- It does not add cache invalidation when the RPC server restarts.
- It does not persist the spec to disk.

## Workflow lane evidence
- Review: grep confirms `_spec_cache` global is gone.
- Acceptance: `python3 -m py_compile adapter.py` passes.
- Commit: `git add -A && git commit -m "TC-004: scope OpenRPC spec cache per adapter"`
