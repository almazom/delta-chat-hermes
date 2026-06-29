# TC-008: Add event-loop health monitor and reconnect logic

**Epic:** 02 — Reliability & Reconnects
**Story Points:** 4
**Priority:** P0
**Status:** TODO
**Dependencies:** TC-007

## User Story

As a Hermes operator, I want the Delta Chat adapter to detect when the RPC server or event loop dies and reconnect automatically, so that a transient crash does not require a manual gateway restart.

## Story Points:** 4

## Description

`adapter.py:955-967` logs event-loop errors and sleeps, but never attempts recovery. This ticket adds a lightweight health monitor that triggers reconnect with exponential backoff.

## Prerequisites

- [ ] TC-007 complete

## Implementation Steps

### Step 1: Add health check inside `_event_listener`

**File:** `adapter.py:955-967`

Detect transport/RPC death:
```python
async def _event_listener(self) -> None:
    consecutive_errors = 0
    while self._running:
        try:
            if not self._rpc_client or not self._rpc_client.is_alive():
                raise RuntimeError("RPC client is not alive")
            if self.account_id:
                envelope = await self.rpc.get_next_event()
                if envelope.get("context_id") == self.account_id:
                    await self._handle_dc_event(envelope.get("event", {}))
            consecutive_errors = 0
        except asyncio.CancelledError:
            break
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Event listener error ({consecutive_errors}): {e}")
            if consecutive_errors >= 3:
                logger.warning("Triggering reconnect due to repeated event-loop errors")
                asyncio.create_task(self._reconnect())
                break
            await asyncio.sleep(1)
```

### Step 2: Implement `_reconnect`

**File:** `adapter.py`

```python
async def _reconnect(self) -> bool:
    logger.info("Delta Chat reconnecting...")
    try:
        await self.disconnect()
    except Exception as e:
        logger.debug(f"Disconnect during reconnect failed (non-fatal): {e}")
    for attempt in range(1, 6):
        logger.info(f"Reconnect attempt {attempt}/5")
        if await self.connect():
            logger.info("Delta Chat reconnected successfully")
            return True
        wait = min(2 ** attempt, 30)
        logger.info(f"Reconnect attempt {attempt} failed; waiting {wait}s")
        await asyncio.sleep(wait)
    logger.error("Delta Chat reconnect failed after 5 attempts")
    self._mark_disconnected()
    return False
```

### Step 3: Prevent concurrent reconnects

Add `self._reconnecting: bool = False` in `__init__` and guard `_reconnect()`.

### Step 4: Verify

```bash
python3 -m py_compile adapter.py
```

**Expected:** No syntax errors.

## Acceptance Criteria

- [ ] `_event_listener` detects repeated failures and triggers reconnect.
- [ ] `_reconnect` uses exponential backoff up to 5 attempts.
- [ ] Concurrent reconnect attempts are prevented.

## Definition of Done

- The adapter can recover from transient RPC transport failures without manual intervention.

## Dependencies
TC-007

## What this is NOT
- It does not monitor the `deltachat-rpc-server` OS process directly.
- It does not persist undelivered messages across reconnects.

## Workflow lane evidence
- Review: inspect `_event_listener` and `_reconnect`.
- Acceptance: `python3 -m py_compile adapter.py` passes.
- Commit: `git add -A && git commit -m "TC-008: add RPC reconnect with exponential backoff"`
