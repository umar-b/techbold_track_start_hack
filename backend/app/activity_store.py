"""Durable mirror of submitted activities, keyed by ticket.

The Phoenix ERP exposes no endpoint to read activities back (only POST
/activities/create), so to show a ticket's resolution when it is reopened we keep
a local append-only copy written at submit time. Stored under AUDIT_DIR (the same
durable location as the per-run audit log, ADR-0008). Fields are already redacted
by the caller before they reach here (ADR-0004), so the mirror is secret-free.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from .config import settings

log = logging.getLogger("activity_store")


def _path(ticket_id: int) -> Path:
    base = Path(settings.AUDIT_DIR) / "activities"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{ticket_id}.jsonl"


def record(ticket_id: int, activity: Dict[str, Any]) -> None:
    """Append one submitted activity for a ticket. Never raises — a mirror-write
    failure must not break submitting the activity to the ERP."""
    try:
        with _path(ticket_id).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(activity) + "\n")
    except Exception:  # noqa: BLE001
        log.exception("activity mirror write failed for ticket %s", ticket_id)


def for_ticket(ticket_id: int) -> List[Dict[str, Any]]:
    """All recorded activities for a ticket, newest first. Never raises."""
    try:
        path = Path(settings.AUDIT_DIR) / "activities" / f"{ticket_id}.jsonl"
        if not path.is_file():
            return []
        out: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # skip a torn line rather than failing the whole read
        out.reverse()  # newest first
        return out
    except Exception:  # noqa: BLE001
        log.exception("activity mirror read failed for ticket %s", ticket_id)
        return []
