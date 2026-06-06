# Smoke checks

Throwaway scripts to verify the three external integrations **before** building, so
unknowns surface now and not during the demo. Stdlib only (except `check_ssh.py`,
which needs `paramiko`). They read the repo-root `.env`.

```bash
cp .env.example .env        # fill in Builder Base creds + your Azure values
pip install paramiko        # only needed for the SSH check

python scripts/smoke/check_phoenix.py   # ERP token + list tickets
python scripts/smoke/check_ssh.py       # SSH into the first ticket's VM, run uname/id/sudo
python scripts/smoke/check_llm.py       # LLM seam (LangChain, provider-agnostic): JSON completion
```

What each tells you:

- **check_phoenix** — token valid, tickets load. A 401 means a bad `PHOENIX_API_TOKEN`.
- **check_ssh** — key loads, VM reachable, and whether `azureuser` has passwordless sudo
  (needed for fixes and `sudo /opt/hackathon/public-test.sh`).
- **check_llm** — goes through the backend `app.llm` seam (LangChain, model-agnostic;
  ADR-0010), so it tests whatever `LLM_PROVIDER` is set (azure-openai default, or ollama).
  Confirms `llm.available()` and that `complete_json()` returns a parsed JSON dict (JSON mode
  is the agent path). Degrades with a clear message when creds/config or deps are missing.

Delete this directory once the real backend wraps these integrations.
