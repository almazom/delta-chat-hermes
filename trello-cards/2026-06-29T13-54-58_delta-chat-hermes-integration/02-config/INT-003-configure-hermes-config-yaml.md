# INT-003: Configure Hermes config.yaml for deltachat-platform

SP: 2

## Goal
Tell Hermes gateway to load the Delta Chat platform adapter.

## Acceptance
- `config.yaml` contains a `deltachat:` section.
- No YAML syntax errors.
- Gateway starts without platform-load errors.

## Notes
Add a minimal section:
```yaml
deltachat:
  enabled: true
  extra:
    rpc_server: deltachat-rpc-server
```
Also add `deltachat` to `platforms:` runtime list if Hermes requires it.
