# TC-012: Shrink adapter.py to platform interface only

**Epic:** 03 — Module Refactor
**Story Points:** 3
**Priority:** P1
**Status:** TODO
**Dependencies:** TC-009, TC-010, TC-011

## User Story

As a maintainer, I want `adapter.py` to contain only the platform adapter interface, so that the module has a single responsibility and is easier to navigate.

## Story Points:** 3

## Description

After extracting chat tokens, RPC tools, and media handling, `adapter.py` should only contain `DeltaChatAdapter`, `check_requirements`, `validate_config`, `_env_enablement`, and `register_platform`. Remove any leftover dead code.

## Prerequisites

- [ ] TC-009 complete
- [ ] TC-010 complete
- [ ] TC-011 complete

## Implementation Steps

### Step 1: Audit `adapter.py`

**File:** `adapter.py`

Remove any helper functions that are now in other modules:
- `_get_or_create_chat_token` / `_resolve_chat_token` → gone via TC-009
- `register_rpc_tools` → gone via TC-010
- `_resolve_blob_path`, `_copy_to_hermes_cache`, media overrides → gone via TC-011
- `_handle_audio_message_UNUSED` → delete if still present
- `_DESTRUCTIVE_METHODS` → moved to `chat_tokens.py`
- `_fetch_spec` → move to `rpc_tools.py` or keep if still needed by adapter

### Step 2: Ensure imports are clean

**File:** `adapter.py`

Only import what the adapter class needs:
```python
import functools
import html
import json
import os
import sys
import asyncio
import logging
from typing import Optional, Dict, Any

from chat_tokens import get_or_create_chat_token, resolve_chat_token
from media import resolve_blob_path, copy_to_hermes_cache
```

### Step 3: Verify no dead code

```bash
python3 -m py_compile adapter.py
```

**Expected:** No syntax errors.

### Step 4: Run existing tests

```bash
pytest tests/test_adapter_integration.py -q
```

**Expected:** Tests pass or failures are documented.

## Acceptance Criteria

- [ ] `adapter.py` is under ~600 lines.
- [ ] It contains only platform interface concerns.
- [ ] It imports helpers from `chat_tokens.py`, `media.py`, `rpc_tools.py`.

## Definition of Done

- `adapter.py` has one clear responsibility: the Delta Chat platform adapter interface.

## Dependencies
TC-009, TC-010, TC-011

## What this is NOT
- It does not change external behavior.
- It does not add new features.

## Workflow lane evidence
- Review: inspect `adapter.py` line count and contents.
- Acceptance: `python3 -m py_compile adapter.py` passes.
- Commit: `git add -A && git commit -m "TC-012: shrink adapter.py to platform interface"`
