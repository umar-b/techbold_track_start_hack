# AI Service Desk Autopilot — Design Document

**Project:** techbold START Hack Vienna '26  
**Date:** 2026-06-06  
**Track:** AI Service Desk Autopilot  

---

## 1. Vision & Initial Idea

The problem: IT incidents get logged in an ERP, a technician opens the ticket, SSHs into a Linux VM, manually diagnoses the issue, runs fix commands, verifies, then writes up what they did. This is slow, inconsistent, and the institutional knowledge of "what worked last time" lives in people's heads.

The idea: Build an AI agent that does the diagnosis and fix proposal work, while keeping the technician in control of every category of action. The agent does the thinking and grunt work; the human approves scope and reviews results. After each resolved incident, the system learns — storing what worked as a searchable knowledge base so future similar incidents get faster, better-targeted fix plans.

Two outputs per resolved incident:
1. **ERP activity** — clean, structured summary submitted back to Phoenix for grading and customer record
2. **Persistent memory entry** — detailed step-by-step record with context, stored in a vector database, retrieved semantically when a similar incident appears later

---

## 2. Constraints & Context

### Hackathon scoring (100 pts total)

| Category | Points | What matters |
|---|---|---|
| B. Troubleshooting performance | 35 | 5 hidden incidents × 7pts — root cause correct, fix works, persists, no regression |
| C. Safety, auditability, responsible AI | 20 | Audit trail, no dangerous commands, secret protection, human control |
| A. ERP workflow | 20 | Load tickets, complete activity schema, handle errors |
| E. Engineering quality | 15 | Clean structure, tests, error handling, .env |
| D. Technician UX | 10 | Overview, detail, progress, logs, review/retry/abort |

**Hard constraint:** Human must approve every action category. Agent never executes unsupervised.

**Hard fails (any incident → 0, possible disqualification):**
- `chmod -R 777` on system directories
- Deleting or reinitializing databases
- Disabling firewall/audit/security services
- Reading, logging, or exposing secrets
- Deleting logs to cover actions
- Running app as superuser to bypass DB permissions

### ERP API (Phoenix)
- Auth: `Bearer <PHOENIX_API_TOKEN>`
- Key endpoints: `GET /api/v1/me/tickets`, `GET /api/v1/tickets/{id}`, `GET /api/v1/tickets/{id}/customer-system`, `PATCH /api/v1/tickets/{id}/status`, `POST /api/v1/activities/create`
- Customer-system returns: `{ip, port, username, os, notes}` — SSH target

---

## 3. Architecture Decision

### Options considered

**Option A — Custom ReAct loop** ✅ Selected  
Hand-written observe→think→act loop. LLM is a pure text-in/text-out call behind a thin abstraction. Tools are plain Python functions. No framework.

**Option B — LangGraph state machine**  
Agent modeled as explicit directed graph with typed state. Good structure but heavy dependency, opinionated, harder to go provider-agnostic.

**Option C — Sequential pipeline**  
Fixed 6-stage pipeline, each stage calls LLM once. Simplest but brittle — can't loop back when a step fails or the fix doesn't work.

### Why Option A

- **Full control over the approval pause points** — the loop can pause mid-execution waiting for WebSocket input from the frontend without fighting framework abstractions
- **LLM-agnostic** — one `llm.py` file, one env var to swap provider (Anthropic/OpenAI/Azure/local)
- **Debuggable** — every think/act/result is a plain Python dict, easy to log and inspect
- **Hackathon speed** — no framework to learn, ~200 lines of loop logic
- **Iterable** — agent can loop back on failed steps, retry with different approach, unlike a fixed pipeline

---

## 4. System Architecture

```
┌─────────────────────────────────────────────────────┐
│  FRONTEND (React + TypeScript + Vite)               │
│                                                     │
│  Ticket List → Ticket Detail → Category Approval    │
│  → Live Agent Stream → Activity Review → Submit     │
└──────────────────┬──────────────────────────────────┘
                   │ HTTP REST + WebSocket
┌──────────────────▼──────────────────────────────────┐
│  BACKEND (FastAPI + Python 3.11)                    │
│                                                     │
│  ┌─────────────┐  ┌────────────┐  ┌──────────────┐ │
│  │ erp_client  │  │ ssh_runner │  │safety_filter │ │
│  └─────────────┘  └────────────┘  └──────────────┘ │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │  agent.py — ReAct loop                       │   │
│  │                                              │   │
│  │  tools:                                      │   │
│  │    ssh_exec(cmd) → stdout/stderr/exit_code   │   │
│  │    erp_get_ticket(id) → ticket data          │   │
│  │    erp_get_customer_system(id) → SSH creds   │   │
│  │    memory_search(query) → similar past fixes │   │
│  │    memory_save(entry) → persist to ChromaDB  │   │
│  │    read_file(path) → file contents from VM   │   │
│  └──────────────────┬───────────────────────────┘   │
│                     │                               │
│  ┌──────────────────▼───────────────────────────┐   │
│  │  llm.py           memory.py     guidebook.py │   │
│  │  (provider swap)  (ChromaDB)    (markdown)   │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
           │ SSH (paramiko)           │ REST (httpx)
┌──────────▼──────────┐   ┌──────────▼──────────────┐
│   Linux VM (target) │   │   Phoenix ERP API        │
└─────────────────────┘   └──────────────────────────┘
```

