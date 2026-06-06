"""FastAPI backend for the technician workspace.

The browser never receives the ERP token or SSH key. Starting a run performs
safe read-only diagnostics, then waits for the technician to approve a fix plan.
Every command is checked, audited, and redacted before it reaches the UI.

Routes are normal `def` functions because SSH and LLM calls block. FastAPI runs
them in a threadpool, which keeps the event loop safe.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import activity as activity_mod
from . import agent
from . import schemas
from .audit import redact
from .config import settings
from .phoenix_client import PhoenixClient, PhoenixError
from .runstore import store
from .safety import RiskTier, check_command
from .ssh_runner import SSHError, SSHRunner

logging.basicConfig(level=logging.INFO)

_TERMINAL = {"finished", "aborted", "escalated"}

# Analysis converges to a plan: force a plan after the soft limit, escalate at the hard limit.
DIAGNOSE_SOFT_LIMIT = 6
DIAGNOSE_HARD_LIMIT = 10

# --- Phoenix dependency (overridable in tests) ----------------------------- #
_phoenix: Optional[PhoenixClient] = None


def get_phoenix() -> PhoenixClient:
    """Return the shared Phoenix client, with test overrides supported."""

    global _phoenix
    if _phoenix is None:
        _phoenix = PhoenixClient()
    return _phoenix


def _erp(fn, *args, **kwargs):
    """Call Phoenix and turn its errors into API-friendly HTTP errors."""

    try:
        return fn(*args, **kwargs)
    except PhoenixError as exc:
        raise HTTPException(status_code=502, detail=f"ERP error: {exc}")


# --- SSH execution: one reused connection per run (overridable in tests) --- #
# Opening a fresh connection per command causes SSH banner-timeout churn; reuse one
# connection per run and reconnect once if it dropped (also covers an approval wait).
_ssh_cache: Dict[str, SSHRunner] = {}


def _ssh_for(run: Dict[str, Any], system: Dict[str, Any]) -> SSHRunner:
    """Return a reused SSH connection for this run, reconnecting if needed."""

    runner = _ssh_cache.get(run["id"])
    if runner is not None and runner._client is not None:
        return runner
    runner = SSHRunner(host=system.get("ip", ""), port=int(system.get("port") or 22),
                       username=system.get("username"), ticket_id=run["ticket_id"])
    last: Optional[Exception] = None
    for _ in range(2):  # tolerate a transient banner timeout on connect
        try:
            runner.__enter__()
            _ssh_cache[run["id"]] = runner
            return runner
        except SSHError as exc:
            last = exc
    raise last  # type: ignore[misc]


def _close_ssh(run_id: str) -> None:
    """Close and forget the cached SSH connection for a run."""

    runner = _ssh_cache.pop(run_id, None)
    if runner is not None:
        try:
            runner.__exit__()
        except Exception:  # noqa: BLE001
            pass


def _execute(run: Dict[str, Any], system: Dict[str, Any], command: str, timeout=None):
    """Run a command on the run's SSH connection; reconnect once if it dropped."""
    try:
        return _ssh_for(run, system).run(command, timeout=timeout)
    except SSHError:
        _close_ssh(run["id"])
        return _ssh_for(run, system).run(command, timeout=timeout)


# --- run helpers ----------------------------------------------------------- #
def _new_step(run, kind, command="", rationale="", risk=None, status="proposed", expected=""):
    """Append one visible step to the run log."""

    step = {"index": len(run["steps"]), "kind": kind, "command": command,
            "rationale": rationale, "risk": risk.value if risk else None,
            "expected": expected, "status": status, "result": None, "safety_reason": ""}
    run["steps"].append(step)
    return step


def _executed_history(run) -> List[Dict[str, Any]]:
    """Return command results that the agent can use as evidence."""

    out = []
    for s in run["steps"]:
        if s["kind"] in ("diagnose", "fix", "validate") and s["status"] in ("executed", "failed"):
            res = s["result"] or {}
            out.append({"command": s["command"], "stdout": res.get("stdout", ""),
                        "stderr": res.get("stderr", ""), "exit_code": res.get("exit_code")})
    return out


def _run_command(run, system, step, audit) -> bool:
    """Safety-check then execute a step, returning True on exit code 0."""

    verdict = check_command(step["command"])
    step["risk"] = verdict.tier.value
    if verdict.tier is RiskTier.BLOCKED:
        step["status"] = "blocked"
        step["safety_reason"] = verdict.reason
        audit.add("command_blocked", command=step["command"], reason=verdict.reason)
        return False
    audit.add("command_approved", command=step["command"], risk=verdict.tier.value)
    try:
        res = _execute(run, system, step["command"])
    except SSHError as exc:
        step["status"] = "failed"
        step["result"] = {"stdout": "", "stderr": str(exc), "exit_code": None, "duration_ms": None}
        audit.add("command_failed", command=step["command"], error=str(exc))
        return False
    step["result"] = {"stdout": redact(res.stdout), "stderr": redact(res.stderr),
                      "exit_code": res.exit_code, "duration_ms": res.duration_ms}
    step["status"] = "executed" if res.exit_code == 0 else "failed"
    audit.add("command_executed", command=step["command"], exit_code=res.exit_code)
    return res.exit_code == 0


