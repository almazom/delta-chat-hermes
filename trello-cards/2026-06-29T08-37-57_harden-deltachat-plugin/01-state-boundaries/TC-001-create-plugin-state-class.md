# TC-001: Create per-adapter plugin state class

**Epic:** 01 — State & Boundaries
**Story Points:** 2
**Priority:** P0
**Status:** TODO
**Dependencies:** None

## User Story

As a Hermes gateway operator, I want each Delta Chat platform adapter to own its own state, so that multiple Hermes profiles can run in isolation without corrupting each other's token maps or active adapter references.

## Story Points: 2

## Description

The adapter currently stores critical state at module scope in `adapter.py` (`_active_adapter`, `_chat_id_to_token`, `_chat_token_to_id`, `_spec_cache`). This ticket creates a single `DeltaChatPluginState` dataclass/class that holds all of this state per adapter instance.

## Prerequisites

- None

## Implementation Steps

### Step 1: Create `DeltaChatPluginState` in a new module

**File:** `adapter.py` (or new `state.py` if preferred)

```python
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

@dataclass
class DeltaChatPluginState:
    """All mutable plugin state scoped to a single adapter instance."""
    adapter: Optional["DeltaChatAdapter"] = None
    chat_id_to_token: Dict[int, str] = field(default_factory=dict)
    chat_token_to_id: Dict[str, int] = field(default_factory=dict)
    spec_cache: Optional[dict] = None
```

### Step 2: Verify import path

```bash
python3 -m py_compile adapter.py
```

**Expected:** No syntax errors.

## Acceptance Criteria

- [ ] `DeltaChatPluginState` exists and has fields for adapter, token maps, and spec cache.
- [ ] The class can be instantiated with no arguments.
- [ ] A py_compile check passes.

## Definition of Done

- The new state class is available for the next cards to consume, with no behavioral changes yet.

## Dependencies
None

## What this is NOT
- It does not replace the global variables yet; that is TC-002/TC-003/TC-004.
- It does not add persistence beyond the existing DC config token storage.

## Workflow lane evidence
- Review: code inspection of the new class.
- Acceptance: `python3 -m py_compile adapter.py` passes.
- Commit: `git add -A && git commit -m "TC-001: add DeltaChatPluginState dataclass"`
