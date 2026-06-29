# TC-018: Add tests for reconnect and non-interactive setup

**Epic:** 05 — Automation & Tests
**Story Points:** 3
**Priority:** P1
**Status:** TODO
**Dependencies:** TC-008, TC-016

## User Story

As a developer, I want tests for RPC reconnect behavior and non-interactive setup, so that these production-critical paths do not regress.

## Story Points:** 3

## Description

Add tests covering reconnect retry limits and the non-interactive setup CLI.

## Prerequisites

- [ ] TC-008 complete
- [ ] TC-016 complete

## Implementation Steps

### Step 1: Add reconnect tests

**File:** `tests/test_reconnect.py`

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_reconnect_gives_up_after_max_attempts():
    from adapter import DeltaChatAdapter
    adapter = MagicMock(spec=DeltaChatAdapter)
    adapter.connect = AsyncMock(return_value=False)
    adapter.disconnect = AsyncMock()
    adapter._mark_disconnected = MagicMock()

    # Bind the real _reconnect method to the mock
    result = await DeltaChatAdapter._reconnect(adapter)
    assert result is False
    assert adapter.connect.call_count == 5
```

### Step 2: Add non-interactive setup test

**File:** `tests/test_setup.py`

```python
def test_non_interactive_argparse():
    import setup
    # argparse exits on --help, so test the parser directly
    parser = setup._build_argparser()
    args = parser.parse_args(["--non-interactive", "--relay", "nine.testrun.org", "--name", "Bot"])
    assert args.non_interactive is True
    assert args.relay == "nine.testrun.org"
    assert args.name == "Bot"
```

### Step 3: Run tests

```bash
pytest tests/test_reconnect.py tests/test_setup.py -q
```

**Expected:** Tests pass.

## Acceptance Criteria

- [ ] Reconnect retry limit is tested.
- [ ] Non-interactive CLI flags are tested.
- [ ] Tests do not require real network or Delta Chat server.

## Definition of Done

- Reconnect and setup automation have automated coverage.

## Dependencies
TC-008, TC-016

## What this is NOT
- It does not test actual WebRTC calls.
- It does not test real email account creation.

## Workflow lane evidence
- Review: inspect `tests/test_reconnect.py` and `tests/test_setup.py`.
- Acceptance: `pytest tests/test_reconnect.py tests/test_setup.py -q` passes.
- Commit: `git add -A && git commit -m "TC-018: add reconnect and setup CLI tests"`
