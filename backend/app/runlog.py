"""Durable per-run record — the learning corpus (extends the audit trail, ADR-0008).

Run *control* state lives in memory (runstore) and is lost on restart. This module
is the durable counterpart: every run that reaches a terminal state — finished,
escalated, **or aborted** — is snapshotted to `AUDIT_DIR/runs/<run_id>.json` with
its full step log (every command, rationale, risk, status, stdout/stderr/exit) and
its outcome. Successes AND failures alike: a failed or aborted attempt is exactly
the negative signal that, accumulated across many tickets, lets the system learn to
resolve a recurring incident with less (eventually no) intervention.

Snapshots are redacted (ADR-0004) and append-as-file (one file per run, overwritten
idempotently at the terminal transition). They are removed only by hand. Writes
never raise — persisting the corpus must not break a run.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .audit import redact
from .config import settings

log = logging.getLogger("runlog")


def _dir() -> Path:
    base = Path(settings.AUDIT_DIR) / "runs"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_step(step: Dict[str, Any]) -> Dict[str, Any]:
    """A step copy with every free-text field re-redacted (defence in depth — the
    live step results are already redacted at capture)."""
    res = step.get("result")
    out: Dict[str, Any] = {
        "index": step.get("index"),
        "kind": step.get("kind"),
        "command": redact(step.get("command", "")),
        "rationale": redact(step.get("rationale", "")),
        "risk": step.get("risk"),
        "expected": redact(step.get("expected", "")),
        "status": step.get("status"),
        "safety_reason": redact(step.get("safety_reason", "")),
        "result": None,
    }
    if isinstance(res, dict):
        out["result"] = {
            "stdout": redact(res.get("stdout", "")),
            "stderr": redact(res.get("stderr", "")),
            "exit_code": res.get("exit_code"),
            "duration_ms": res.get("duration_ms"),
        }
    return out


def _snapshot(run: Dict[str, Any]) -> Dict[str, Any]:
    steps = run.get("steps", []) or []
    fixes = [s for s in steps if s.get("kind") == "fix"]
    return {
        "id": run.get("id"),
        "ticket_id": run.get("ticket_id"),
        # `status` mirrors the wire contract; `outcome` is the same value named for
        # the corpus reader (finished | escalated | aborted).
        "status": run.get("status"),
        "outcome": run.get("status"),
        "created_at": run.get("created_at"),
        "ended_at": _now_iso(),
        "memory_count": run.get("memory_count", 0),
        "counts": {
            "steps": len(steps),
            "fixes": len(fixes),
            "fixes_executed": sum(1 for s in fixes if s.get("status") == "executed"),
            "fixes_failed": sum(1 for s in fixes if s.get("status") in ("failed", "blocked")),
        },
        "steps": [_redact_step(s) for s in steps],
    }


def record(run: Dict[str, Any]) -> None:
    """Persist a terminal run's full snapshot (idempotent overwrite). Never raises."""
    try:
        run_id = run.get("id")
        if not run_id:
            return
        path = _dir() / f"{run_id}.json"
        path.write_text(json.dumps(_snapshot(run), indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 — corpus persistence must not break a run
        log.exception("run snapshot write failed for run %s", run.get("id"))


def get(run_id: str) -> Optional[Dict[str, Any]]:
    """One persisted run snapshot, or None. Survives a restart (unlike the in-memory
    run), so a terminated run's step log stays reviewable. Never raises."""
    try:
        path = Path(settings.AUDIT_DIR) / "runs" / f"{run_id}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        log.exception("run snapshot read failed for run %s", run_id)
        return None


def for_ticket(ticket_id: int) -> List[Dict[str, Any]]:
    """Every persisted run snapshot for a ticket, newest first — the full attempt
    history (resolved, escalated, aborted). Never raises."""
    try:
        base = Path(settings.AUDIT_DIR) / "runs"
        if not base.is_dir():
            return []
        out: List[Dict[str, Any]] = []
        for path in base.glob("*.json"):
            try:
                snap = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue  # skip a torn/locked file rather than failing the whole read
            if snap.get("ticket_id") == ticket_id:
                out.append(snap)
        out.sort(key=lambda s: s.get("ended_at", ""), reverse=True)
        return out
    except Exception:  # noqa: BLE001
        log.exception("run snapshot list failed for ticket %s", ticket_id)
        return []
