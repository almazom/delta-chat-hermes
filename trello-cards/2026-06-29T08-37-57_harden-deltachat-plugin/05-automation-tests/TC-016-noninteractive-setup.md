# TC-016: Add non-interactive CLI flags to setup.py

**Epic:** 05 — Automation & Tests
**Story Points:** 2
**Priority:** P1
**Status:** TODO
**Dependencies:** None

## User Story

As a DevOps operator, I want `setup.py` to run without interactive prompts, so that Delta Chat account creation can be automated in CI or headless installs.

## Story Points:** 2

## Description

`setup.py` currently calls `input()` repeatedly. This ticket adds CLI flags for non-interactive account creation.

## Prerequisites

- None

## Implementation Steps

### Step 1: Add argparse to `setup.py`

**File:** `setup.py:310-378`

```python
import argparse

def main():
    parser = argparse.ArgumentParser(description="Delta Chat account setup for Hermes")
    parser.add_argument("--non-interactive", action="store_true", help="Run without prompts")
    parser.add_argument("--relay", default=None, help="Public relay domain, e.g. nine.testrun.org")
    parser.add_argument("--email", default=None, help="Email address for existing credentials")
    parser.add_argument("--password", default=None, help="Password for existing email")
    parser.add_argument("--name", default=None, help="Display name for the bot")
    parser.add_argument("--profile", default=None, help="Hermes profile name")
    args = parser.parse_args()
    ...
```

### Step 2: Add non-interactive setup path

**File:** `setup.py`

Add a new method or branch in `interactive_setup`:
```python
if args.non_interactive:
    name = args.name or (profile_name if profile_name != "default" else "Hermes Bot")
    if not accounts:
        account_id = self.rpc.add_account()
        self.rpc.set_config(account_id, "displayname", name)
    else:
        account_id = accounts[0]["id"]
    if not self.rpc.is_configured(account_id):
        if args.email and args.password:
            self.rpc.add_or_update_transport(account_id, {"addr": args.email, "password": args.password})
        elif args.relay:
            self.rpc.add_transport_from_qr(account_id, f"dcaccount:{args.relay}")
        else:
            relays = get_relay_servers()
            self.rpc.add_transport_from_qr(account_id, f"dcaccount:{relays[0]}")
    return account_id
```

### Step 3: Keep interactive mode as default

The existing `input()` flow remains the default when `--non-interactive` is not passed.

### Step 4: Verify

```bash
python3 -m py_compile setup.py
python setup.py --help
```

**Expected:** Help output shows the new flags.

## Acceptance Criteria

- [ ] `--non-interactive` flag exists.
- [ ] `--relay`, `--email`, `--password`, `--name`, `--profile` flags exist.
- [ ] Non-interactive mode never calls `input()`.
- [ ] Interactive mode remains unchanged.

## Definition of Done

- `setup.py` can be used in scripts and CI.

## Dependencies
None

## What this is NOT
- It does not add a REST API for account creation.
- It does not support multiple accounts at once.

## Workflow lane evidence
- Review: inspect argparse setup and non-interactive branch.
- Acceptance: `python setup.py --help` shows flags.
- Commit: `git add -A && git commit -m "TC-016: add non-interactive CLI flags to setup.py"`
