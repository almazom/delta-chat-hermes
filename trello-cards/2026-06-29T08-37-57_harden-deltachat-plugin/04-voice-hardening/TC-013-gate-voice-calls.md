# TC-013: Gate CallManager behind DELTACHAT_ENABLE_VOICE_CALLS

**Epic:** 04 — Voice Call Hardening
**Story Points:** 2
**Priority:** P0
**Status:** TODO
**Dependencies:** TC-012

## User Story

As a Mac Mini M4 operator, I want voice calls disabled by default, so that local Whisper + aiortc do not exhaust the 16 GB RAM budget unless I explicitly opt in.

## Story Points:** 2

## Description

Voice calls currently instantiate `CallManager` unconditionally in `adapter.py:374-375`. This ticket gates that behind `DELTACHAT_ENABLE_VOICE_CALLS` and makes `aiortc` a lazy import.

## Prerequisites

- [ ] TC-012 complete

## Implementation Steps

### Step 1: Add env flag helper

**File:** `adapter.py`

```python
def _voice_calls_enabled() -> bool:
    return os.getenv("DELTACHAT_ENABLE_VOICE_CALLS", "").strip().lower() in ("1", "true", "yes", "on")
```

### Step 2: Gate CallManager instantiation

**File:** `adapter.py:374-375`

Change:
```python
from call_handler import CallManager
self._call_manager = CallManager(self)
```

To:
```python
self._call_manager = None
if _voice_calls_enabled():
    try:
        from call_handler import CallManager
        self._call_manager = CallManager(self)
        logger.info("Voice calls enabled")
    except ImportError as e:
        logger.error("Voice calls enabled but aiortc/deltachat2 missing: %s", e)
```

### Step 3: Guard call event handlers

**File:** `adapter.py:985-994`

```python
elif event_kind == EventType.INCOMING_CALL:
    if self._call_manager:
        asyncio.create_task(self._call_manager.handle_incoming_call(event))
    else:
        logger.info("Incoming call ignored: voice calls disabled")
```

### Step 4: Update `plugin.yaml`

**File:** `plugin.yaml`

Add:
```yaml
optional_env:
  - name: DELTACHAT_ENABLE_VOICE_CALLS
    description: "Enable experimental WebRTC voice calls (requires aiortc; high RAM use)"
    prompt: "Enable voice calls"
    password: false
```

### Step 5: Update docs

**File:** `docs/voice-calls.md`

Add a note that the flag must be set and that local Whisper on 16 GB is not recommended.

### Step 6: Verify

```bash
python3 -m py_compile adapter.py
DELTACHAT_ENABLE_VOICE_CALLS=0 python -c "from adapter import DeltaChatAdapter; print('voice disabled ok')"
```

**Expected:** Both pass.

## Acceptance Criteria

- [ ] `CallManager` is only instantiated when `DELTACHAT_ENABLE_VOICE_CALLS=1`.
- [ ] Incoming call events are ignored when voice is disabled.
- [ ] `plugin.yaml` documents the env var.

## Definition of Done

- Voice calls are opt-in and do not load heavy dependencies by default.

## Dependencies
TC-012

## What this is NOT
- It does not remove voice call functionality.
- It does not add cloud STT configuration.

## Workflow lane evidence
- Review: inspect `connect()` and `_handle_dc_event()` guards.
- Acceptance: `DELTACHAT_ENABLE_VOICE_CALLS=0` import test passes.
- Commit: `git add -A && git commit -m "TC-013: gate voice calls behind env flag"`
