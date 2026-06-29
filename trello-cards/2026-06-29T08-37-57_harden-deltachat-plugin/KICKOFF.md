# KICKOFF — Harden hermes-deltachat-platform

Input plan: `~/.plan/2026-06-29_harden-hermes-deltachat-plugin.md`
Execution SSOT: `kanban.json`
Derived state: `state.json`
Board view: `BOARD.md`

## Start sequence

1. Read `kanban.json` as the only writable execution state.
2. Read `BOARD.md` for overview.
3. Start with the first unblocked card: **TC-001**.
4. Advance cards through: backlog → in_progress → code_review → simplification → auto_commit → done.

## Execution rules

- Never modify `kanban.json` by hand; update it via state transitions only.
- Commit after every card with message `TC-NNN: <description>`.
- Do not push to remote repos without operator approval.
- If a card is blocked, log evidence, mark it blocked, and continue with unblocked cards.

## Plan summary

Harden the Delta Chat platform adapter for production on a 16 GB Mac Mini by removing global mutable state, adding RPC reconnects, splitting monolithic `adapter.py`, gating voice calls, making setup non-interactive, and adding tests.
