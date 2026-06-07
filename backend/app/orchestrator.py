"""Run-loop orchestration — the deterministic analyze→approve→apply→verify→replan flow.

Extracted from the API layer so the FastAPI handlers stay thin (the project's
FastAPI rule: keep routers thin, move business behaviour into a service). The
HTTP handlers in `main.py` validate input, talk to the ERP, and then hand off to
the functions here, which advance a run on a background worker (ADR-0008): SAFE
diagnostics auto-run until a gate, GATED steps run only inside an approved plan,
and a BLOCKED command never runs. Every action is audited and redacted.

Behaviour is identical to the previous in-`main` implementation; this module only
concentrates the loop and its helpers (the SSH-exec, scheduler, and step/plan
seams that the tests patch live here now).
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from . import activity as activity_mod  # noqa: F401  (kept for parity / future use)
from . import agent
from . import memory as memory_mod
from . import runlog
from .audit import redact
from .config import settings
from .runstate import RunStatus, is_terminal, transition
from .runstore import store
from .safety import RiskTier, check_command
from .ssh_runner import SSHError

log = logging.getLogger("api")

# Analysis converges to a plan in stages:
#   SOFT  — start telling the model "you have enough evidence, plan now"; it may still run a
#           couple more read-only probes if it's closing in on the cause.
#   FORCE — stop probing: make ONE last plan request and accept plan/finish, else escalate.
#           Without this the model can spend EVERY attempt on read-only diagnostics and never
#           commit to a fix (observed on ticket 7005: 9 probes, no plan, then hard-limit escalate).
#   HARD  — absolute attempt cap; also covers the all-failing/unreachable case.
DIAGNOSE_SOFT_LIMIT = 4
DIAGNOSE_FORCE_LIMIT = 7
DIAGNOSE_HARD_LIMIT = 10
# After this many diagnostics are REJECTED (proposed but not read-only), stop asking for
# another diagnostic and force a plan — otherwise the agent re-proposes the same GATED command
# (e.g. the validation script) every iteration until the hard limit, doing no useful work.
REJECTED_DIAGNOSE_LIMIT = 2

# How many fix→verify cycles to attempt before escalating. Without this the agent can
# keep proposing plausible-but-wrong plans indefinitely (each human-approved), as on
# ticket 7005. After this many failed validations, hand to the technician with the evidence.
MAX_FIX_ATTEMPTS = 5

# The run loop advances on a background worker so POST handlers return immediately and
# the browser sees diagnostics stream in over SSE (ADR-0008). `_submit` is overridden to
# run inline in tests.
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="runloop")

# Background sweeper that evicts idle SSH sessions (e.g. a run parked at
# awaiting_plan_approval). Started on app startup, stopped on shutdown (main.py).
_reaper_stop = threading.Event()


def _reaper_loop() -> None:
    interval = settings.SSH_SESSION_REAP_INTERVAL
    ttl = settings.SSH_SESSION_IDLE_TTL
    while not _reaper_stop.wait(interval):
        try:
            reaped = store.reap_idle_sessions(ttl)
            if reaped:
                log.info("reaped %d idle SSH session(s)", reaped)
        except Exception:  # noqa: BLE001 - the sweeper must never die on one bad cycle
            log.exception("idle-session reaper cycle failed")


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
        log.exception("run loop failed run_id=%s status=%s", run.get("id"), run.get("status"))
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
        log.exception("could not schedule run loop run_id=%s", run.get("id"))
        try:
            if not is_terminal(run["status"]):
                _escalate(run, "could not schedule the run loop")
        except Exception:  # noqa: BLE001
            pass
        _close_if_terminal(run)


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
    """Close the run's SSH session once it reaches a terminal status, and persist the
    run to the durable corpus.

    The single site every terminal run passes through — finished/escalated via the
    worker's finally, aborted via the abort handler — so it is also where the full
    run (success OR failure) is snapshotted for the learning corpus (runlog). The
    per-run lock makes the close wait for any in-flight command so an abort on
    another thread never closes the transport mid-exec.
    """
    if is_terminal(run["status"]):
        runlog.record(run)  # durable record of every outcome, incl. failed/aborted
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
        # FORCE a decision once we have enough evidence OR have tried too many times: the next
        # propose() is the model's last chance to plan/finish — a further diagnose is refused so
        # it can't keep probing forever (the unreachable host, every diagnostic failing, also
        # lands here via attempts). SOFT just turns on the "plan now" nudge while still allowing
        # a couple more probes. Repeated rejections (non-read-only) also force the issue.
        force = executed >= DIAGNOSE_FORCE_LIMIT or attempts >= DIAGNOSE_HARD_LIMIT
        must_plan = force or executed >= DIAGNOSE_SOFT_LIMIT or len(rejected) >= REJECTED_DIAGNOSE_LIMIT
        action = agent.propose_action(ticket, system, _executed_history(run), memory=mem,
                                      must_plan=must_plan, rejected=rejected, force=force)
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
        # The model wants to diagnose again, but it has had its forced chance to plan — stop
        # here and hand to the technician with the evidence gathered, rather than probing on.
        if force:
            _escalate(run, "could not converge on a plan after diagnostics")
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
    run["fix_attempts"] = run.get("fix_attempts", 0) + 1
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
        if run.get("fix_attempts", 0) >= MAX_FIX_ATTEMPTS:
            _escalate(run, f"the fix did not pass validation after {run['fix_attempts']} attempts "
                           "— handing to the technician with the evidence gathered")
            return
        _replan(run, ticket, system)


def _replan(run, ticket, system, feedback: str = "") -> None:
    """After a failed/rejected plan, the agent forms a NEW plan for the technician to approve.

    `feedback` is optional technician steer (the "discuss" loop) passed through to the agent.
    """
    transition(run, RunStatus.ANALYZING)
    mem = memory_mod.retrieve(ticket, system)
    action = agent.propose_action(ticket, system, _executed_history(run), memory=mem,
                                  must_plan=True, feedback=feedback)
    if action.get("action") == "plan":
        _set_plan(run, action)
        store.audit(run["id"]).add("replan_proposed", root_cause=run["plan"]["root_cause"],
                                   steps=len(run["plan"]["steps"]))
    else:
        _escalate(run, "could not form a new plan after a failed attempt")
