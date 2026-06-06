"""In-memory Run store + per-run audit log (ADR-0008).

Run control state lives in memory keyed by run_id (single-process demo). The
audit log is mirrored to a per-run file so the trail survives a restart.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .audit import AuditLog
from .config import settings
from .ssh_runner import SSHRunner  # one-way dependency: ssh_runner must not import runstore


def _now_iso() -> str:
    """Use UTC timestamps for run creation times."""

    return datetime.now(timezone.utc).isoformat()


class RunStore:
    """Small in-memory database for active troubleshooting runs."""

    def __init__(self) -> None:
        """Start with no runs and no audit logs."""

        self._runs: Dict[str, Dict[str, Any]] = {}
        self._audits: Dict[str, AuditLog] = {}
        # One reused SSH connection per run, owned here (run-control state, ADR-0008)
        # rather than as ambient module-global state in the route layer.
        # TODO: no idle-timeout eviction — a run parked at awaiting_plan_approval the
        # technician never resolves keeps its TCP connection until the process exits.
        self._sessions: Dict[str, SSHRunner] = {}
        # Per-run lock serialising a command-execution against a close, so an abort on
        # another thread cannot close the SSH transport mid-command (the run loop now
        # runs on a background worker — ADR-0008).
        self._locks: Dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def create(self, ticket_id: int) -> Dict[str, Any]:
        """Create a new run and its matching audit log."""

        run_id = uuid.uuid4().hex[:12]
        run = {
            "id": run_id,
            "ticket_id": ticket_id,
            "status": "created",
            "steps": [],
            "plan": None,
            "created_at": _now_iso(),
        }
        self._runs[run_id] = run
        self._audits[run_id] = AuditLog(run_id, persist_dir=settings.AUDIT_DIR)
        return run

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Return a run by id, or None when the id is unknown."""

        return self._runs.get(run_id)

    def audit(self, run_id: str) -> AuditLog:
        """Return the audit log for a run that already exists."""

        return self._audits[run_id]

    def all(self) -> List[Dict[str, Any]]:
        """Return all runs for debugging or future admin views."""

        return list(self._runs.values())

    def session(self, run: Dict[str, Any], system: Dict[str, Any]) -> SSHRunner:
        """The run's live SSH connection, created+connected on first use and reused.

        The connection deliberately survives between requests (e.g. the wait
        between starting a run and approving its plan), so it is keyed by run id
        rather than scoped to a single request.
        """
        sess = self._sessions.get(run["id"])
        if sess is None:
            sess = SSHRunner(
                host=system.get("ip", ""),
                port=int(system.get("port") or 22),
                username=system.get("username"),
                ticket_id=run["ticket_id"],
            )
            sess.ensure_connected()  # connect before storing, so a failed connect leaves nothing cached
            self._sessions[run["id"]] = sess
        else:
            sess.ensure_connected()  # reconnect if the connection dropped during an approval wait
        return sess

    def lock(self, run_id: str) -> threading.Lock:
        """The per-run lock guarding command-execution vs. close (created on first use)."""
        with self._locks_guard:
            lock = self._locks.get(run_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[run_id] = lock
            return lock

    def close_session(self, run_id: str) -> None:
        sess = self._sessions.pop(run_id, None)
        if sess is not None:
            try:
                sess.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass


# The API imports one shared store so all routes see the same demo state.
store = RunStore()
