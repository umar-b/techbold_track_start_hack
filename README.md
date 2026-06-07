# AI Service Desk Autopilot

An AI-assisted technician workspace for the techbold START Hack track. It reads incident
tickets from the **Phoenix ERP**, connects to a customer's Linux VM over **SSH**, and — under
the technician's approval on every change — **diagnoses, fixes, validates**, and writes a clean
**activity** back to the ERP. A human approves every state-changing action; the agent never acts
unsupervised.

- **Technical writeup:** [`REPORT.md`](REPORT.md) — architecture, agent method, safety, testing & reliability
- **Domain vocabulary:** [`CONTEXT.md`](CONTEXT.md)
- **Decisions & rationale:** [`docs/adr/`](docs/adr/) (11 ADRs)
- **Diagrams (components, run loop, state, safety tiers):** [`docs/architecture.md`](docs/architecture.md)

## How it works

```
React workspace ──HTTP──▶ FastAPI backend ──HTTP──▶ Phoenix ERP mock
(technician UI)           (token + SSH key   ──SSH──▶ Customer Linux VM
                           live only here)    ──HTTP──▶ Azure OpenAI (gpt-5.4-nano)
```

A single planning **agent** drives a human-in-the-loop loop with two approval gates:

1. **Connect & diagnose** — the agent runs *read-only* diagnostics (auto-approved as `SAFE`) and
   forms a ranked root-cause hypothesis.
2. **Approve the fix plan** — the technician approves/edits/rejects a plan of `GATED`
   (state-changing) commands. `BLOCKED` commands (dangerous blanket ops, secret reads) never run,
   even if approved. The fix is then validated (incl. `sudo /opt/hackathon/public-test.sh`) and a
   redacted activity is drafted for submission.

Safety, secret-redaction, and fix-persistence are enforced in **code**, not left to the model
(see [ADR-0002](docs/adr/0002-plan-level-approval-risk-tiers.md),
[ADR-0004](docs/adr/0004-code-enforced-safety-redaction-and-fallback.md),
[ADR-0005](docs/adr/0005-persistence-without-self-reboot.md)).

## Project structure

```
backend/app/
  main.py            thin FastAPI handlers (validate, talk to ERP, delegate) + SSE
  orchestrator.py    the propose→approve→execute→verify→replan run loop + idle-session reaper
  config.py          typed settings (env / .env)
  phoenix_client.py  ERP client (timeouts, 5xx-only retry, typed errors)
  ssh_runner.py      paramiko runner; per-VM key resolver; connection reused per run
  safety.py          SAFE / GATED / BLOCKED classifier + secret-read blocking
  audit.py           secret redactor + append-only audit log (→ per-run JSONL)
  runstore.py        in-memory run store
  llm.py             Azure OpenAI v1 wrapper, JSON mode (never breaks the loop)
  agent.py           planning agent (diagnose|plan|finish) + guidebook
  guidebook.md       diagnostic method + failure-class knowledge + safety notes
  activity.py        ERP activity drafter (redacted; LLM + deterministic fallback)
backend/tests/       pytest — safety, redaction, ERP client, agent, run orchestration
frontend/src/        React: TicketList, TicketDetail, RunView, ActivityReview
scripts/smoke/       stdlib checks: Phoenix auth, SSH-to-VM, Azure
```

## Setup

```bash
cp .env.example .env        # fill in the values below
```

| Variable | Meaning |
|---|---|
| `PHOENIX_API_BASE_URL`, `PHOENIX_API_TOKEN` | ERP mock URL + your team token |
| `SSH_PRIVATE_KEY_PATH` / `SSH_KEY_DIR`, `SSH_USERNAME` | SSH access (`azureuser`). Single key, or per-VM `caseN_key.pem` in `SSH_KEY_DIR` (N = `ticket_id − 7000`) |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` | Bring-your-own LLM |
| `VITE_API_BASE` | URL the browser uses to reach the backend (default `http://localhost:8000`) |

> **LLM note (verified):** the endpoint is an **Azure AI Foundry project** endpoint and is called
> over the OpenAI-compatible **v1 API** (`{endpoint}/openai/v1/`, *no* `api-version`). Native
> tool-calling is unreliable on `gpt-5.4-nano`, so the agent uses **JSON mode**. See
> [ADR-0006](docs/adr/0006-single-llm-provider-azure.md). `.env` and `keys/` are git-ignored —
> never commit secrets.

