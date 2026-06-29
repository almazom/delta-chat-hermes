# Harden hermes-deltachat-platform — Board

Total cards: 19 | Total SP: 40 | Done: 0/19 (0%)

────────────────────────────────────────────────────────
Epic 01 — State & Boundaries   ████░░░░░░  0%  (0/5 done, 9 SP)
Epic 02 — Reliability          ████░░░░░░  0%  (0/3 done, 9 SP)
Epic 03 — Module Refactor      ████░░░░░░  0%  (0/4 done, 11 SP)
Epic 04 — Voice Hardening      ████░░░░░░  0%  (0/3 done, 5 SP)
Epic 05 — Automation & Tests   ████░░░░░░  0%  (0/4 done, 9 SP)
────────────────────────────────────────────────────────

## Critical path

TC-001 → TC-002 → TC-010 → TC-012 → TC-013 → TC-019

## Cards

| ID | Epic | Title | SP | Status | Deps |
|----|------|-------|----|--------|------|
| TC-001 | 01 | Create per-adapter plugin state class | 2 | backlog | None |
| TC-002 | 01 | Replace global _active_adapter with context-bound state | 3 | backlog | TC-001 |
| TC-003 | 01 | Replace global token maps with per-adapter token store | 2 | backlog | TC-001 |
| TC-004 | 01 | Move OpenRPC spec cache into state object | 1 | backlog | TC-001 |
| TC-005 | 01 | Harden version check to fail closed | 1 | backlog | None |
| TC-006 | 02 | Create DeltaChatRpcClient wrapper for transport lifecycle | 3 | backlog | TC-005 |
| TC-007 | 02 | Replace sleep-based readiness with polling loop | 2 | backlog | TC-006 |
| TC-008 | 02 | Add event-loop health monitor and reconnect logic | 4 | backlog | TC-007 |
| TC-009 | 03 | Extract chat token functions to chat_tokens.py | 2 | backlog | TC-003 |
| TC-010 | 03 | Extract RPC tools to rpc_tools.py | 3 | backlog | TC-002, TC-009 |
| TC-011 | 03 | Extract media handling to media.py | 3 | backlog | None |
| TC-012 | 03 | Shrink adapter.py to platform interface only | 3 | backlog | TC-009, TC-010, TC-011 |
| TC-013 | 04 | Gate CallManager behind DELTACHAT_ENABLE_VOICE_CALLS | 2 | backlog | TC-012 |
| TC-014 | 04 | Add bounded queues and thread-pool limits | 2 | backlog | TC-013 |
| TC-015 | 04 | Add audio cache cleanup after STT | 1 | backlog | TC-013 |
| TC-016 | 05 | Add non-interactive CLI flags to setup.py | 2 | backlog | None |
| TC-017 | 05 | Add tests for state isolation and token round-trip | 2 | backlog | TC-001, TC-003 |
| TC-018 | 05 | Add tests for reconnect and non-interactive setup | 3 | backlog | TC-008, TC-016 |
| TC-019 | 05 | Run full pytest suite and fix regressions | 2 | backlog | TC-012, TC-013, TC-017, TC-018 |
