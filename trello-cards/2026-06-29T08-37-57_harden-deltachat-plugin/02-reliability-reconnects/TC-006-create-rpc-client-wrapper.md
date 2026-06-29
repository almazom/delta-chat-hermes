# TC-006: Create DeltaChatRpcClient wrapper for transport lifecycle

**Epic:** 02 — Reliability & Reconnects
**Story Points:** 3
**Priority:** P0
**Status:** TODO
**Dependencies:** TC-005

## User Story

As a Hermes operator, I want the RPC transport lifecycle wrapped in a small client, so that the adapter can detect failures and restart the transport without duplicating logic across `connect()` and reconnect paths.

## Story Points: 3

## Description

`adapter.py:298-388` inlines RPC server startup, transport creation, and readiness. This ticket extracts a `DeltaChatRpcClient` class that owns the transport and the wrapped async RPC.

## Prerequisites

- [ ] TC-005 complete

## Implementation Steps

### Step 1: Create `DeltaChatRpcClient`

**File:** `adapter.py` (or new `rpc_client.py`)

```python
import asyncio
from typing import Optional

class DeltaChatRpcClient:
    def __init__(self, accounts_dir: str, rpc_server_path: str):
        self.accounts_dir = accounts_dir
        self.rpc_server_path = rpc_server_path
        self.transport = None
        self.rpc = None

    async def start(self) -> bool:
        import deltachat2
        from deltachat2.transport import IOTransport
        self.transport = IOTransport(
            accounts_dir=self.accounts_dir,
            rpc_server=self.rpc_server_path,
        )
        self.transport.start()
        self.rpc = _AsyncRpc(deltachat2.Rpc(self.transport))
        return await self._wait_ready(timeout=10)

    async def _wait_ready(self, timeout: float = 10.0) -> bool:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                await self.rpc.get_all_accounts()
                return True
            except Exception:
                await asyncio.sleep(0.5)
        return False

    def stop(self) -> None:
        if self.transport:
            try:
                self.transport.close()
            except Exception:
                pass
            self.transport = None
        self.rpc = None

    def is_alive(self) -> bool:
        if not self.transport or not self.rpc:
            return False
        return True
```

### Step 2: Refactor `DeltaChatAdapter.connect()` to use the client

**File:** `adapter.py:298-388`

Replace inline transport/rpc setup with:
```python
self._rpc_client = DeltaChatRpcClient(dc_accounts_path, rpc_server_path)
if not await self._rpc_client.start():
    logger.error("RPC server failed to start")
    return False
self.rpc = self._rpc_client.rpc
```

### Step 3: Update disconnect/cleanup

**File:** `adapter.py:390-414`

Call `self._rpc_client.stop()` in `_cleanup()` / `disconnect()`.

### Step 4: Verify

```bash
python3 -m py_compile adapter.py
```

**Expected:** No syntax errors.

## Acceptance Criteria

- [ ] `DeltaChatRpcClient` exists and encapsulates transport start/stop.
- [ ] `connect()` uses it.
- [ ] `disconnect()` stops it cleanly.

## Definition of Done

- RPC transport lifecycle is centralized in one reusable client.

## Dependencies
TC-005

## What this is NOT
- It does not add automatic reconnect yet (TC-008).
- It does not change the async RPC wrapping strategy.

## Workflow lane evidence
- Review: inspect `DeltaChatRpcClient` and `connect()`.
- Acceptance: `python3 -m py_compile adapter.py` passes.
- Commit: `git add -A && git commit -m "TC-006: add DeltaChatRpcClient wrapper"`
