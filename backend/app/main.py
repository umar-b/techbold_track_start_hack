"""FastAPI backend — technician workspace API + the human-in-the-loop run loop.

The ERP token and SSH key live only here, never in the browser. Starting a run or
approving a plan returns immediately and advances the run on a background worker
(ADR-0008): SAFE diagnostics auto-run until a gate, GATED steps run only inside an
approved plan, and a BLOCKED command never runs. Progress streams to the browser
over SSE (steps, status, and the proposed plan). Every action is audited and redacted.

Handlers are sync `def` (FastAPI runs them in a threadpool); the blocking SSH/LLM
run loop is dispatched to a worker thread so the handler never blocks on it.
"""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import activity as activity_mod
from . import agent
from . import memory as memory_mod
from . import schemas
from .audit import redact
from .config import settings
from .phoenix_client import PhoenixClient, PhoenixError
from .runstate import RunStatus, is_terminal, transition
from .runstore import store
from .safety import RiskTier, check_command
from .ssh_runner import SSHError

logging.basicConfig(level=logging.INFO)

# Analysis converges to a plan: force a plan after the soft limit, escalate at the hard limit.
DIAGNOSE_SOFT_LIMIT = 6
DIAGNOSE_HARD_LIMIT = 10
# After this many diagnostics are REJECTED (proposed but not read-only), stop asking for
# another diagnostic and force a plan — otherwise the agent re-proposes the same GATED command
# (e.g. the validation script) every iteration until the hard limit, doing no useful work.
REJECTED_DIAGNOSE_LIMIT = 2

# The run loop advances on a background worker so POST handlers return immediately and
# the browser sees diagnostics stream in over SSE (ADR-0008). `_submit` is overridden to
# run inline in tests.
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="runloop")


def _guarded(fn, *args) -> None:
    """Run one run-loop phase: skip if already aborted, escalate on an unexpected error,
    and always close the SSH session once the run is terminal."""
    run = args[0]
    try:
        if is_terminal(run["status"]):  # aborted before the worker picked it up
            return
        fn(*args)
    except Exception:  # noqa: BLE001
        if is_terminal(run["status"]):
            return  # an abort raced the loop (e.g. an illegal transition) — not an error
        logging.getLogger("api").exception("run loop failed run_id=%s status=%s",
                                           run.get("id"), run.get("status"))
        try:
            _escalate(run, "internal error in the run loop")
        except Exception:  # noqa: BLE001
            pass
    finally:
        _close_if_terminal(run)


def _submit(fn, *args) -> None:
    try:
        _executor.submit(_guarded, fn, *args)
    except RuntimeError:  # executor rejected/shut down — don't strand the run mid-phase
        run = args[0]
        logging.getLogger("api").exception("could not schedule run loop run_id=%s", run.get("id"))
        try:
            if not is_terminal(run["status"]):
                _escalate(run, "could not schedule the run loop")
        except Exception:  # noqa: BLE001
            pass
        _close_if_terminal(run)

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


# --- SSH execution: the run's reused connection lives in the store (overridable in tests) --- #
def _execute(run: Dict[str, Any], system: Dict[str, Any], command: str, timeout=None):
    """Run a command on the run's reused SSH connection; reconnect once if it dropped.

    Reusing one connection per run avoids the banner-timeout churn of opening a
    fresh connection per command; the session is owned by the store and survives
    an approval wait. Connection lifecycle (connect-retry, liveness) lives in the
    SSHRunner; this only adds reconnect-once on a dropped channel.
    """
    with store.lock(run["id"]):  # block a concurrent abort from closing the session mid-command
        try:
            return store.session(run, system).run(command, timeout=timeout)
        except SSHError:
            store.close_session(run["id"])
            return store.session(run, system).run(command, timeout=timeout)


def _close_if_terminal(run: Dict[str, Any]) -> None:
    """Close the run's SSH session once it reaches a terminal status.

    The single cleanup site; the per-run lock makes it wait for any in-flight command
    so abort (on another thread) never closes the transport mid-exec.
    """
    if is_terminal(run["status"]):
        with store.lock(run["id"]):
            store.close_session(run["id"])


# --- run helpers ----------------------------------------------------------- #
def _new_step(run, kind, command="", rationale="", risk=None, status="proposed", expected=""):
    step = {"index": len(run["steps"]), "kind": kind, "command": command,
            "rationale": rationale, "risk": risk.value if risk else None,
            "expected": expected, "status": status, "result": None, "safety_reason": ""}
    run["steps"].append(step)
    return step