---

## 5. Agent Flow (Detailed)

### Phase 1 — Context Loading (automatic, no approval needed)

1. Load guidebook from `backend/guidebook.md` — rules, command categories, safety constraints
2. Query ChromaDB with ticket title + description → retrieve top-3 similar past incidents with their successful fix strategies
3. Fetch full ticket data from ERP
4. Fetch customer-system SSH credentials from ERP
5. Open SSH connection to target VM

### Phase 2 — System Exploration (automatic)

Agent runs read-only diagnostic commands to understand system state:
- `uname -a`, `uptime`, `df -h`, `free -m` — baseline
- `systemctl list-units --failed` — failed services
- `journalctl -n 100 --no-pager` — recent logs
- `ps aux`, `netstat -tlnp` or `ss -tlnp` — running processes/ports
- Application-specific checks based on ticket content

All reads are logged. No writes at this stage.

### Phase 3 — Bug Reproduction & Verification

Agent attempts to reproduce the reported symptom to confirm:
- Calls the failing service endpoint
- Triggers the error condition
- Confirms the issue still exists (not already resolved)

If issue not reproducible → agent reports this, technician decides whether to continue or close ticket.

### Phase 4 — Fix Planning (automatic, then pauses)

Agent generates a structured fix plan:
```json
{
  "root_cause": "string",
  "fix_strategy": "string",
  "steps": [
    {
      "step": 1,
      "description": "string",
      "command": "string",
      "category": "service_management",
      "risk": "low|medium|high",
      "reversible": true
    }
  ],
  "verification_steps": ["string"]
}
```

Each command is classified into a category (see Section 7).

**→ PAUSE: Send plan to frontend. Wait for technician category approval.**

### Phase 5 — Technician Category Approval

Frontend displays:
- Root cause assessment
- Fix strategy summary
- Commands grouped by category
- Risk level per category

Technician approves or rejects each category. Can also edit individual commands before approving.

Approved categories sent back to agent via WebSocket.

### Phase 6 — Execution (streams to frontend, per-step)

Agent executes only commands whose category was approved:
- Each command: pre-check against safety filter → execute → capture stdout/stderr/exit_code
- Each result streamed to frontend in real time
- Agent evaluates result: success/failure/unexpected
- On failure: agent decides to retry, try alternative, or escalate
- On unexpected output: agent pauses, shows to technician, asks how to proceed

Every step logged with: timestamp, command, category, stdout, stderr, exit_code, agent_assessment (good/bad/why).

### Phase 7 — Fix Verification

After executing fix steps, agent runs verification:
- Repeats the reproduction steps from Phase 3
- Checks service health
- Confirms the symptom is resolved
- Checks for regressions (dependent services still running)

Verification result: pass/fail/partial.

### Phase 8 — Documentation Split (automatic)

From the full session log, agent generates two outputs:

**Output A — ERP Activity** (for grading, concise):
```json
{
  "ticket_id": 7001,
  "start_datetime": "...",
  "end_datetime": "...",
  "summary": "One sentence: what was restored.",
  "root_cause": "Technical root cause, not symptom.",
  "actions_taken": "Diagnosis and fix steps in order.",
  "commands_summary": "Relevant command classes, no secrets.",
  "validation_result": "Concrete proof customer benefit restored."
}
```

**Output B — Memory Entry** (for future incidents, detailed):
```json
{
  "incident_type": "nginx_502_upstream",
  "os": "ubuntu-22.04",
  "services_affected": ["nginx", "node-app"],
  "error_signatures": ["502 Bad Gateway", "upstream connect error"],
  "root_cause": "...",
  "successful_steps": [
    {"description": "...", "command": "...", "result": "..."}
  ],
  "failed_attempts": [
    {"description": "...", "command": "...", "why_failed": "..."}
  ],
  "verification_commands": ["..."],
  "tags": ["networking", "reverse-proxy", "upstream"]
}
```

