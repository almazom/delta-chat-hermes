# delta-chat-hermes-integration

Source plan: on-the-fly integration runbook derived from /p2i hardening output.

## Lanes

- 01-infrastructure
- 02-config
- 03-account
- 04-smoke-test
- 05-docs

## Cards

- INT-001: Install deltachat-rpc-server binary (1 SP)
- INT-002: Link plugin into Hermes plugins directory (1 SP)
- INT-003: Configure Hermes config.yaml for deltachat-platform (2 SP)
- INT-004: Create Delta Chat account via setup.py (2 SP)
- INT-005: Start Hermes gateway and verify DC connection (2 SP)
- INT-006: Smoke-test send/receive message (2 SP)
- INT-007: Document integration runbook (1 SP)
