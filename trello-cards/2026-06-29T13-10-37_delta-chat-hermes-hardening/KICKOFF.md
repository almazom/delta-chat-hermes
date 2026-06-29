# KICKOFF

Input plan: `/Users/mac-mini-m4-almazom/.plan/2026-06-29_delta-chat-hermes-hardening.md`
Execution SSOT: `trello-cards/2026-06-29T13-10-37_delta-chat-hermes-hardening/kanban.json`
Derived state: `trello-cards/2026-06-29T13-10-37_delta-chat-hermes-hardening/state.json`
Board view: `trello-cards/2026-06-29T13-10-37_delta-chat-hermes-hardening/BOARD.md`

Start sequence:
1. Read `kanban.json` as the only writable execution state.
2. Process cards from backlog → in_progress → review → simplification → auto_commit → done.
3. Run `make test` after each card.
