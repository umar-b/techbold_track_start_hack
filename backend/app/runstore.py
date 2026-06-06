"""In-memory Run store + per-run audit log (ADR-0008).

Run control state lives in memory keyed by run_id (single-process demo). The
audit log is mirrored to a per-run file so the trail survives a restart.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .audit import AuditLog
from .config import settings


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    def __init__(self) -> None:
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._audits: Dict[str, AuditLog] = {}

    def create(self, ticket_id: int) -> Dict[str, Any]:
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
        return self._runs.get(run_id)

    def audit(self, run_id: str) -> AuditLog:
        return self._audits[run_id]

    def all(self) -> List[Dict[str, Any]]:
        return list(self._runs.values())


store = RunStore()
