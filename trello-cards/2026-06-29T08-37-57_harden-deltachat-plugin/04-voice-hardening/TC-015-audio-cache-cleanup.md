# TC-015: Add audio cache cleanup after STT

**Epic:** 04 — Voice Call Hardening
**Story Points:** 1
**Priority:** P1
**Status:** TODO
**Dependencies:** TC-013

## User Story

As a Hermes operator, I want temporary call WAV files cleaned up after transcription, so that the audio cache does not grow without bound on disk.

## Story Points:** 1

## Description

`call_handler.py:424-434` writes WAV files for STT but never deletes them. This ticket deletes the file after successful transcription and limits cache retention.

## Prerequisites

- [ ] TC-013 complete

## Implementation Steps

### Step 1: Delete WAV after transcription

**File:** `call_handler.py:382-399`

```python
async def _process_utterance(self, pcm: bytes) -> None:
    wav_path = await asyncio.to_thread(self._pcm_to_wav, pcm)
    if not wav_path:
        return
    t0 = time.monotonic()
    async with self._stt_lock:
        try:
            result = await asyncio.to_thread(self._transcribe, wav_path)
            transcript = result.get("transcript", "").strip() if result.get("success") else ""
        except Exception as e:
            logger.error("STT failed: %s", e)
            return
        finally:
            try:
                os.unlink(wav_path)
                logger.debug("Cleaned up STT WAV: %s", wav_path)
            except Exception:
                pass
    ...
```

### Step 2: Add cache rotation on startup

**File:** `call_handler.py:281-282`

In `IncomingAudioBuffer.__init__`, add:
```python
self._rotate_audio_cache()
```

Add method:
```python
def _rotate_audio_cache(self) -> None:
    try:
        files = sorted(self._audio_cache.glob("call_*.wav"), key=lambda p: p.stat().st_mtime)
        for old in files[:-20]:
            old.unlink(missing_ok=True)
            logger.debug("Rotated old audio cache file: %s", old)
    except Exception as e:
        logger.debug("Audio cache rotation failed (non-fatal): %s", e)
```

### Step 3: Verify

```bash
python3 -m py_compile call_handler.py
```

**Expected:** No syntax errors.

## Acceptance Criteria

- [ ] WAV file is deleted after transcription.
- [ ] Old `call_*.wav` files are pruned to the latest 20 on buffer init.

## Definition of Done

- Temporary call audio does not accumulate indefinitely.

## Dependencies
TC-013

## What this is NOT
- It does not delete user-sent voice message blobs (those are DC-owned).
- It does not compress or archive audio.

## Workflow lane evidence
- Review: inspect `_process_utterance` and `_rotate_audio_cache`.
- Acceptance: `python3 -m py_compile call_handler.py` passes.
- Commit: `git add -A && git commit -m "TC-015: clean up temporary call audio files"`
