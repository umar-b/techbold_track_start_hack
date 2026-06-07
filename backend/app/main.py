"""FastAPI backend — technician workspace API.

The ERP token and SSH key live only here, never in the browser. The HTTP handlers
stay thin: they validate input, talk to the Phoenix ERP, and hand the run off to
the orchestrator (`app/orchestrator.py`), which advances it on a background worker
(ADR-0008). Progress streams to the browser over SSE; every action is audited and
redacted.

Handlers are sync `def` (FastAPI runs them in a threadpool); the blocking SSH/LLM
run loop is dispatched to a worker thread so the handler never blocks on it.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, Optional

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import activity as activity_mod
from . import memory as memory_mod
from . import orchestrator as orch
from . import schemas
from .audit import redact
from .config import settings
from .phoenix_client import PhoenixClient, PhoenixError
from .runstate import RunStatus, is_terminal, transition
from .runstore import store

logging.basicConfig(level=logging.INFO)


# --- Phoenix dependency (overridable in tests) ----------------------------- #
_phoenix: Optional[PhoenixClient] = None


def get_phoenix() -> PhoenixClient:
    global _phoenix
    if _phoenix is None:
        _phoenix = PhoenixClient()
    return _phoenix


def _erp(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except PhoenixError as exc:
        raise HTTPException(status_code=502, detail=f"ERP error: {exc}")


# --- app ------------------------------------------------------------------- #
def create_app() -> FastAPI:
    app = FastAPI(title="AI Service Desk Autopilot — Team Backend", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.on_event("startup")
    def _startup():
        if settings.SSH_SESSION_IDLE_TTL > 0 and settings.SSH_SESSION_REAP_INTERVAL > 0:
            orch._reaper_stop.clear()
            threading.Thread(target=orch._reaper_loop, name="ssh-session-reaper", daemon=True).start()

    @app.on_event("shutdown")
    def _shutdown():
        orch._reaper_stop.set()
        orch._executor.shutdown(cancel_futures=True)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/runs")
    def list_runs():
        """A compact list of all runs this process knows about (in-memory, ADR-0008)."""
        return [{"id": r["id"], "ticket_id": r["ticket_id"], "status": r["status"],
                 "steps": len(r["steps"]), "created_at": r["created_at"]}
                for r in store.all()]

    @app.get("/api/stats")
    def stats():
        """Run counts by status + live SSH-session count, for an operations view."""
        return store.summary()

    @app.get("/api/me")
    def me(phoenix: PhoenixClient = Depends(get_phoenix)):
        return _erp(phoenix.me)

    @app.get("/api/tickets")
    def tickets(status: Optional[str] = None, priority: Optional[str] = None,
                sort: str = "date", phoenix: PhoenixClient = Depends(get_phoenix)):
        return _erp(phoenix.list_tickets, status, priority, sort)

    @app.get("/api/tickets/{ticket_id}")
    def ticket_detail(ticket_id: int, phoenix: PhoenixClient = Depends(get_phoenix)):
        return {"ticket": _erp(phoenix.get_ticket, ticket_id),
                "system": _erp(phoenix.customer_system, ticket_id)}

    @app.post("/api/runs")
    def start_run(body: schemas.StartRunIn, phoenix: PhoenixClient = Depends(get_phoenix)):
        active = next((r for r in store.all()
                       if r["ticket_id"] == body.ticket_id and not is_terminal(r["status"])), None)
        if active is not None:  # one active run per ticket — never two workers on one VM
            raise HTTPException(409, f"A run is already active for ticket {body.ticket_id}")
        ticket = _erp(phoenix.get_ticket, body.ticket_id)
        system = _erp(phoenix.customer_system, body.ticket_id).get("system", {})
        run = store.create(body.ticket_id)
        store.audit(run["id"]).add("run_started", ticket_id=body.ticket_id,
                                   ticket_title=ticket.get("title", ""))
        _erp(phoenix.set_status, body.ticket_id, "PENDING")
        transition(run, RunStatus.ANALYZING)  # immediate feedback; the worker takes over
        orch._submit(orch._analyze, run, ticket, system, memory_mod.retrieve(ticket, system))
        return run

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        run = store.get(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        return run

    @app.post("/api/runs/{run_id}/approve")
    def approve(run_id: str, body: schemas.ApproveIn = Body(default=schemas.ApproveIn()),
                phoenix: PhoenixClient = Depends(get_phoenix)):
        run = store.get(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        if run["status"] != "awaiting_plan_approval":
            raise HTTPException(409, f"Nothing to approve (status={run['status']})")
        ticket = _erp(phoenix.get_ticket, run["ticket_id"])
        system = _erp(phoenix.customer_system, run["ticket_id"]).get("system", {})
        steps = [s.model_dump() for s in body.steps] if body.steps is not None else None
        transition(run, RunStatus.EXECUTING)
        orch._submit(orch._execute_and_verify, run, ticket, system, steps)
        return run

    @app.post("/api/runs/{run_id}/reject")
    def reject(run_id: str, body: schemas.RejectIn = Body(default=schemas.RejectIn()),
               phoenix: PhoenixClient = Depends(get_phoenix)):
        run = store.get(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        if run["status"] != "awaiting_plan_approval":
            raise HTTPException(409, f"Nothing to reject (status={run['status']})")
        ticket = _erp(phoenix.get_ticket, run["ticket_id"])
        system = _erp(phoenix.customer_system, run["ticket_id"]).get("system", {})
        # Cap length before it reaches the LLM prompt — bounds the prompt-injection
        # surface from this free-text field (the safety layer re-checks every command).
        feedback = (body.feedback or "").strip()[:1000]
        store.audit(run_id).add("plan_rejected", feedback=feedback)
        transition(run, RunStatus.ANALYZING)
        run["plan"] = None
        orch._submit(orch._replan, run, ticket, system, feedback)
        return run

    @app.post("/api/runs/{run_id}/abort")
    def abort(run_id: str):
        run = store.get(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        if not is_terminal(run["status"]):
            transition(run, RunStatus.ABORTED)
            store.audit(run_id).add("run_aborted")
        orch._close_if_terminal(run)
        return run

    @app.get("/api/runs/{run_id}/audit")
    def audit_trail(run_id: str):
        """The append-only, already-redacted audit trail for a run (ADR-0004).

        Surfaces the canonical record the UI can show alongside the step log —
        including events steps don't carry (plan_proposed/approved, escalated,
        activity_submitted). Read-only; entries are immutable.
        """
        run = store.get(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        return {"run_id": run_id, "entries": store.audit(run_id).entries}

    @app.get("/api/runs/{run_id}/activity-draft")
    def activity_draft(run_id: str, phoenix: PhoenixClient = Depends(get_phoenix)):
        run = store.get(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        ticket = _erp(phoenix.get_ticket, run["ticket_id"])
        return activity_mod.draft_activity(ticket, orch._executed_history(run))

    @app.post("/api/runs/{run_id}/submit-activity")
    def submit_activity(run_id: str, body: schemas.SubmitActivityIn,
                        phoenix: PhoenixClient = Depends(get_phoenix)):
        run = store.get(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        audit = store.audit(run_id)
        end = audit.entries[-1]["ts"] if audit.entries else run["created_at"]
        payload = {
            "ticket_id": run["ticket_id"],
            "start_datetime": run["created_at"],
            "end_datetime": end,
            "description": redact(body.summary),
            "summary": redact(body.summary),
            "root_cause": redact(body.root_cause),
            "actions_taken": redact(body.actions_taken),
            "commands_summary": redact(body.commands_summary),
            "validation_result": redact(body.validation_result),
        }
        created = _erp(phoenix.create_activity, payload)
        if body.set_done:
            _erp(phoenix.set_status, run["ticket_id"], "DONE")
        # Append a sanitized memory note (ADR-0001). Must never break the submit.
        note_path = None
        try:
            ticket = phoenix.get_ticket(run["ticket_id"])
            system = phoenix.customer_system(run["ticket_id"]).get("system", {})
            note_path = memory_mod.write_note(run, ticket, payload, system)
        except Exception:  # noqa: BLE001
            logging.getLogger("api").warning("memory note skipped after submit", exc_info=True)
            note_path = None
        audit.add("activity_submitted", ticket_id=run["ticket_id"], memory_note=bool(note_path))
        return {"activity": created, "run": run}

    @app.get("/api/runs/{run_id}/events")
    def events(run_id: str):
        def gen():
            sent_steps: Dict[int, str] = {}
            plan_sent = False
            for _ in range(1800):  # ~15 min keep-alive; the browser auto-reconnects past it
                run = store.get(run_id)
                if not run:
                    break
                steps = run["steps"]
                # Re-emit a step whenever its payload changes (proposed -> executed + output),
                # since the worker mutates a step in place after appending it.
                for i in range(len(steps)):
                    payload = json.dumps({"type": "step", "step": steps[i]})
                    if sent_steps.get(i) != payload:
                        sent_steps[i] = payload
                        yield f"data: {payload}\n\n"
                plan = run.get("plan")
                if plan and not plan_sent:  # the proposed plan isn't carried by step events
                    yield f"data: {json.dumps({'type': 'plan', 'plan': plan})}\n\n"
                    plan_sent = True
                elif not plan and plan_sent:  # explicitly clear it (execute / before a replan)
                    yield f"data: {json.dumps({'type': 'plan', 'plan': None})}\n\n"
                    plan_sent = False
                yield f"data: {json.dumps({'type': 'status', 'status': run['status']})}\n\n"
                if is_terminal(run["status"]):
                    break
                time.sleep(0.5)
        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


app = create_app()