def _set_plan(run, action) -> None:
    """Store the proposed plan and mark the run as waiting for approval."""

    steps = action.get("steps", []) or []
    for st in steps:
        st["risk"] = check_command(st.get("command", "")).tier.value
    run["plan"] = {"root_cause": action.get("root_cause", ""), "steps": steps,
                   "validation": action.get("validation", []) or []}
    run["status"] = "awaiting_plan_approval"


def _escalate(run, reason: str) -> None:
    """Stop automation and hand the ticket back to the technician."""

    _new_step(run, "finish", rationale=f"Escalated to technician: {reason}", status="done")
    run["status"] = "escalated"
    store.audit(run["id"]).add("escalated", reason=reason)
    _close_ssh(run["id"])


def _analyze(run, ticket, system) -> None:
    """Run read-only diagnostics until the agent can propose a plan."""

    audit = store.audit(run["id"])
    run["status"] = "analyzing"
    while True:
        diagnostics = sum(1 for s in run["steps"] if s["kind"] == "diagnose" and s["status"] == "executed")
        if diagnostics >= DIAGNOSE_HARD_LIMIT:
            _escalate(run, "could not converge on a plan after diagnostics")
            return
        must_plan = diagnostics >= DIAGNOSE_SOFT_LIMIT
        action = agent.propose_action(ticket, system, _executed_history(run), must_plan=must_plan)
        kind = action.get("action")
        if kind == "plan":
            _set_plan(run, action)
            audit.add("plan_proposed", root_cause=run["plan"]["root_cause"], steps=len(run["plan"]["steps"]))
            return
        if kind == "finish":
            _new_step(run, "finish", rationale=action.get("summary", "System already healthy; no change needed."),
                      status="done")
            run["status"] = "finished"
            audit.add("agent_reports_resolved", summary=action.get("summary", ""))
            _close_ssh(run["id"])
            return
        # diagnose — read-only only
        cmd = action.get("command", "")
        verdict = check_command(cmd)
        step = _new_step(run, "diagnose", cmd, action.get("rationale", ""), risk=verdict.tier)
        if verdict.tier is RiskTier.SAFE:
            _run_command(run, system, step, audit)
            continue
        step["status"] = "rejected"
        step["safety_reason"] = verdict.reason
        audit.add("nonread_diagnostic_rejected", command=cmd, risk=verdict.tier.value)
        if must_plan:
            _escalate(run, "agent did not produce a valid plan")
            return


def _execute_and_verify(run, ticket, system, edited_steps=None) -> None:
    """Run the approved plan once, validate it, then finish or ask for a new plan."""

    audit = store.audit(run["id"])
    plan = run["plan"] or {}
    steps = edited_steps if edited_steps is not None else plan.get("steps", [])
    validation = plan.get("validation", []) or []
    run["status"] = "executing"
    audit.add("plan_approved", steps=len(steps))
    fixes_ok = True
    for st in steps:
        step = _new_step(run, "fix", st.get("command", ""), st.get("rationale", ""),
                         expected=st.get("expected", ""))
        fixes_ok = _run_command(run, system, step, audit) and fixes_ok
    run["status"] = "verifying"
    validation_ok = True
    for vc in validation:
        step = _new_step(run, "validate", vc, "Validate the fix")
        validation_ok = _run_command(run, system, step, audit) and validation_ok
    run["plan"] = None
    verdict = validation_ok if validation else fixes_ok
    if verdict:
        run["status"] = "finished"
        audit.add("verified_resolved")
        _close_ssh(run["id"])
    else:
        audit.add("verification_failed")
        _replan(run, ticket, system)


def _replan(run, ticket, system) -> None:
    """Ask the agent for a new plan after rejection or failed validation."""

    run["status"] = "analyzing"
    action = agent.propose_action(ticket, system, _executed_history(run), must_plan=True)
    if action.get("action") == "plan":
        _set_plan(run, action)
        store.audit(run["id"]).add("replan_proposed", root_cause=run["plan"]["root_cause"],
                                   steps=len(run["plan"]["steps"]))
    else:
        _escalate(run, "could not form a new plan after a failed attempt")


