# TC-002: Replace global _active_adapter with context-bound state

**Epic:** 01 — State & Boundaries
**Story Points:** 3
**Priority:** P0
**Status:** TODO
**Dependencies:** TC-001

## User Story

As a multi-profile Hermes user, I want each profile's Delta Chat adapter to be referenced independently, so that RPC tools and call managers always operate on the correct account.

## Story Points: 3

## Description

`adapter.py:142-143` defines `_active_adapter = None` and every RPC tool handler reads this global. If two Hermes profiles load this plugin, the second adapter overwrites the first, and tools/calls target the wrong account. This ticket stores the adapter instance in the Hermes gateway context and passes it to tool handlers.

## Prerequisites

- [ ] TC-001 complete

## Implementation Steps

### Step 1: Add state holder to `DeltaChatAdapter`

**File:** `adapter.py`

```python
class DeltaChatAdapter(BasePlatformAdapter):
    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform("deltachat-platform"))
        self.state = DeltaChatPluginState(adapter=self)
        # ... existing init ...
```

### Step 2: Remove module-level `_active_adapter`

**File:** `adapter.py:142-143`

Delete:
```python
# Tracks the currently connected adapter instance; used by RPC tools.
_active_adapter = None
```

### Step 3: Update `connect()` and `disconnect()`

**File:** `adapter.py:370-372`, `adapter.py:390-394`

Remove assignments to `_active_adapter`. The adapter instance is now reachable via `self.state.adapter`.

### Step 4: Pass adapter/state into tool registration

**File:** `adapter.py:1665`

Change `register_rpc_tools(ctx)` signature to accept the adapter instance:

```python
def register_rpc_tools(ctx, adapter: DeltaChatAdapter) -> None:
    ...
```

Update tool handlers to close over `adapter` instead of reading `_active_adapter`.

### Step 5: Update `__init__.py`

**File:** `__init__.py`

```python
def register(ctx):
    register_platform(ctx)
    # NOTE: tools are registered per adapter instance by the gateway.
```

If the gateway expects tools registered at plugin load time, instead register a factory that resolves the active adapter from ctx. Document the chosen approach in `Agents.md`.

### Step 6: Verify

```bash
python3 -m py_compile adapter.py __init__.py
```

**Expected:** No syntax errors.

## Acceptance Criteria

- [ ] No module-level `_active_adapter` remains in `adapter.py`.
- [ ] Tool handlers use a bound adapter reference.
- [ ] Two `DeltaChatAdapter` instances can coexist without overwriting each other's state.

## Definition of Done

- The global active adapter singleton is eliminated; each adapter carries its own state.

## Dependencies
TC-001

## What this is NOT
- It does not yet change how chat tokens are stored (TC-003).
- It does not implement multi-profile gateway support in Hermes itself.

## Workflow lane evidence
- Review: grep confirms `_active_adapter` is gone.
- Acceptance: `python3 -m py_compile adapter.py __init__.py` passes.
- Commit: `git add -A && git commit -m "TC-002: remove global _active_adapter"`
