# INT-006: Smoke-test send/receive message

SP: 2

## Goal
Prove end-to-end messaging works through Hermes.

## Acceptance
- Send a message from another Delta Chat client to the bot address.
- Hermes receives it and generates a reply.
- Reply is delivered back to the sender.

## Verification
- Log shows incoming message event.
- No RPC errors in logs.
