# hermes-deltachat-platform Hardening — Card Package

Generated: 2026-06-29T08:37:57Z

## Contents

- `kanban.json` — SSOT execution state
- `state.json` — derived agile state machine state
- `BOARD.md` — terminal board view
- `KICKOFF.md` — start sequence for implementer
- `trello_quality_gate.json` — quality gate result
- `cards_catalog.md` — flat card index
- Epic directories with individual `TC-NNN.md` cards

## How to use

1. Start execution with `/trello-to-implement --kanban-file kanban.json`.
2. Follow KICKOFF.md sequence.
3. Update `kanban.json` as cards move through lanes.

## Quality gate

- Score: 96/100
- Passed: true
- No blockers
- All cards ≤ 4 SP
- No dependency cycles
