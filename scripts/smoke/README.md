# Smoke checks

Throwaway scripts to verify the three external integrations **before** building, so
unknowns surface now and not during the demo. Stdlib only (except `check_ssh.py`,
which needs `paramiko`). They read the repo-root `.env`.

```bash
cp .env.example .env        # fill in Builder Base creds + your Azure values
pip install paramiko        # only needed for the SSH check

python scripts/smoke/check_phoenix.py   # ERP token + list tickets
python scripts/smoke/check_ssh.py       # SSH into the first ticket's VM, run uname/id/sudo
python scripts/smoke/check_azure.py     # chat + TOOL-CALLING + JSON mode on gpt-5.4-nano
```

What each tells you:

- **check_phoenix** — token valid, tickets load. A 401 means a bad `PHOENIX_API_TOKEN`.
- **check_ssh** — key loads, VM reachable, and whether `azureuser` has passwordless sudo
  (needed for fixes and `sudo /opt/hackathon/public-test.sh`).
- **check_azure** — the make-or-break: does `gpt-5.4-nano` support **native tool-calling**?
  If yes, build on native tools; if no, build on the strict-JSON fallback (ADR-0006).
  If a request errors on a parameter, the script prints the error body — that's the value to fix.

Delete this directory once the real backend wraps these integrations.
