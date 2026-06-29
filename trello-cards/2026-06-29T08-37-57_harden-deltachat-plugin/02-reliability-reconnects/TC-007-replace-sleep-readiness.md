# TC-007: Replace sleep-based readiness with polling loop

**Epic:** 02 — Reliability & Reconnects
**Story Points:** 2
**Priority:** P1
**Status:** TODO
**Dependencies:** TC-006

## User Story

As a Hermes operator, I want the adapter to detect RPC server readiness quickly and reliably, so that startup does not waste a fixed second or fail when the server is slow.

## Story Points:** 2

## Description

`adapter.py:335` uses `await asyncio.sleep(1)` to wait for the RPC server. `setup.py:357-367` does similar with 1-second sleeps up to 10 attempts. This ticket replaces both with event-driven polling via `DeltaChatRpcClient._wait_ready()`.

## Prerequisites

- [ ] TC-006 complete

## Implementation Steps

### Step 1: Use the polling helper in adapter

**File:** `adapter.py`

Already done if TC-006 implemented `DeltaChatRpcClient.start()` using `_wait_ready()`. Ensure `connect()` waits for the client to be ready.

### Step 2: Refactor `setup.py` readiness loop

**File:** `setup.py:356-367`

Replace the fixed-sleep loop:
```python
async def wait_for_rpc(rpc, timeout: float = 10.0) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            rpc.get_all_accounts()
            return True
        except Exception:
            await asyncio.sleep(0.5)
    return False
```

Then call `await wait_for_rpc(rpc)` instead of the manual loop.

### Step 3: Verify

```bash
python3 -m py_compile adapter.py setup.py
```

**Expected:** No syntax errors.

## Acceptance Criteria

- [ ] No fixed `sleep(1)` calls remain for RPC readiness in adapter or setup.
- [ ] Readiness is polled with a short backoff up to a timeout.

## Definition of Done

- RPC readiness detection is responsive and bounded.

## Dependencies
TC-006

## What this is NOT
- It does not add health monitoring after startup (TC-008).
- It does not change the RPC transport type.

## Workflow lane evidence
- Review: grep for `sleep(1)` in adapter/setup.
- Acceptance: `python3 -m py_compile adapter.py setup.py` passes.
- Commit: `git add -A && git commit -m "TC-007: poll RPC readiness instead of fixed sleep"`
