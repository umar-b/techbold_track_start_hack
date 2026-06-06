# AI Service Desk Autopilot

An AI-assisted technician workspace for the techbold START Hack track. It reads incident
tickets from the Phoenix ERP, connects to a customer's Linux VM over SSH, and — under the
technician's approval on every action — diagnoses, fixes, and validates the fault, then
writes a structured activity record back to the ERP.

## Language

**Ticket**:
A customer's incident report as it exists in the Phoenix ERP. Contains the *symptom only*,
not the cause. Has id, title, description, priority, status (OPEN/PENDING/DONE), customer.
_Avoid_: case, issue (when you mean the ERP record).

**Incident**:
The actual underlying fault on the customer VM that a Ticket reports. One Ticket → one
Incident. The Ticket is the report; the Incident is the real broken thing on the system.
_Avoid_: problem, bug.

**Customer System**:
The SSH-reachable Linux VM that is the troubleshooting target. Fields: ip, port, username,
os, notes. Fetched per-ticket from the ERP. Ubuntu in practice; treated as OS-agnostic.
_Avoid_: server, host, machine (when you mean this specific ERP-supplied target).

**Technician**:
The human operator in the workspace. Holds final authority — approves, edits, rejects,
retries or aborts every action the Agent proposes. Identity derived from the ERP token.
_Avoid_: user, operator.

**Agent**:
The AI that analyses the Ticket + Customer System, proposes diagnostic and fix steps, and
(once approved) executes them over SSH. May be one planning agent or several specialised
ones — the term refers to the AI actor regardless of internal structure.

**Run**:
One troubleshooting session: one Technician working one Ticket against one Customer System,
from analysis through validation to submitted Activity. The unit of state the backend tracks.
_Avoid_: session (flagged below — skeleton routes say `/api/runs`, design doc said "session";
**Run** is canonical).

**Activity**:
The structured documentation record written back to the ERP at the end of a Run. Graded
fields: summary, root_cause (technical cause, not symptom), actions_taken, commands_summary
(no secrets), validation_result. This is the scored deliverable, not a free-text note.
_Avoid_: report, log (those are internal; the Activity is the ERP artefact).

**Audit log**:
The complete internal record of every command and key action in a Run — timestamp, command,
reason, risk, approval state, who approved, stdout/stderr/exit code. Source of truth for
the C (safety) score and the basis from which the Activity is drafted.
_Avoid_: history, trace.

**Guidebook**:
Static markdown of general Linux troubleshooting knowledge (common failure classes) plus
safety rules, loaded into the Agent's context. This — not any database — is what generalises
to fresh, unseen incidents.

**Memory**:
A markdown-graph (Obsidian-style, wiki-linked) of past resolved Incidents — the product's
core differentiator. Each resolved Run writes a **Memory note**; notes link to related notes
to form a navigable graph. On a new Run, relevant notes are retrieved (no embeddings, no DB —
tag/keyword prefilter + graph-link traversal) to **seed a better, faster proposed Plan**.
Invariant: Memory improves the Plan; it never removes an Approval gate. Notes are committed
artefacts → must be secret-free (same rule as an Activity). Not directly scored (incidents are
graded on fresh VMs), but the heart of the build.

**Memory note**:
One markdown file per resolved (or partially-resolved) Incident. Holds: symptom signature,
system context (OS/services), root cause, steps that worked (as **command classes / redacted
forms**, never raw secret-bearing output), attempts that failed + why, verification, tags, and
`[[wiki-links]]` to related notes. **Append-mostly** (new note + new links per Run; old notes
rarely edited). Every note passes the same **sanitizer** as an Activity before it is written —
secrets redacted, no credentials. Edges come from both model-authored links and a shared-tag
backbone. Retrieved by lexical prefilter + 1-hop graph traversal (no embeddings, no DB).

Storage location is configurable (`MEMORY_DIR` / storage backend): committed `backend/memory/`
for the hackathon (shared-brain demo), an external file server in production — same code.

**Plan**:
The Agent's proposed course of action for a Run: a ranked root-cause hypothesis plus an
ordered list of steps, each step being one command with its risk tier, reason, and expected
outcome. The Plan is the unit the Technician approves (not individual commands, not categories).
A Run has at most one *approved* Plan in flight; deviating requires a new Plan and re-approval.

**Approval gate**:
A point where the Run pauses for explicit Technician confirmation. Two gates: (1) approve
connecting to the VM and running read-only diagnostics; (2) approve the fix **Plan** before any
state-changing command runs. Re-planning re-triggers gate 2.

**Risk tier**:
The safety classification of a command, governing whether it needs approval:
- **SAFE** — non-mutating reads; auto-run without approval, always logged. Exception: reading
  secret paths is BLOCKED, not SAFE.
- **GATED** — state-changing; runs only as part of an approved Plan.
- **BLOCKED** — hard-fail commands; never run, cannot be approved.
_Avoid_: "command category" as an approval mechanism — categories are display labels only;
the **risk tier** decides approval.

## Flagged ambiguities

- **Run vs Session** — resolved to **Run** (matches skeleton's `/api/runs`). Do not introduce
  "session" as a separate concept.
- **Memory vs Guidebook** — distinct: Guidebook is static, hand-authored, generalises (on the
  scoring path via the system prompt). Memory is accumulated per-incident notes (off the
  scoring path). Don't conflate them.
