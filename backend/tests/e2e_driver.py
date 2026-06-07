"""Reusable live end-to-end driver — the Technician-in-the-loop workflow runner.

Drives ONE ticket through the real workflow against live infrastructure (real
Phoenix ERP, real SSH to the customer VM, real Azure LLM): start -> read-only
diagnose -> approve the fix plan -> execute -> validate -> submit the activity.
The driver plays the **Technician**: it approves the agent's plan unedited (the
honest test of whether the agent gets it right unaided) and approves any GATED
diagnostic probe the agent asks to run.

It is deliberately generic — it asserts nothing ticket-specific (no hard-coded
service/path/command), only the *shape* of a correct run, so it generalises to
the four hidden tickets in the final eval. The per-ticket pytest suite
(`test_e2e_live.py`) and the fast concurrent optimize script both import this.

This module is NOT a test file (no `test_` prefix) and is never collected.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi.testclient import TestClient

from app import orchestrator as orch_mod
from app.main import create_app
from app.config import settings

# ---- "works first try" definition ---------------------------------------- #
# These audit events mean the agent did NOT solve it on the first plan: it had to
# re-plan, a validation failed, the technician rejected, or it gave up. A clean
# first-try run shows none of them.
NOT_FIRST_TRY_EVENTS = {
    "replan_proposed", "verification_failed", "plan_rejected", "escalated",
    "command_blocked", "nonread_diagnostic_rejected",
}

# Secret shapes that must NEVER appear in audit / activity / memory (redaction holds).
# Matches real leaked material, not the literal "[REDACTED...]" placeholders.
import re  # noqa: E402

_SECRET_SCANNERS = [
    re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{12,}"),
    re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key)\s*[=:]\s*(?!\[REDACTED)\S{4,}"),
    re.compile(r"(?i)://[^\s:/@]+:(?!\[REDACTED)[^\s:/@]{3,}@"),  # user:pass@host
]


def scan_secrets(text: str) -> List[str]:
    """Return any secret-looking substrings found (should be empty everywhere)."""
    if not text:
        return []
    hits: List[str] = []
    for pat in _SECRET_SCANNERS:
        hits += pat.findall(text)
    return hits


@dataclass
class TicketResult:
    ticket_id: int
    run_id: str = ""
    final_status: str = ""
    fix_attempts: int = 0
    diagnostic_gates: int = 0
    diagnose_steps: int = 0
    events: List[str] = field(default_factory=list)
    validation_passed: bool = False
    activity_id: Optional[Any] = None
    ticket_status: str = ""
    memory_note: Optional[str] = None
    secret_hits: List[str] = field(default_factory=list)
    error: str = ""
    elapsed_s: float = 0.0
    run: Dict[str, Any] = field(default_factory=dict)
    audit: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def first_try(self) -> bool:
        """True iff the agent resolved it on its first fix plan, validated, no retries."""
        return (
            self.final_status == "finished"
            and self.fix_attempts == 1
            and self.validation_passed
            and not (set(self.events) & NOT_FIRST_TRY_EVENTS)
            and not self.secret_hits
        )

    def why(self) -> str:
        """One-line human-readable verdict for the scoreboard."""
        if self.error:
            return f"ERROR: {self.error}"
        if self.first_try:
            extra = f" (+{self.diagnostic_gates} diag-gate)" if self.diagnostic_gates else ""
            return f"first-try OK{extra} — {self.diagnose_steps} probes, validated, activity {self.activity_id}"
        bad = sorted(set(self.events) & NOT_FIRST_TRY_EVENTS)
        bits = [f"status={self.final_status}", f"fix_attempts={self.fix_attempts}",
                f"validated={self.validation_passed}"]
        if bad:
            bits.append("events=" + ",".join(bad))
        if self.secret_hits:
            bits.append(f"LEAK={self.secret_hits[:2]}")
        return "; ".join(bits)


def install_inline_submit() -> Any:
    """Run the orchestrator loop inline (like the mocked suite) for deterministic,
    poll-free driving. Returns the previous `_submit` so the caller can restore it."""
    prev = orch_mod._submit
    orch_mod._submit = lambda fn, *a: orch_mod._guarded(fn, *a)
    return prev


def build_live_client() -> TestClient:
    """A TestClient over the REAL app: real Phoenix, real SSH, real agent/LLM.

    Only the run-loop scheduling is made inline (deterministic). The reaper is left
    to settings (callers should set SSH_SESSION_IDLE_TTL=0 in env to disable it)."""
    return TestClient(create_app())


def _last_validate_passed(run: Dict[str, Any]) -> bool:
    """True iff the provided public-test.sh was run and exited 0.

    Ticket-agnostic: every ticket validates with the same `sudo /opt/hackathon/
    public-test.sh`, so this is the universal graded success signal, not an overfit.
    Accepts it as a validate OR fix step (the agent normally puts it in the plan's
    validation list, but a fix-step placement still counts as the check having run)."""
    runs = [s for s in run.get("steps", [])
            if s.get("kind") in ("validate", "fix") and "public-test.sh" in (s.get("command") or "")]
    if not runs:
        return False
    res = runs[-1].get("result") or {}
    return runs[-1].get("status") == "executed" and res.get("exit_code") == 0


def run_ticket(client: TestClient, ticket_id: int, *, max_gates: int = 12,
               phase_timeout: float = 300.0) -> TicketResult:
    """Drive one ticket end-to-end as the Technician. Never raises — captures the
    outcome (success or failure) into a TicketResult for assertion / diagnosis."""
    r = TicketResult(ticket_id=ticket_id)
    t0 = time.time()
    try:
        resp = client.post("/api/runs", json={"ticket_id": ticket_id})
        if resp.status_code != 200:
            r.error = f"start {resp.status_code}: {resp.text[:200]}"
            return r
        run = resp.json()
        r.run_id = run["id"]

        gates = 0
        while True:
            run = _wait_settled(client, r.run_id, phase_timeout)
            status = run["status"]
            if status in ("finished", "escalated", "aborted"):
                break
            if status == "awaiting_plan_approval":
                gates += 1
                if gates > max_gates:
                    r.error = f"exceeded {max_gates} approval gates (loop)"
                    client.post(f"/api/runs/{r.run_id}/abort")
                    break
                plan = run.get("plan") or {}
                if plan.get("mode") == "diagnostic":
                    r.diagnostic_gates += 1
                # Technician approves the plan UNEDITED (honest test of the agent).
                ap = client.post(f"/api/runs/{r.run_id}/approve", json={})
                if ap.status_code != 200:
                    r.error = f"approve {ap.status_code}: {ap.text[:200]}"
                    break
                continue
            # Unexpected non-terminal stall.
            r.error = f"stalled in status={status}"
            client.post(f"/api/runs/{r.run_id}/abort")
            break

        run = client.get(f"/api/runs/{r.run_id}").json()
        r.run = run
        r.final_status = run["status"]
        r.fix_attempts = run.get("fix_attempts", 0)
        r.diagnose_steps = sum(1 for s in run["steps"]
                               if s["kind"] == "diagnose" and s["status"] == "executed")
        r.validation_passed = _last_validate_passed(run)
        r.audit = client.get(f"/api/runs/{r.run_id}/audit").json().get("entries", [])
        r.events = [e["event"] for e in r.audit]

        # The Technician documents and submits the activity for a resolved run.
        if r.final_status == "finished":
            _submit_activity(client, r)

        # Memory + audit must be secret-free.
        r.secret_hits = _scan_run_artifacts(r)
        r.memory_note = _find_memory_note(r.run_id)
    except Exception as exc:  # noqa: BLE001 - the driver must always return a result
        r.error = f"{type(exc).__name__}: {exc}"
    finally:
        r.elapsed_s = round(time.time() - t0, 1)
    return r


def _wait_settled(client: TestClient, run_id: str, timeout: float) -> Dict[str, Any]:
    """Poll until the run reaches a stable state (awaiting approval or terminal).

    With inline `_submit` the POST already returns settled, so the first GET breaks
    immediately; the poll loop also supports the background-worker mode unchanged."""
    deadline = time.time() + timeout
    last = client.get(f"/api/runs/{run_id}").json()
    while time.time() < deadline:
        status = last["status"]
        if status in ("awaiting_plan_approval", "finished", "escalated", "aborted"):
            return last
        time.sleep(0.5)
        last = client.get(f"/api/runs/{run_id}").json()
    return last


def _submit_activity(client: TestClient, r: TicketResult) -> None:
    draft = client.get(f"/api/runs/{r.run_id}/activity-draft").json()
    body = {k: draft.get(k, "") for k in
            ("summary", "root_cause", "actions_taken", "commands_summary", "validation_result")}
    body["set_done"] = True
    resp = client.post(f"/api/runs/{r.run_id}/submit-activity", json=body)
    if resp.status_code != 200:
        r.error = f"submit-activity {resp.status_code}: {resp.text[:200]}"
        return
    created = resp.json().get("activity") or {}
    r.activity_id = created.get("id") if isinstance(created, dict) else None
    # Confirm the ERP write landed and the ticket is DONE (read-back via our mirror).
    acts = client.get(f"/api/tickets/{r.ticket_id}/activities").json().get("activities", [])
    r.ticket_status = "DONE" if acts else ""


def _scan_run_artifacts(r: TicketResult) -> List[str]:
    """Scan everything that leaves the box (audit + memory note) for secret leakage."""
    hits: List[str] = []
    for entry in r.audit:
        for v in entry.values():
            if isinstance(v, str):
                hits += scan_secrets(v)
    note = _find_memory_note(r.run_id)
    if note and os.path.isfile(note):
        with open(note, encoding="utf-8") as fh:
            hits += scan_secrets(fh.read())
    return hits


def _find_memory_note(run_id: str) -> Optional[str]:
    """The memory note written for this run, if any (slug embeds the run id)."""
    base = settings.MEMORY_DIR
    if not run_id or not os.path.isdir(base):
        return None
    for name in os.listdir(base):
        if name.endswith(".md") and run_id in name:
            return os.path.join(base, name)
    return None


# ---- environment reset (eval-harness setup) ------------------------------- #
ALL_TICKETS = [7001, 7002, 7003, 7004, 7005]


def reset_team(timeout: float = 120.0) -> Dict[str, Any]:
    """Clear activities + reboot (redeploy) all VMs via Phoenix. Returns the result.

    Reset triggers VM reboots, so the endpoint is slow to respond — use a generous
    timeout and NO retries (a retried POST would request a second reboot)."""
    from app.phoenix_client import PhoenixClient
    px = PhoenixClient(retries=0, timeout=timeout)
    try:
        return px.reset_me()
    finally:
        px.close()


# A VM is "freshly rebooted" only if its /proc/uptime is below this. Reset reboots
# leave the prior session up for a moment, so reachability alone is not proof of a
# reboot — a low uptime (or an observed down->up transition) is.
_FRESH_BOOT_SECONDS = 300.0


def wait_for_vms(ticket_ids: Optional[List[int]] = None, *, timeout: float = 540.0,
                 log=print) -> Dict[int, bool]:
    """Block until every VM has actually REBOOTED and is reachable again (or timeout).

    The reset endpoint only *requests* a reboot, then returns; the VM stays up for a
    moment before going down. So "reachable" is not enough — probing too early catches
    the pre-reboot host. A VM is accepted as freshly redeployed only when it is
    reachable AND either (a) its /proc/uptime is low (it booted recently) or (b) we
    previously saw it go down in this wait (a definitive reboot). Returns
    {ticket_id: ready}."""
    from app.phoenix_client import PhoenixClient
    from app.ssh_runner import SSHRunner

    ticket_ids = ticket_ids or ALL_TICKETS
    px = PhoenixClient()
    targets: Dict[int, Dict[str, Any]] = {}
    for tid in ticket_ids:
        try:
            targets[tid] = px.customer_system(tid).get("system", {})
        except Exception as exc:  # noqa: BLE001
            log(f"[reset] ticket {tid}: cannot read customer-system: {exc}")
    px.close()

    ready: Dict[int, bool] = {tid: False for tid in ticket_ids}
    seen_down: Dict[int, bool] = {tid: False for tid in ticket_ids}
    deadline = time.time() + timeout
    while time.time() < deadline and not all(ready.values()):
        for tid, sysinfo in targets.items():
            if ready.get(tid):
                continue
            try:
                runner = SSHRunner(host=sysinfo.get("ip", ""), port=int(sysinfo.get("port") or 22),
                                   username=sysinfo.get("username"), ticket_id=tid)
                runner.__enter__()
                uptime = float(runner.run("cat /proc/uptime", timeout=10).stdout.split()[0])
                runner.__exit__(None, None, None)
                if seen_down[tid] or uptime < _FRESH_BOOT_SECONDS:
                    ready[tid] = True
                    log(f"[reset] ticket {tid} VM rebooted+up (uptime {uptime:.0f}s, "
                        f"{sum(ready.values())}/{len(ready)})")
            except Exception:  # noqa: BLE001 - unreachable => it is rebooting now
                seen_down[tid] = True
        if not all(ready.values()):
            time.sleep(8.0)
    return ready