def _executed_history(run) -> List[Dict[str, Any]]:
    out = []
    for s in run["steps"]:
        if s["kind"] in ("diagnose", "fix", "validate") and s["status"] in ("executed", "failed"):
            res = s["result"] or {}
            out.append({"command": s["command"], "stdout": res.get("stdout", ""),
                        "stderr": res.get("stderr", ""), "exit_code": res.get("exit_code")})
    return out


def _run_command(run, system, step, audit) -> bool:
    """Safety-check then execute a step. Returns True on exit_code 0."""
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
    steps = action.get("steps", []) or []
    for st in steps:
        st["risk"] = check_command(st.get("command", "")).tier.value
    # Transition first: if an abort raced analysis this raises and leaves plan untouched
    # (a terminal run must never carry a stale plan).
    transition(run, RunStatus.AWAITING_PLAN_APPROVAL)
    run["plan"] = {"root_cause": action.get("root_cause", ""), "steps": steps,
                   "validation": action.get("validation", []) or []}


def _escalate(run, reason: str) -> None:
    _new_step(run, "finish", rationale=f"Escalated to technician: {reason}", status="done")
    transition(run, RunStatus.ESCALATED)
    store.audit(run["id"]).add("escalated", reason=reason)


def _analyze(run, ticket, system, mem: str = "") -> None:
    """Analysis phase: run read-only diagnostics, then converge to a Plan (forced after a
    soft limit, escalate at the hard limit). Diagnostics are read-only only; a mutating
    "diagnostic" is rejected — fixes belong in a Plan the technician approves."""
    audit = store.audit(run["id"])
    transition(run, RunStatus.ANALYZING)
    while True:
        if is_terminal(run["status"]):  # aborted during analysis
            return
        executed = sum(1 for s in run["steps"] if s["kind"] == "diagnose" and s["status"] == "executed")
        attempts = sum(1 for s in run["steps"] if s["kind"] == "diagnose")
        rejected = [s for s in run["steps"] if s["kind"] == "diagnose" and s["status"] == "rejected"]
        # Bound by TOTAL diagnostic attempts so an unreachable host (every diagnostic
        # failing, never "executed") still terminates instead of looping forever.
        if attempts >= DIAGNOSE_HARD_LIMIT:
            _escalate(run, "could not converge on a plan after diagnostics")
            return
        # Force a plan once we have enough evidence OR the agent keeps proposing non-read-only
        # "diagnostics": repeated rejections mean it wants to change state, which belongs in a
        # plan — not in a diagnose step re-proposed forever.
        must_plan = executed >= DIAGNOSE_SOFT_LIMIT or len(rejected) >= REJECTED_DIAGNOSE_LIMIT
        action = agent.propose_action(ticket, system, _executed_history(run), memory=mem,
                                      must_plan=must_plan, rejected=rejected)
        kind = action.get("action")
        if kind == "plan":
            _set_plan(run, action)
            audit.add("plan_proposed", root_cause=run["plan"]["root_cause"], steps=len(run["plan"]["steps"]))
            return
        if kind == "finish":
            executed_any = any(s["kind"] == "diagnose" and s["status"] == "executed" for s in run["steps"])
            attempted_any = any(s["kind"] == "diagnose" for s in run["steps"])
            if attempted_any and not executed_any:
                # Every diagnostic failed (e.g. host unreachable) — can't claim "resolved".
                _escalate(run, "could not gather any evidence — handing to the technician")
                return
            _new_step(run, "finish", rationale=action.get("summary", "System already healthy; no change needed."),
                      status="done")
            transition(run, RunStatus.FINISHED)
            audit.add("agent_reports_resolved", summary=action.get("summary", ""))
            return
        # diagnose — read-only only
        cmd = action.get("command", "")
        verdict = check_command(cmd)
        step = _new_step(run, "diagnose", cmd, action.get("rationale", ""), risk=verdict.tier)
        if verdict.tier is RiskTier.SAFE:
            _run_command(run, system, step, audit)
            # An SSH transport failure (could not connect / load the key) is recorded as a
            # "failed" step with exit_code None — distinct from a command that ran and exited
            # non-zero. The connection won't heal on its own, so every further diagnostic would
            # fail identically: escalate now with the cause instead of looping to the hard limit.
            res = step.get("result") or {}
            if step["status"] == "failed" and res.get("exit_code") is None:
                _escalate(run, f"cannot reach the customer VM — {res.get('stderr') or 'SSH error'}")
                return
            continue
        step["status"] = "rejected"
        step["safety_reason"] = verdict.reason
        audit.add("nonread_diagnostic_rejected", command=cmd, risk=verdict.tier.value)
        if must_plan:
            _escalate(run, "agent did not produce a valid plan")
            return


