"""In-memory Run store + per-run audit log (ADR-0008).

Run control state lives in memory keyed by run_id (single-process demo). The
audit log is mirrored to a per-run file so the trail survives a restart.
"""
from __future__ import annotations

import threading
import time
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
        # rather than as ambient module-global state in the route layer. The reaper
        # (reap_idle_sessions) evicts connections left idle past a TTL — e.g. a run
        # parked at awaiting_plan_approval — using the monotonic last-touch below.
        self._sessions: Dict[str, SSHRunner] = {}
        self._session_last_used: Dict[str, float] = {}
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

    def summary(self) -> Dict[str, Any]:
        """Aggregate run counts by status + live-session count (for /api/stats)."""
        by_status: Dict[str, int] = {}
        for run in self._runs.values():
            by_status[run["status"]] = by_status.get(run["status"], 0) + 1
        return {
            "total": len(self._runs),
            "by_status": by_status,
            "active_sessions": len(self._sessions),
        }

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
        self._session_last_used[run["id"]] = time.monotonic()
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
        self._session_last_used.pop(run_id, None)
        sess = self._sessions.pop(run_id, None)
        if sess is not None:
            try:
                sess.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass

    def reap_idle_sessions(self, ttl_seconds: float, now: Optional[float] = None) -> int:
        """Close SSH sessions untouched for longer than ttl_seconds; return the count.

        Takes each run's lock non-blockingly: a session with a command in flight
        holds the lock, so it is skipped (it is not idle anyway). The next command
        on a reaped run transparently reconnects via session(). ttl<=0 disables.
        """
        if ttl_seconds <= 0:
            return 0
        current = time.monotonic() if now is None else now
        reaped = 0
        for run_id in list(self._sessions.keys()):
            last = self._session_last_used.get(run_id, current)
            if current - last < ttl_seconds:
                continue
            lock = self.lock(run_id)
            if not lock.acquire(blocking=False):
                continue  # a command is running on this session — not idle
            try:
                self.close_session(run_id)
                reaped += 1
            finally:
                lock.release()
        return reaped


# The API imports one shared store so all routes see the same demo state.
store = RunStore()
