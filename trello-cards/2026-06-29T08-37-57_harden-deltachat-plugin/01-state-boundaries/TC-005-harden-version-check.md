# TC-005: Harden version check to fail closed

**Epic:** 01 — State & Boundaries
**Story Points:** 1
**Priority:** P0
**Status:** TODO
**Dependencies:** None

## User Story

As a Hermes operator, I want the adapter to refuse connection when it cannot verify the Delta Chat core version, so that an incompatible or broken RPC server does not silently pass the gate.

## Story Points: 1

## Description

`adapter.py:115-118` returns `True` if the version check raises an exception. This is fail-open behavior. This ticket makes it fail closed.

## Prerequisites

- None

## Implementation Steps

### Step 1: Change exception handling in `_check_dc_version`

**File:** `adapter.py:83-118`

Change:
```python
    except Exception as e:
        logger.warning(f"Could not check Delta Chat version: {e}")
        # Don't block connection for version check failures
        return True
```

To:
```python
    except Exception as e:
        logger.error(f"Could not check Delta Chat version: {e}")
        return False
```

### Step 2: Update tests if any assert the old behavior

**File:** `tests/test_version.py`

Adjust expectations so that version-check failure returns `False`.

### Step 3: Verify

```bash
python3 -m py_compile adapter.py
pytest tests/test_version.py -q
```

**Expected:** All tests pass; py_compile passes.

## Acceptance Criteria

- [ ] `_check_dc_version` returns `False` when the RPC call raises.
- [ ] `connect()` aborts when version check fails.
- [ ] Existing version tests are updated.

## Definition of Done

- Version verification is fail-closed.

## Dependencies
None

## What this is NOT
- It does not add automatic Delta Chat core upgrades.
- It does not change the minimum version number.

## Workflow lane evidence
- Review: inspect `_check_dc_version` exception branch.
- Acceptance: `pytest tests/test_version.py -q` passes.
- Commit: `git add -A && git commit -m "TC-005: fail closed on version check errors"`
