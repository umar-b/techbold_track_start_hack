"""In-memory run store plus one audit log per run.

This is enough for the hackathon demo because the backend is one process. The
audit log is also written to disk so command history is not lost on restart.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .audit import AuditLog
from .config import settings


def _now_iso() -> str:
    """Use UTC timestamps for run creation times."""

    return datetime.now(timezone.utc).isoformat()


class RunStore:
    """Small in-memory database for active troubleshooting runs."""

    def __init__(self) -> None:
        """Start with no runs and no audit logs."""

        self._runs: Dict[str, Dict[str, Any]] = {}
        self._audits: Dict[str, AuditLog] = {}

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


# The API imports one shared store so all routes see the same demo state.
store = RunStore()
