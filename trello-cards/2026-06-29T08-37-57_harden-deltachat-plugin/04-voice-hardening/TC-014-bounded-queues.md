# TC-014: Add bounded queues and thread-pool limits

**Epic:** 04 — Voice Call Hardening
**Story Points:** 2
**Priority:** P1
**Status:** TODO
**Dependencies:** TC-013

## User Story

As a Hermes operator, I want bounded audio queues and limited thread pools in the voice pipeline, so that a runaway call cannot consume unbounded RAM or spawn unlimited threads.

## Story Points:** 2

## Description

`call_handler.py:173` uses an unbounded `asyncio.Queue`. `adapter.py:137-138` uses the default executor for every RPC call. This ticket bounds both.

## Prerequisites

- [ ] TC-013 complete

## Implementation Steps

### Step 1: Bound TTS audio queue

**File:** `call_handler.py:173`

```python
self._queue: asyncio.Queue = asyncio.Queue(maxsize=1200)  # ~24s of audio
```

In `enqueue_tts_frames`, log and drop oldest if full:
```python
def enqueue_tts_frames(self, frames: list) -> None:
    for frame in frames:
        if self._queue.full():
            logger.warning("TTS queue full; dropping oldest frame to avoid unbounded growth")
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self._queue.put_nowait(frame)
```

### Step 2: Bound RPC executor

**File:** `adapter.py:121-139`

Change `_AsyncRpc` to use a shared executor with limited workers:
```python
class _AsyncRpc:
    _executor = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="dc-rpc-")

    def __init__(self, rpc) -> None:
        object.__setattr__(self, "_rpc", rpc)

    def __getattr__(self, name: str):
        method = getattr(object.__getattribute__(self, "_rpc"), name)
        async def _async_call(*args):
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._executor, method, *args)
        return _async_call
```

Add `import concurrent.futures` at the top of `adapter.py`.

### Step 3: Bound STT semaphore

**File:** `call_handler.py:285`

Already a semaphore; verify it is sufficient. Optionally tighten to 1 if not already.

### Step 4: Verify

```bash
python3 -m py_compile adapter.py call_handler.py
```

**Expected:** No syntax errors.

## Acceptance Criteria

- [ ] `HermesAudioTrack._queue` has a `maxsize`.
- [ ] `_AsyncRpc` uses a bounded `ThreadPoolExecutor`.
- [ ] Overflow behavior is logged, not silent.

## Definition of Done

- Voice and RPC paths have bounded concurrency resources.

## Dependencies
TC-013

## What this is NOT
- It does not add backpressure to the STT pipeline.
- It does not limit the number of concurrent calls.

## Workflow lane evidence
- Review: inspect queue and executor declarations.
- Acceptance: `python3 -m py_compile adapter.py call_handler.py` passes.
- Commit: `git add -A && git commit -m "TC-014: bound audio queue and RPC thread pool"`