# --- app ------------------------------------------------------------------- #
def create_app() -> FastAPI:
    """Build the FastAPI app and register all technician workflow routes."""

    app = FastAPI(title="AI Service Desk Autopilot — Team Backend", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    def health():
        """Simple health check used by Docker, smoke tests, and humans."""

        return {"status": "ok"}

    @app.get("/api/me")
    def me(phoenix: PhoenixClient = Depends(get_phoenix)):
        """Proxy the logged-in technician/team identity from Phoenix."""

        return _erp(phoenix.me)

    @app.get("/api/tickets")
    def tickets(status: Optional[str] = None, priority: Optional[str] = None,
                sort: str = "date", phoenix: PhoenixClient = Depends(get_phoenix)):
        """List the team's tickets for the ticket overview screen."""

        return _erp(phoenix.list_tickets, status, priority, sort)

    @app.get("/api/tickets/{ticket_id}")
    def ticket_detail(ticket_id: int, phoenix: PhoenixClient = Depends(get_phoenix)):
        """Load ticket text and the customer system needed for SSH."""

        return {"ticket": _erp(phoenix.get_ticket, ticket_id),
                "system": _erp(phoenix.customer_system, ticket_id)}

    @app.post("/api/runs")
    def start_run(body: schemas.StartRunIn, phoenix: PhoenixClient = Depends(get_phoenix)):
        """Start analysis for one ticket and stop at the first approval gate."""

        ticket = _erp(phoenix.get_ticket, body.ticket_id)
        system = _erp(phoenix.customer_system, body.ticket_id).get("system", {})
        run = store.create(body.ticket_id)
        store.audit(run["id"]).add("run_started", ticket_id=body.ticket_id,
                                   ticket_title=ticket.get("title", ""))
        _erp(phoenix.set_status, body.ticket_id, "PENDING")
        _analyze(run, ticket, system)
        return run

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        """Return the latest run state for polling or refresh."""

        run = store.get(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        return run

    @app.post("/api/runs/{run_id}/approve")
    def approve(run_id: str, body: schemas.ApproveIn = Body(default=schemas.ApproveIn()),
                phoenix: PhoenixClient = Depends(get_phoenix)):
        """Approve the current plan and run its commands behind safety checks."""

        run = store.get(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        if run["status"] != "awaiting_plan_approval":
            raise HTTPException(409, f"Nothing to approve (status={run['status']})")
        ticket = _erp(phoenix.get_ticket, run["ticket_id"])
        system = _erp(phoenix.customer_system, run["ticket_id"]).get("system", {})
        steps = [s.model_dump() for s in body.steps] if body.steps is not None else None
        _execute_and_verify(run, ticket, system, edited_steps=steps)
        return run

    @app.post("/api/runs/{run_id}/reject")
    def reject(run_id: str, phoenix: PhoenixClient = Depends(get_phoenix)):
        """Reject the current plan and ask the agent for a different one."""

        run = store.get(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        ticket = _erp(phoenix.get_ticket, run["ticket_id"])
        system = _erp(phoenix.customer_system, run["ticket_id"]).get("system", {})
        run["plan"] = None
        store.audit(run_id).add("plan_rejected")
        _replan(run, ticket, system)
        return run

    @app.post("/api/runs/{run_id}/abort")
    def abort(run_id: str):
        """Let the technician stop a run before more commands execute."""

        run = store.get(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        run["status"] = "aborted"
        store.audit(run_id).add("run_aborted")
        _close_ssh(run_id)
        return run

    @app.get("/api/runs/{run_id}/activity-draft")
    def activity_draft(run_id: str, phoenix: PhoenixClient = Depends(get_phoenix)):
        """Draft the ERP activity from commands that actually ran."""

        run = store.get(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        ticket = _erp(phoenix.get_ticket, run["ticket_id"])
        return activity_mod.draft_activity(ticket, _executed_history(run))

    @app.post("/api/runs/{run_id}/submit-activity")
    def submit_activity(run_id: str, body: schemas.SubmitActivityIn,
                        phoenix: PhoenixClient = Depends(get_phoenix)):
        """Write the reviewed activity back to Phoenix and optionally close the ticket."""

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
        audit.add("activity_submitted", ticket_id=run["ticket_id"])
        return {"activity": created, "run": run}

    @app.get("/api/runs/{run_id}/events")
    def events(run_id: str):
        """Stream run status and new steps to the UI while work is happening."""

        def gen():
            """Yield server-sent events until the run reaches a terminal state."""

            last = 0
            for _ in range(600):
                run = store.get(run_id)
                if not run:
                    break
                steps = run["steps"]
                while last < len(steps):
                    yield f"data: {json.dumps({'type': 'step', 'step': steps[last]})}\n\n"
                    last += 1
                yield f"data: {json.dumps({'type': 'status', 'status': run['status']})}\n\n"
                if run["status"] in _TERMINAL:
                    break
                time.sleep(0.5)
        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


app = create_app()
