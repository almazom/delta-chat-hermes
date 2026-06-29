# TC-019: Run full pytest suite and fix regressions

**Epic:** 05 — Automation & Tests
**Story Points:** 2
**Priority:** P0
**Status:** TODO
**Dependencies:** TC-012, TC-013, TC-017, TC-018

## User Story

As a maintainer, I want all existing and new tests to pass after the refactor, so that the hardening does not introduce regressions.

## Story Points:** 2

## Description

Run the full test suite, fix any failures caused by the module refactor or state changes, and ensure the plugin still loads.

## Prerequisites

- [ ] TC-012 complete
- [ ] TC-013 complete
- [ ] TC-017 complete
- [ ] TC-018 complete

## Implementation Steps

### Step 1: Run syntax checks

```bash
python3 -m py_compile __init__.py adapter.py chat_tokens.py rpc_tools.py media.py setup.py call_handler.py
```

**Expected:** All pass.

### Step 2: Run full pytest

```bash
pytest tests/ -q
```

### Step 3: Fix regressions

Common issues to fix:
- Import errors after module split.
- Tests that referenced `_active_adapter` or `_chat_id_to_token` globals.
- Mock setup that now needs `state` argument.

### Step 4: Verify plugin registration

```bash
HERMES_PLUGINS_DEBUG=1 python -c "from __init__ import register; print('ok')"
```

**Expected:** No errors.

## Acceptance Criteria

- [ ] `python3 -m py_compile` passes for all modified files.
- [ ] `pytest tests/ -q` passes (or failures are documented blockers).
- [ ] Plugin imports cleanly.

## Definition of Done

- The hardened plugin passes automated verification.

## Dependencies
TC-012, TC-013, TC-017, TC-018

## What this is NOT
- It does not add new integration tests against a real Delta Chat server.
- It does not run on CI runners without the required deps.

## Workflow lane evidence
- Review: inspect test output.
- Acceptance: `pytest tests/ -q` passes.
- Commit: `git add -A && git commit -m "TC-019: fix test regressions after hardening"`
