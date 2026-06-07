# Improvement Roadmap

Work tracked on branch `feat/optimize-and-enhance`. Baseline at start: **133 backend
tests green, frontend `tsc` clean** (commit `19b3123`). Every item below lands as its
own commit with the test suite green between commits, so the working demo is never at
risk. Additive, behaviour-preserving work is done first; the one structural refactor is
done last and is guarded by the existing run-orchestration tests.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done

---

## Phase 1 — Frontend nice-to-haves (highest demo value, fully additive)

The run view captures `duration_ms` per step but never shows it; there is no command
copy affordance, no live connection signal, no run timer, and the ticket list only
sorts. These are all client-only and cannot affect backend behaviour.

- [ ] **Step timing + copy command.** Render `result.duration_ms` as a right-aligned
  `· 142 ms` on each executed step; add a copy-to-clipboard button on every command
  block (`useClipboard` hook). Signals precision (brand: *precise, trustworthy*).
- [ ] **SSE connection indicator.** Surface the live/reconnecting/closed state of the
  `EventSource` from `useRun` and show a small status dot in the chat header. Reassures
  the technician the live stream is healthy during a long execute phase.
- [ ] **Run elapsed timer.** A monotonic `mm:ss` since run start in the chat sidebar,
  frozen on a terminal status. Reduced-motion safe (text, not animation).
- [ ] **Ticket list search + filters.** A search box (id / title / customer) and
  status + priority filters layered over the existing sort, computed client-side from
  the already-fetched list. Empty-filter state handled.
- [ ] **Keyboard shortcuts.** `A` approve · `R` reject · `Esc` abort while awaiting a
  plan, with a visible hint row. Ignored while typing in an input/textarea.
- [ ] **Toasts.** Lightweight, accessible (`role="status"`) toast feedback for
  approve/reject/abort/errors. No new dependency — a tiny portal-based component.

## Phase 2 — Backend additive features (no behaviour change to the run loop)

- [ ] **`GET /api/runs` + `GET /api/stats`.** Expose `store.all()` as a runs list
  (id, ticket, status, step count, created_at) and a status-count summary. Powers a
  future operations view and makes the in-memory state inspectable. Read-only.
- [ ] **Idle SSH session reaper.** Resolve the standing TODO in `runstore.py`: a run
  parked at `awaiting_plan_approval` holds its TCP connection until process exit. Track
  `last_used` per session and evict sessions idle past a TTL via a daemon sweeper started
  in the app lifespan. Bounded, opportunistic, fully tested.

## Phase 3 — Architecture refactor (behaviour-preserving, tests-guarded)

- [ ] **Extract the orchestrator.** `main.py` is ~470 lines mixing the FastAPI routers
  with the whole `analyze → execute → verify → replan` run loop. The project's own
  FastAPI rule says *keep routers thin; move business behaviour into services*. Move the
  loop (`_analyze`, `_execute_and_verify`, `_replan`, `_run_command`, `_execute`,
  `_escalate`, history/plan helpers) into `app/orchestrator.py`, leaving `main.py` as
  thin handlers. No behaviour change — `test_runs.py` and friends must stay green
  unchanged. Done last because it is the only change that touches the hot path.

## Phase 4 — Verification & docs

- [ ] Full `pytest` + new tests for Phase 2 endpoints and the reaper.
- [ ] Frontend `tsc --noEmit` clean.
- [ ] `code-reviewer` subagent pass on the diff; fix CRITICAL/HIGH.
- [ ] Update `README.md` (new endpoints, UX features) and the architecture doc.

---

## Explicitly out of scope (deliberate non-goals)

- **Persisting run state to a DB.** ADR-0008 keeps run control in-memory for the
  single-process demo; the audit log is already file-backed. Changing this is a
  product decision, not a tidy-up.
- **Wiring embeddings / vector recall.** ADR-0001 chose a markdown memory graph on
  purpose. Out of scope unless asked.
- **Dark mode / theme switch.** `PRODUCT.md` explicitly warns off defaulting to dark.
- **Replacing the SSE poll with push.** The 0.5 s poll is adequate for the demo and a
  push rewrite carries reconnection-correctness risk for little visible gain.
</content>
</invoke>
