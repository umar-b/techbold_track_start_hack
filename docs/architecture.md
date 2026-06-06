# Architecture

Visual overview of the AI Service Desk Autopilot. Vocabulary is defined in
[`../CONTEXT.md`](../CONTEXT.md); the rationale behind each choice is in
[`adr/`](adr/). Diagrams are Mermaid — they render on GitHub and in VS Code.

---

## 1. Components

A thin React workspace over a FastAPI backend that orchestrates a human-in-the-loop
troubleshooting loop. The backend is the **only** holder of the ERP token and SSH key —
the browser never sees them. Events stream to the UI over SSE; technician actions are
REST POSTs (ADR-0008).

```mermaid
flowchart LR
  subgraph Browser["Technician workspace (React + Vite)"]
    UList["Ticket list"]
    UDetail["Ticket detail + system info"]
    URun["Run view: event stream, plan approval, abort"]
    UAct["Activity review + submit"]
  end

  subgraph Backend["Backend (FastAPI) — holds token + SSH key"]
    API["API layer: REST actions + SSE events"]
    Loop["Agent loop (single planning agent) — ADR-0007"]
    LLM["llm.py (Azure OpenAI, native tools / JSON fallback) — ADR-0006"]
    Safety["safety: SAFE / GATED / BLOCKED + blocklist — ADR-0002, 0004"]
    SSH["ssh_runner (paramiko, timeouts)"]
    ERPc["phoenix_client (timeouts + retries)"]
    Audit["audit + redact (append-only, secret-safe) — ADR-0004"]
    Act["activity generator (redacted)"]
    Mem["memory: markdown graph — ADR-0001, 0009"]
    Store["runstore (in-memory) + audit-to-file — ADR-0008"]
  end

  subgraph External["Provided services"]
    Phoenix["Phoenix ERP mock"]
    VM["Customer Linux VM"]
    Azure["Azure OpenAI"]
  end

  Browser -- "REST actions" --> API
  API -- "SSE events" --> Browser
  API --> Loop
  Loop --> LLM --> Azure
  Loop --> Mem
  Loop --> Safety --> SSH --> VM
  Loop --> Store
  API --> ERPc --> Phoenix
  Act --> ERPc
  Loop --> Act
  Loop --> Audit
  Safety --> Audit
  Act --> Audit
  Mem -. "sanitized note on resolve" .-> Audit
```

---

## 2. Run loop (sequence)

Two approval gates: **connect + diagnose**, then the **fix plan**. SAFE reads auto-run;
GATED commands run only inside an approved plan; BLOCKED never runs. Memory pre-fills the
plan as *hypotheses to verify*, never as auto-actions (ADR-0009).

```mermaid
sequenceDiagram
  actor T as Technician
  participant FE as Frontend
  participant BE as Agent loop
  participant SF as Safety
  participant VM as Linux VM (SSH)
  participant AI as Azure OpenAI
  participant ERP as Phoenix ERP
  participant M as Memory

  T->>FE: Open ticket, click Start
  FE->>BE: POST /api/runs
  BE->>ERP: load ticket + customer system, set PENDING
  BE->>M: retrieve related notes (tag + 1-hop links)
  M-->>BE: seed hypotheses (verify, do not apply)

  Note over BE,T: Gate 1 — approve connect + diagnostics
  T->>BE: approve
  BE->>SF: check read-only commands
  SF-->>BE: SAFE
  BE->>VM: run diagnostics (auto, streamed)
  BE->>AI: rank hypotheses + draft fix plan
  AI-->>BE: plan (steps: command, risk, reason, expected)

  Note over BE,T: Gate 2 — approve fix plan
  BE-->>FE: plan (SSE)
  T->>BE: approve / edit / reject

  loop each approved step
    BE->>SF: check command
    alt BLOCKED
      SF-->>BE: refuse (never runs)
    else SAFE / GATED
      BE->>VM: execute (streamed + audited)
    end
  end

  BE->>VM: verify persistence (is-enabled / on-disk) — ADR-0005
  alt verified
    BE->>AI: draft activity (redacted)
    BE-->>FE: activity draft
    T->>BE: review + submit
    BE->>ERP: POST activity, set DONE
    BE->>M: write sanitized note + links
  else fix failed
    Note over BE,T: discard plan, re-plan (bounded) → escalate
  end
```

---

## 3. Run state machine

```mermaid
stateDiagram-v2
  [*] --> Created
  Created --> AwaitingConnect: load ticket + system
  AwaitingConnect --> Diagnosing: approve connect
  Diagnosing --> Planning: evidence gathered
  Planning --> AwaitingPlan: plan proposed
  AwaitingPlan --> Executing: approve plan
  AwaitingPlan --> Planning: reject / edit
  Executing --> Verifying: steps done
  Verifying --> Documenting: persists + symptom gone
  Verifying --> Replanning: fix failed
  Replanning --> AwaitingPlan: new plan
  Replanning --> Escalated: attempts exhausted
  Documenting --> AwaitingReview: activity drafted
  AwaitingReview --> Submitted: submit to ERP
  Submitted --> Done: status DONE + memory note
  Done --> [*]

  AwaitingConnect --> Aborted: abort
  Diagnosing --> Aborted: abort
  AwaitingPlan --> Aborted: abort
  Executing --> Aborted: abort
  Escalated --> Aborted: abort
  Aborted --> [*]
```

---

## 4. Command safety tiers

Every proposed command passes the safety layer before it can run. The model proposes;
code disposes (ADR-0002, ADR-0004).

```mermaid
flowchart TD
  Cmd["Proposed command"] --> Sec{"Reads a secret path?<br/>(/etc/shadow, *.env, keys)"}
  Sec -- yes --> Block["BLOCKED — never runs"]
  Sec -- no --> Danger{"Dangerous blanket op?<br/>(rm -rf /, chmod -R 777 /etc,<br/>drop database, disable firewall...)"}
  Danger -- yes --> Block
  Danger -- no --> Mut{"Mutates state?"}
  Mut -- "no (read-only)" --> Safe["SAFE — auto-run, logged"]
  Mut -- yes --> Gated{"Inside an approved plan?"}
  Gated -- no --> Hold["Wait for plan approval"]
  Gated -- yes --> Run["GATED — execute, audited"]
  Safe --> Audit["Audit log + redact"]
  Run --> Audit
```
