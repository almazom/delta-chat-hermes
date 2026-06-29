# TC-001: Fix DC_ACCOUNTS_PATH global env mutation

**Epic:** 01-isolation
**Story Points:** 2
**Priority:** P1
**Status:** backlog
**Dependencies:** None

## User Story

As a Hermes operator, I want the Delta Chat plugin to be hardened, so that multi-profile isolation, RPC access control, and test coverage meet production readiness.

## Story Points: 2

## Description

Fix DC_ACCOUNTS_PATH global env mutation.

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
None

## What this is NOT

- Not a full rewrite of the plugin.
- Not adding new user-facing features.