## Run

```bash
docker compose up --build
```
- Technician workspace → http://localhost:5173
- Backend API + Swagger → http://localhost:8000/docs

### Without Docker
```bash
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload      # backend on :8000
cd ../frontend && npm install && npm run dev  # frontend on :5173
```

## Verify it works

```bash
# 1) Integration smoke checks (need a filled-in .env)
python scripts/smoke/check_phoenix.py        # ERP token + tickets
python scripts/smoke/check_ssh.py            # SSH into the first ticket's VM (uname/id/sudo)
python scripts/smoke/check_azure.py          # chat + JSON mode on the deployment

# 2) Backend tests (no network — mocked, fully offline)
cd backend && .venv/bin/python -m pytest -q  # 165 passed, 12 skipped

# 3) Frontend typecheck
cd frontend && npx tsc --noEmit
```

### Live end-to-end (optional — needs a filled-in `.env`)

A per-ticket suite drives the **whole** real workflow (start → diagnose → approve → execute
→ validate → submit) against live Phoenix + SSH VMs + Azure. It is **skipped by default** so
the suite above stays hermetic; opt in with `RUN_LIVE_E2E=1`. Assertions are generic (a run
finishes, `public-test.sh` passes, the activity is written, the memory note is secret-free,
the audit is complete) — never ticket-specific, so the same bar applies to unseen incidents.

```bash
cd backend && RUN_LIVE_E2E=1 SSH_SESSION_IDLE_TTL=0 \
  .venv/bin/python -m pytest tests/test_e2e_live.py -v
```

> Reset between runs with the Phoenix `POST /api/v1/me/reset` endpoint (wired as
> `PhoenixClient.reset_me()`; it reboots the VMs back to the broken state). It is
> deliberately **not** exposed as a backend route — nothing in the workspace should reboot
> every customer VM with one click. The suite's fixture calls it once up front.

## How it maps to the rubric

- **A (ERP workflow)** — `phoenix_client` + the run API load tickets, customer-system, set
  status, and submit a complete activity; 404/empty/auth surface cleanly.
- **B (troubleshooting)** — guidebook-driven diagnosis + minimal, *persistent* fixes (services
  `enable`d, config on disk), validated with the provided `public-test.sh`.
- **C (safety)** — code-enforced `SAFE/GATED/BLOCKED` tiers, secret-read blocking, append-only
  audit log (exposed read-only at `/api/runs/{id}/audit` and viewable in the UI), redaction on
  every output/activity, plan-level human approval.
- **D (UX)** — searchable/filterable + keyboard-navigable ticket list, detail + system info,
  live step log (collapsible output, per-step timing, copy-command), a live SSE connection
  indicator + run timer, keyboard shortcuts (A/R/Esc), toasts, approve/edit/reject and a plan
  **discuss** loop. Plus a **Run history** view (`/api/runs` + `/api/stats`) and a **Memory
  browser** (`/api/memory`) with a per-run "seeded by N past incidents" chip.
- **E (engineering)** — separated modules, this README, runnable tests, timeouts + bounded
  retries, `.env.example`, no secrets in the repo.

## Assumptions

- One incident per run; run state is in-memory (single-process demo) — the audit log is persisted
  per run. Production memory/state would move to a file server/DB (storage is abstracted).
- Rebooting a VM **redeploys it to the broken initial state** and takes it briefly offline, so the
  agent never self-reboots; persistence is verified via `is-enabled`/on-disk checks (ADR-0005).
- Without Azure configured, the agent degrades to read-only baseline diagnostics so the loop still
  runs end to end.

## Troubleshooting

- **401 from Phoenix** → check `PHOENIX_API_TOKEN`.
- **SSH connect fails / "banner" errors** → confirm the right key (`caseN_key.pem`), `azureuser`,
  and VM reachability; the backend reuses one connection per run to avoid reconnect churn.
- **Azure 400 "API version not supported"** → you're on the classic path; this deployment needs
  the **v1** path with no `api-version` (already handled by `llm.py`; see ADR-0006).
- **Agent only runs read-only diagnostics** → Azure vars not set, or tool/JSON call failing — run
  `scripts/smoke/check_azure.py`.
- **Can't reach a local mock from Docker** → use `host.docker.internal`, not `localhost`.

## License

[MIT](LICENSE).
