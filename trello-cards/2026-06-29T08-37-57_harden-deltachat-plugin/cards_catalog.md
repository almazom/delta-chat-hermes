# Cards Catalog

| ID | Epic | Title | SP | Status |
|----|------|-------|----|--------|
| TC-001 | 01-state-boundaries | Create per-adapter plugin state class | 2 | backlog |
| TC-002 | 01-state-boundaries | Replace global _active_adapter with context-bound state | 3 | backlog |
| TC-003 | 01-state-boundaries | Replace global token maps with per-adapter token store | 2 | backlog |
| TC-004 | 01-state-boundaries | Move OpenRPC spec cache into state object | 1 | backlog |
| TC-005 | 01-state-boundaries | Harden version check to fail closed | 1 | backlog |
| TC-006 | 02-reliability-reconnects | Create DeltaChatRpcClient wrapper for transport lifecycle | 3 | backlog |
| TC-007 | 02-reliability-reconnects | Replace sleep-based readiness with polling loop | 2 | backlog |
| TC-008 | 02-reliability-reconnects | Add event-loop health monitor and reconnect logic | 4 | backlog |
| TC-009 | 03-module-refactor | Extract chat token functions to chat_tokens.py | 2 | backlog |
| TC-010 | 03-module-refactor | Extract RPC tools to rpc_tools.py | 3 | backlog |
| TC-011 | 03-module-refactor | Extract media handling to media.py | 3 | backlog |
| TC-012 | 03-module-refactor | Shrink adapter.py to platform interface only | 3 | backlog |
| TC-013 | 04-voice-hardening | Gate CallManager behind DELTACHAT_ENABLE_VOICE_CALLS | 2 | backlog |
| TC-014 | 04-voice-hardening | Add bounded queues and thread-pool limits | 2 | backlog |
| TC-015 | 04-voice-hardening | Add audio cache cleanup after STT | 1 | backlog |
| TC-016 | 05-automation-tests | Add non-interactive CLI flags to setup.py | 2 | backlog |
| TC-017 | 05-automation-tests | Add tests for state isolation and token round-trip | 2 | backlog |
| TC-018 | 05-automation-tests | Add tests for reconnect and non-interactive setup | 3 | backlog |
| TC-019 | 05-automation-tests | Run full pytest suite and fix regressions | 2 | backlog |