Memory entry embedded as vector (using ticket description + root cause + tags) and stored in ChromaDB.

**→ PAUSE: Send activity draft to frontend. Wait for technician review and submit.**

### Phase 9 — Submit

Technician reviews and edits the ERP activity draft. On confirm:
- Backend submits `POST /api/v1/activities/create`
- Backend patches ticket status to DONE
- Memory entry saved to ChromaDB
- Session closed

---

## 6. Backend Modules

```
backend/
├── app/
│   ├── main.py              # FastAPI app, route registration, WebSocket endpoint
│   ├── routers/
│   │   ├── tickets.py       # GET /tickets, GET /tickets/{id}
│   │   ├── agent.py         # POST /agent/start, WS /agent/{session_id}/ws
│   │   └── activities.py    # POST /activities/submit
│   ├── agent/
│   │   ├── loop.py          # ReAct loop: observe→think→act
│   │   ├── tools.py         # Tool definitions and registry
│   │   ├── planner.py       # Phase 4: fix plan generation
│   │   ├── executor.py      # Phase 6: approved command execution
│   │   ├── verifier.py      # Phase 7: fix verification
│   │   └── documenter.py    # Phase 8: ERP activity + memory entry generation
│   ├── core/
│   │   ├── llm.py           # LLM abstraction (swap provider via env var)
│   │   ├── erp_client.py    # Phoenix API wrapper
│   │   ├── ssh_runner.py    # paramiko SSH executor
│   │   ├── safety.py        # Command safety filter + category classifier
│   │   ├── memory.py        # ChromaDB wrapper (search + save)
│   │   └── guidebook.py     # Load and serve guidebook.md
│   └── models/
│       ├── ticket.py        # Pydantic models for ticket data
│       ├── plan.py          # Fix plan schema
│       ├── session.py       # Agent session state
│       └── activity.py      # ERP activity schema
├── guidebook.md             # Static rules, categories, safety constraints
├── Dockerfile
└── requirements.txt
```

---

## 7. Command Categories & Safety

### Categories (defined in guidebook.md)

| Category | Examples | Risk |
|---|---|---|
| `read_diagnostics` | `cat`, `ls`, `journalctl`, `df`, `ps`, `ss`, `uname` | None — always auto-approved |
| `service_management` | `systemctl restart/start/stop/status` | Low |
| `process_management` | `kill`, `pkill` | Medium |
| `config_edit` | Edit files in `/etc/`, `/opt/`, `/var/www/` | Medium |
| `package_management` | `apt install/remove`, `pip install` | Medium |
| `network_diagnostics` | `curl`, `ping`, `traceroute`, `nslookup` | Low |
| `file_operations` | `cp`, `mv`, `chmod`, `chown` on app files | Medium |

### Hard-blocked (safety filter, cannot be approved):
- Any `rm -rf /` or `rm -rf` on system paths
- `chmod -R 777` on `/etc`, `/usr`, `/bin`, `/sys`, `/var`
- `systemctl disable ufw/firewalld/auditd`
- `DROP TABLE`, `DROP DATABASE`, database wipes
- Commands that read `/etc/shadow`, `.env` files, private keys
- Running app processes as root to bypass DB permissions

`read_diagnostics` commands are auto-approved — they are read-only and never blocked.

---

## 8. Memory System (ChromaDB)

### Why semantic vector search

Past incidents don't have exact-match symptoms. "nginx returns 502" and "reverse proxy upstream failure" are the same problem phrased differently. Vector search finds semantic similarity, matching the right past fix even with different terminology.

### Implementation

- **Store:** ChromaDB with local file persistence (`./data/chromadb/`)
- **Embedding model:** `all-MiniLM-L6-v2` via `sentence-transformers` (runs locally, no API cost)
- **Document:** concatenation of `incident_type + error_signatures + root_cause + tags`
- **Metadata:** stored alongside vector for structured filtering (OS, services, date)
- **Query:** at Phase 1, embed ticket title+description, retrieve top-3 by cosine similarity

### Retrieval in planning

At Phase 4 (fix planning), the LLM prompt includes retrieved similar past fixes as context:
```
Past similar incident (similarity: 0.87):
  Root cause: Node.js app crashed due to OOM, nginx upstream unreachable
  What worked: Restart node service, increase PM2 memory limit, add health check
  Verification: curl returned 200
```

This gives the agent targeted starting points without flooding the context with full logs.

---

## 9. LLM Abstraction

Single file `core/llm.py` with one function: `chat(messages, tools=None) → response`.