def _execute_and_verify(run, ticket, system, edited_steps=None) -> None:
    """Apply the WHOLE approved plan once (no mid-execution re-planning), then verify.
    Verified -> finished (the technician then documents/submits). Not verified -> the agent
    forms a NEW plan for the technician to approve (the only loop, and it is human-gated)."""
    audit = store.audit(run["id"])
    plan = run["plan"] or {}
    steps = edited_steps if edited_steps is not None else plan.get("steps", [])
    validation = plan.get("validation", []) or []
    transition(run, RunStatus.EXECUTING)
    audit.add("plan_approved", steps=len(steps))
    fixes_ok = True
    for st in steps:
        if is_terminal(run["status"]):  # aborted mid-execution
            return
        step = _new_step(run, "fix", st.get("command", ""), st.get("rationale", ""),
                         expected=st.get("expected", ""))
        fixes_ok = _run_command(run, system, step, audit) and fixes_ok
    if is_terminal(run["status"]):
        return
    transition(run, RunStatus.VERIFYING)
    validation_ok = True
    for vc in validation:
        if is_terminal(run["status"]):
            return
        step = _new_step(run, "validate", vc, "Validate the fix")
        validation_ok = _run_command(run, system, step, audit) and validation_ok
    run["plan"] = None
    verdict = validation_ok if validation else fixes_ok
    if verdict:
        transition(run, RunStatus.FINISHED)
        audit.add("verified_resolved")
    else:
        audit.add("verification_failed")
        _replan(run, ticket, system)


def _replan(run, ticket, system) -> None:
    """After a failed/rejected plan, the agent forms a NEW plan for the technician to approve."""
    transition(run, RunStatus.ANALYZING)
    mem = memory_mod.retrieve(ticket, system)
    action = agent.propose_action(ticket, system, _executed_history(run), memory=mem, must_plan=True)
    if action.get("action") == "plan":
        _set_plan(run, action)
        store.audit(run["id"]).add("replan_proposed", root_cause=run["plan"]["root_cause"],
                                   steps=len(run["plan"]["steps"]))
    else:
        _escalate(run, "could not form a new plan after a failed attempt")


# --- app ------------------------------------------------------------------- #
def create_app() -> FastAPI:
    app = FastAPI(title="AI Service Desk Autopilot — Team Backend", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.on_event("shutdown")
    def _shutdown():
        _executor.shutdown(cancel_futures=True)

    @app.get("/health")
    def health():
        return {"status": "ok"}

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
        _submit(_analyze, run, ticket, system, memory_mod.retrieve(ticket, system))
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
        _submit(_execute_and_verify, run, ticket, system, steps)
        return run

    @app.post("/api/runs/{run_id}/reject")
    def reject(run_id: str, phoenix: PhoenixClient = Depends(get_phoenix)):
        run = store.get(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        if run["status"] != "awaiting_plan_approval":
            raise HTTPException(409, f"Nothing to reject (status={run['status']})")
        ticket = _erp(phoenix.get_ticket, run["ticket_id"])
        system = _erp(phoenix.customer_system, run["ticket_id"]).get("system", {})
        store.audit(run_id).add("plan_rejected")
        transition(run, RunStatus.ANALYZING)
        run["plan"] = None
        _submit(_replan, run, ticket, system)
        return run

    @app.post("/api/runs/{run_id}/abort")
    def abort(run_id: str):
        run = store.get(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        if not is_terminal(run["status"]):
            transition(run, RunStatus.ABORTED)
            store.audit(run_id).add("run_aborted")
        _close_if_terminal(run)
        return run

    @app.get("/api/runs/{run_id}/activity-draft")
    def activity_draft(run_id: str, phoenix: PhoenixClient = Depends(get_phoenix)):
        run = store.get(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        ticket = _erp(phoenix.get_ticket, run["ticket_id"])
        return activity_mod.draft_activity(ticket, _executed_history(run))

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
