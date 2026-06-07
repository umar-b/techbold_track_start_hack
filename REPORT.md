# Technical Report — AI Service Desk Autopilot

A technician-in-the-loop autopilot for the techbold START Hack. It reads incident
tickets from the **Phoenix ERP**, connects to the affected customer's Linux VM over
**SSH**, runs an AI-driven diagnostic loop in which **the technician approves every
state-changing action**, validates the fix with the provided test, and writes a clean,
redacted **activity** back to the ERP. A human approves every change; the agent never
acts unsupervised.

This report is the engineering writeup. Domain vocabulary is in [`CONTEXT.md`](CONTEXT.md),
the decision log in [`docs/adr/`](docs/adr/), diagrams in
[`docs/architecture.md`](docs/architecture.md), and setup/run in the [`README`](README.md).

---

## 1. Problem and approach

Each incident is a *symptom* on a customer VM (e.g. "status API unavailable", "uploads
fail", "orders can't be created"). The cause is unknown and lives on the box. A correct
resolution must:

1. **find the real root cause** (not the symptom),
2. apply the **smallest persistent fix** (survives a reboot),
3. **change nothing dangerous** (no data loss, no blanket permissions, no secret exposure),
4. **validate** with `sudo /opt/hackathon/public-test.sh`, and
5. **document** it back to the ERP.

Two design commitments shape everything else:

- **The model reasons; the code enforces.** The agent is trusted to *diagnose* from live
  evidence using a guidebook of method + failure-class knowledge (ADR-0003) — there are no
  hard-coded per-ticket playbooks, so the same logic generalises to unseen incidents. But
  **safety, secret-redaction, approval gating, and graceful degradation are enforced in
  code** (ADR-0002, ADR-0004), never left to the model.
- **The human is always in the loop.** Read-only diagnostics auto-run; *every*
  state-changing command runs only inside a technician-approved **Plan** (ADR-0002).

---

## 2. Architecture

```
React workspace ──HTTP──▶ FastAPI backend ──HTTP──▶ Phoenix ERP mock
(technician UI)           (token + SSH key   ──SSH──▶ Customer Linux VM
                           live only here)    ──HTTP──▶ Azure OpenAI (gpt-5.x)
```

The ERP token and SSH key live **only** in the backend, never in the browser. Modules are
small and single-purpose (ADR-0008; the run loop was extracted from the routers per the
project's own "thin routers" rule):

| Module | Responsibility |
|---|---|
| `app/main.py` | Thin FastAPI handlers: validate, talk to the ERP, hand off to the orchestrator; SSE event stream. |
| `app/orchestrator.py` | The `analyze → approve → execute → verify → replan` run loop on a background worker; idle-session reaper. |
| `app/agent.py` | The single planning agent: emits `diagnose` / `plan` / `finish` as JSON; loads the guidebook. |
| `app/safety.py` | `SAFE` / `GATED` / `BLOCKED` classifier + secret-read blocking. The model proposes; this disposes. |
| `app/audit.py` | Secret redactor + append-only audit log (per-run JSONL). |
| `app/memory.py` | The markdown-graph memory: write a sanitized note per resolved run; retrieve related notes to seed plans. |
| `app/phoenix_client.py` | Typed ERP client: timeouts, bounded 5xx-only retry, typed errors. |
| `app/ssh_runner.py` | paramiko runner; per-VM key resolution; one reused connection per run. |
| `app/llm.py` | Model-agnostic LangChain chat-model layer in JSON mode; never breaks the loop. |
| `app/activity.py` | Drafts the ERP activity from the run history (LLM, with a deterministic fallback). |

### The run loop

A **Run** is one technician working one ticket against one VM. It advances on a background
worker so POSTs return immediately and the browser streams progress over SSE (ADR-0008):

1. **Analyze** — the agent proposes one read-only diagnostic at a time; each is
   safety-checked and, if `SAFE`, auto-run and logged. The loop converges to a plan in
   bounded stages (a soft "you have enough evidence, plan now" nudge, then a hard cap that
   forces a single final plan/finish, then an absolute attempt limit) so the model can
   neither under- nor over-diagnose.
2. **Approval gate** — the agent emits a **Plan** (ranked root cause + ordered `GATED`
   steps + a validation list). The Run pauses; the technician **approves / edits / rejects**
   (rejection with free text drives a "discuss" replan).
3. **Execute → verify** — the whole approved plan runs once, then the validation
   (including `public-test.sh`) runs. Verified → `finished`. Not verified → the agent forms
   a **new** plan to approve (the only loop, human-gated, bounded by a max-attempt cap).
4. **Document** — the technician reviews an LLM-drafted, redacted activity and submits it;
   a sanitized memory note is appended.

A second, lighter gate exists: if the agent wants to run a `GATED`/sensitive *diagnostic*
(e.g. read an app's `.env` for a port), it pauses for one-off approval rather than silently
dropping it — the technician approves gaining real evidence, output redacted.

---

## 3. The agent — method, not recipes

The agent (ADR-0003, ADR-0007) is a **single planning agent** that reasons over the
ticket, the live customer system, and the executed-command history, guided by
[`app/guidebook.md`](backend/app/guidebook.md) (a diagnostic *method* + common failure
classes, explicitly framed as illustrative, not an exhaustive checklist). It emits one
JSON action — `diagnose` (one read-only command), `plan`, or `finish` — using **JSON mode**
rather than native tool-calling, which is unreliable on this deployment (ADR-0010). Without
a configured LLM it degrades to a read-only baseline so the loop still runs end to end
(ADR-0004).

**Two-tier routing (ADR-0011):** all in-loop reasoning (diagnosis *and* planning) runs on
the stronger reasoning model; the cheap model is reserved for the activity draft. A loud
one-time warning fires if the reasoning model is misconfigured to the fast model.

### Diagnostic-discipline hardening

Reliable first-try resolution depends less on the model's raw ability than on **gathering
complete evidence before committing to a plan**. The agent's system prompt encodes four
*general* rules (none tied to any specific ticket — they are sound Linux-troubleshooting
practice and apply equally to the hidden incidents):

1. **Restart semantics.** A config change only takes effect when the *process* re-reads it.
   `enable --now` does **not** restart an already-running unit, and `daemon-reload` only
   reloads unit files — so a unit/drop-in/EnvironmentFile/config edit on a running service
   needs an explicit `systemctl restart`, then re-check the symptom *after* the restart.
2. **Complete localisation before planning.** Read the failing component's config
   (`systemctl cat`, its EnvironmentFile, the app config) and reconcile its real values
   (port/path/host/DB-role) against what the ticket says the working state is. Faults
   co-occur (e.g. a service both *not-enabled* **and** *misconfigured*), so a plan that
   fixes only the first symptom fails validation.
3. **Cross-component values from the source.** A value that must match a peer — the
   address/port it listens on — is read from that peer (`ss -tlnp`, its config), never
   guessed; a "connection refused" means *nothing is listening* on the targeted address.
4. **Literal, simple plan steps.** Plan steps run verbatim, each as a separate command with
   no shared shell state, so concrete values are discovered first and written literally;
   each step is one simple command — never a multi-line script, loop, or nested `$(...)`
   (which corrupts e.g. `sed`), and never a placeholder (the safety layer hard-blocks
   `<dbname>` / `/ACTUAL/PATH/...` style placeholders).

> **A deliberate non-goal:** we did not keep adding rules to force the single hardest
> incident to first-try. An over-long prompt measurably *degrades* instruction-following on
> the reasoning model (it regressed the reliable tickets), so the prompt is kept lean and
> the human-gated replan loop — a designed feature, not a failure — handles the rare
> second attempt.

---

## 4. Safety, auditability and responsible AI

Safety is **code-enforced** (ADR-0002, ADR-0004), independent of what the model proposes.

**Risk tiers** ([`app/safety.py`](backend/app/safety.py)) classify every command before it
can run, after stripping a leading `sudo`/`env` so escalation can't smuggle anything past:

- **SAFE** — non-mutating reads; auto-run, always logged. (Reading key material is *not* SAFE.)
- **GATED** — state-changing or sensitive-config reads; run only inside an approved plan, output redacted.
- **BLOCKED** — never run, cannot be approved: fork bombs, `mkfs`, raw `dd` to a device,
  `drop/truncate/dropdb/initdb`, disabling firewall/audit/ssh, clearing history, **recursive
  delete/chown/`chmod 777` on system roots**, reading private keys / `/etc/shadow`, and
  unresolved **placeholders**. Crucially, only *blanket* operations on system roots are
  blocked — a *targeted* `chown` on a narrow app path (e.g. an upload dir) is `GATED`, so a
  legitimate fix is approvable while a dangerous one is not.

**Redaction** ([`app/audit.py`](backend/app/audit.py)) scrubs private-key blocks, `KEY=value`
secrets, bearer tokens, URI credentials, `--password`/`-u user:pass` flags, and inline DB
passwords from *every* string before it is logged, returned to the UI, written to an
activity, or saved to a memory note.

**Audit log** — append-only, immutable, per-run, mirrored to JSONL so it survives a restart;
exposed read-only at `/api/runs/{id}/audit` and downloadable in the UI. It records every
command with its risk tier, approval, exit code, plus events steps don't carry
(`plan_proposed`, `plan_approved`, `verified_resolved`, `escalated`, `activity_submitted`).

**Hard-fails avoided by construction** (per [`docs/scoring.md`](docs/scoring.md) §C): no DB
drop/reinit, no customer-data deletion, no blanket permissions on system roots, no disabling
of security controls, no secret exposure, no running the app as a DB superuser to bypass
grants. Persistence is verified *without self-rebooting* — rebooting these VMs redeploys
them to the broken state, so the agent never reboots; it checks `is-enabled` / on-disk state
instead (ADR-0005).

---

## 5. Memory — the differentiator

Memory (ADR-0001, ADR-0009) is a **markdown graph**, not a vector DB: each resolved Run
appends one sanitized note (symptom signature, root cause, fix as command-classes, failed
attempts, verification, tags, and `[[wiki-links]]` to related notes). On a new Run, related
notes are retrieved by a **lexical tag/keyword prefilter + 1-hop link traversal** (no
embeddings, no DB) and fed to the agent as **hypotheses-to-verify that seed the plan —
never actions to apply, and never removing an approval gate** (ADR-0009). Notes pass the
same redactor as an activity, so the committed brain is secret-free. The UI surfaces the
graph (a Memory browser) and a per-run "seeded by N past incidents" chip.

This is the product's core bet: a shared, inspectable brain that makes the *next* technician
faster, while every safety guarantee stays intact.

---

## 6. Testing and reliability

Two layers, deliberately separated:

**Hermetic suite (default).** `cd backend && pytest -q` → **165 passed, 12 skipped**, in
<1 s, fully offline (ERP, SSH, and LLM mocked). Covers the safety classifier, redaction,
the ERP client, the agent JSON contract, the run-state machine, the orchestrator loop,
memory write/retrieve/graph-linking, and the activity drafter.

**Live end-to-end suite (gated).** `backend/tests/test_e2e_live.py` (+ the reusable
`e2e_driver.py`) drives the **whole real workflow** against live infrastructure — real
Phoenix, real SSH VMs, real Azure — one test per assigned ticket, plus cross-cutting safety,
memory, and audit/redaction checks. It is **skipped unless `RUN_LIVE_E2E=1`**, so the
default suite stays hermetic. Crucially, it asserts only the **shape** of a correct run
(finished, exactly one fix attempt, `public-test.sh` exits 0, activity written, secret-free
memory note, complete redacted audit) — **never a ticket-specific command** — so the same
bar applies unchanged to the four hidden incidents in the final eval. The technician role is
played by auto-approving the agent's plan *unedited* (the honest test of whether the agent
gets it right unaided).

**Methodology.** Each iteration: reset all VMs via the Phoenix `POST /api/v1/me/reset`
endpoint (wired as `PhoenixClient.reset_me()` — deliberately *not* exposed as a backend
route), wait for a confirmed reboot (detected via low `/proc/uptime`, since reachability
alone can catch a pre-reboot host), run all five tickets, read the audit on any failure, and
fix the **general method** — never the specific ticket.

**Results.** Across repeated full live cycles, four of the five assigned incidents resolve
**on the first approved plan**; the fifth — a three-stage monitoring pipeline with a
misconfigured producer, the hardest case — reliably resolves, typically on the second plan
via the human-gated replan loop. Every run passed `public-test.sh`, submitted a complete
activity, wrote a secret-free memory note, and produced a clean redacted audit trail; a
parity smoke confirmed the deployed container resolves a ticket over real HTTP, not just the
in-process test client.

---

## 7. Engineering quality

- **Separation of concerns** — ERP client, SSH runner, agent, safety layer, audit/redaction,
  memory, and activity drafter are independent modules (rubric E).
- **Resilience** — per-request HTTP timeouts + bounded 5xx-only retry on the ERP; SSH
  connect/command timeouts with typed errors and reconnect-once on a dropped channel; the
  LLM layer returns `None` rather than throwing, degrading to a read-only baseline; an
  idle-SSH-session reaper evicts connections parked at an approval gate.
- **Secret handling** — `.env` and `keys/` are git-ignored; `.env.example` documents every
  variable; nothing secret is in the repo (verified by scan across memory, audit, and
  activities — zero hits).
- **Reproducibility** — `docker compose up --build`, a real README, runnable tests, and
  stdlib smoke checks for Phoenix/SSH/Azure.

---

## 8. How it maps to the rubric ([`docs/scoring.md`](docs/scoring.md))

| Cat | What we provide |
|---|---|
| **A · ERP workflow (20)** | Load tickets + customer system, set status, submit a complete activity; searchable/filterable/sortable ticket list; 401/404/empty states handled cleanly. |
| **B · Troubleshooting (35)** | Guidebook-driven root-cause diagnosis + minimal **persistent** fixes, validated with the provided `public-test.sh`; generalises to hidden VMs (no per-ticket playbooks). |
| **C · Safety & responsible AI (20)** | Code-enforced `SAFE/GATED/BLOCKED`, secret-read blocking, append-only redacted audit, plan-level human approval, minimal targeted changes. |
| **D · Technician experience (10)** | Ticket overview + detail with system info, live step log, plan approve/edit/reject + discuss, abort, SSE connection indicator, run timer, toasts, keyboard shortcuts. |
| **E · Engineering (15)** | Separated modules, this report + README + ADRs, hermetic *and* live tests, timeouts/retries everywhere, `.env.example`, no secrets in the repo. |

---

## 9. Assumptions and limitations

- **One incident per run**; run control state is in-memory (single-process demo). The audit
  log, activities mirror, and memory are file-backed and survive container recreation;
  moving run state to a DB is a product decision, not a tidy-up (ADR-0008).
- **Rebooting a VM redeploys it to the broken state**, so the agent never self-reboots;
  persistence is verified via `is-enabled` / on-disk checks (ADR-0005).
- **Without Azure configured**, the agent degrades to read-only baseline diagnostics so the
  loop still runs end to end (ADR-0004).
- Embeddings exist on the Azure resource but are intentionally **unwired** — memory is a
  markdown graph by design (ADR-0001); semantic recall is a config change away, not wired
  into any path.

---

## 10. Reproducing the results

```bash
cp .env.example .env        # fill in Phoenix token, SSH keys, Azure creds
docker compose up --build   # UI :5173 · API + Swagger :8000/docs

# hermetic tests (no network)
cd backend && .venv/bin/python -m pytest -q          # 165 passed, 12 skipped

# live end-to-end (needs real Phoenix + SSH + Azure)
RUN_LIVE_E2E=1 SSH_SESSION_IDLE_TTL=0 .venv/bin/python -m pytest tests/test_e2e_live.py -v

# frontend typecheck
cd ../frontend && npx tsc --noEmit
```
