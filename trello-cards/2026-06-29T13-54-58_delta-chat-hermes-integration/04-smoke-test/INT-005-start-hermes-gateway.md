# INT-005: Start Hermes gateway and verify DC connection

SP: 2

## Goal
Gateway loads the adapter and connects to the RPC server.

## Acceptance
- No import errors in gateway logs.
- Adapter reports connected with bot address.
- `deltachat-rpc-server` process is running under gateway.

## Verification
Check logs for:
`Delta Chat connected successfully. Bot address: ...`
