# TC-011: Run adversarial re-review and fix P0s

**Epic:** 06-verification
**Story Points:** 2
**Priority:** P1
**Status:** backlog
**Dependencies:** TC-001, TC-003, TC-004, TC-005, TC-006, TC-007, TC-008, TC-009, TC-010

## User Story

As a Hermes operator, I want the Delta Chat plugin to be hardened, so that multi-profile isolation, RPC access control, and test coverage meet production readiness.

## Story Points: 2

## Description

Run adversarial re-review and fix P0s.

## Prerequisites

- Plan approved: `/Users/mac-mini-m4-almazom/.plan/2026-06-29_delta-chat-hermes-hardening.md`

## Implementation Steps

### Step 1: Implement

Edit the relevant files and preserve existing behavior.

### Step 2: Verify

```bash
cd /Users/mac-mini-m4-almazom/projects/delta-chat-hermes
make test
```

**Expected:** 50 passed, 2 skipped.

## Acceptance Criteria

- [ ] Change implemented and minimal.
- [ ] `make test` passes.
- [ ] No regressions in existing tests.

## Definition of Done

- All acceptance criteria pass.
- Code committed and pushed to `origin/main`.

## Dependencies
TC-001, TC-003, TC-004, TC-005, TC-006, TC-007, TC-008, TC-009, TC-010

## What this is NOT

- Not a full rewrite of the plugin.
- Not adding new user-facing features.