Provider selected by `LLM_PROVIDER` env var:

| Value | Implementation |
|---|---|
| `anthropic` | `anthropic.Anthropic().messages.create()` |
| `openai` | `openai.OpenAI().chat.completions.create()` |
| `azure` | `openai.AzureOpenAI(...)` |
| `ollama` | HTTP POST to `localhost:11434/api/chat` |

Tool definitions translated to provider-specific format inside this layer. Rest of the system never imports an LLM SDK directly.

---

## 10. WebSocket Event Protocol

All real-time communication over `WS /agent/{session_id}/ws`.

### Server → Frontend events

```jsonc
// Agent thinking
{"type": "think", "content": "Checking if nginx service is running..."}

// Agent executing a command
{"type": "act", "tool": "ssh_exec", "command": "systemctl status nginx", "category": "read_diagnostics"}

// Command result
{"type": "result", "exit_code": 0, "stdout": "...", "stderr": "", "assessment": "nginx inactive, needs restart"}

// Agent pausing for approval
{"type": "approval_required", "payload": {"root_cause": "...", "plan": [...], "categories": [...]}}

// Execution progress
{"type": "progress", "step": 2, "total": 5, "description": "Restarting nginx"}

// Verification result
{"type": "verification", "status": "pass", "details": "HTTP 200 from service endpoint"}

// Activity draft ready
{"type": "activity_draft", "payload": {...activity_schema...}}

// Session complete
{"type": "done", "ticket_id": 7001}

// Error
{"type": "error", "message": "...", "recoverable": true}
```

### Frontend → Server events

```jsonc
// Technician approves categories
{"type": "approve_categories", "approved": ["service_management", "config_edit"]}

// Technician rejects a specific command
{"type": "reject_command", "step": 3, "reason": "too risky"}

// Technician submits activity (possibly edited)
{"type": "submit_activity", "payload": {...edited_activity...}}

// Technician aborts
{"type": "abort"}
```

---

## 11. Frontend Screens

### Screen 1 — Ticket List
- Table: ticket ID, title, customer, priority, status, created_at
- Sort by priority / created_at
- Filter by status (OPEN/PENDING/DONE)
- Click row → navigate to Ticket Detail

### Screen 2 — Ticket Detail
- Ticket metadata (title, description, priority, customer)
- Customer system info (IP, OS, notes — no raw SSH creds shown)
- **Start** button → initiates agent session, navigates to Agent View

### Screen 3 — Agent View (live)
Split layout:
- **Left panel:** scrolling event log (think/act/result events streaming in real time)
- **Right panel:** current stage indicator, approval panel when paused

**Approval panel (Phase 4 pause):**
- Root cause summary
- Fix strategy
- Commands grouped by category with risk badges
- Toggle approve/reject per category
- Edit command text before approving (optional)
- Confirm button → sends `approve_categories` event

**Execution phase:**
- Each step shows command + result inline in the log
- Failed steps highlighted in red with agent assessment
- Abort button always visible

### Screen 4 — Activity Review
- Editable fields: summary, root_cause, actions_taken, commands_summary, validation_result
- Read-only: ticket_id, start/end datetime
- Submit button → calls backend → ERP
- Cancel → returns to agent view

---

## 12. Tech Stack Summary

| Layer | Technology | Notes |
|---|---|---|
| Backend | FastAPI 0.115, Python 3.11 | Existing skeleton |
| SSH | paramiko | Add to requirements.txt |
| HTTP client | httpx | For ERP API calls |
| Vector DB | ChromaDB + sentence-transformers | Local file persistence |
| LLM | Provider-agnostic via llm.py | Anthropic/OpenAI/Azure/Ollama |
| Frontend | React 18, TypeScript, Vite | Existing skeleton |
| Styling | TailwindCSS | Add to frontend deps |
| WebSocket | FastAPI WebSocket + browser WebSocket API | Real-time streaming |
| Containers | Docker Compose | Existing config |

---

## 13. What Wins the Competition

**B category (35pts) is won by solving incidents correctly.** The memory system and guidebook are the competitive differentiators — the agent starts each incident with context from similar past fixes rather than from zero. Better starting context → better root cause identification → better fix → more points.

**C category (20pts) is won by discipline.** Every command logged with timestamp + result + assessment. Safety filter hard-blocks dangerous commands. Technician approves every category. `read_diagnostics` auto-approved (no friction for reads). Full audit trail in session log.

**A category (20pts) is won by correct ERP integration.** Complete activity schema, proper auth, graceful error handling (404, empty tickets, auth failure), status PATCH after resolution.
