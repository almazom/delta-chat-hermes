# KICKOFF: delta-chat-hermes-integration

Goal: move the hardened delta-chat-hermes plugin from "code ready" to "running Hermes Delta Chat bot" with ≥95% confidence.

Entry criteria:
- Hardening card package is done (81 tests pass, lint clean).
- `deltachat-rpc-server` is installable on macOS ARM64.
- Hermes gateway is already running other platforms (discord, telegram).

Exit criteria:
- Account created and configured.
- Hermes gateway loads the platform without errors.
- A real Delta Chat message is received and a reply is sent.

SSOT: this card package + state.json.
