# INT-004: Create Delta Chat account via setup.py

SP: 2

## Goal
Create a configured DC account under `~/.hermes/deltachat-platform/`.

## Acceptance
- `setup.py` exits 0.
- Account directory has SQLite db and blobs.
- SecureJoin link or address is printed.

## Command (relay example)
```bash
python3 /Users/mac-mini-m4-almazom/projects/delta-chat-hermes/setup.py \
  --non-interactive --profile default --name "Hermes Bot" --relay nine.testrun.org
```

## Security
Do not pass `--password`. Use `DELTACHAT_EMAIL_PASSWORD` if email transport is needed.
