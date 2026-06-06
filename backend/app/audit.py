"""Audit trail and secret redaction.

Every string that can reach the UI, logs, or ERP activity should pass through
`redact()`. `AuditLog` records important run events and can mirror them to JSONL
so the team can prove what happened during a ticket.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Values that must never appear in logs, the UI, the repo, or an activity.
_REDACTIONS = [
    # Private key blocks are large, so match the whole block at once.
    (re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.S),
     "[REDACTED_PRIVATE_KEY]"),
    # Common KEY=value or key: value secret formats from configs and logs.
    (re.compile(r"(?i)\b([\w-]*(?:password|passwd|pwd|secret|token|api[_-]?key)[\w-]*)\s*[=:]\s*\S+"),
     r"\1=[REDACTED]"),
    # Bearer tokens are enough to access APIs, so never show the value.
    (re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+\S+"), "Authorization: Bearer [REDACTED]"),
    # Credentials embedded in a connection URI: scheme://user:pass@host
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+):[^\s:/@]+@"), r"\1:[REDACTED]@"),
]


def redact(text: Optional[str]) -> Optional[str]:
    """Return *text* with any detected secrets replaced. Non-strings pass through."""
    if not text or not isinstance(text, str):
        return text
    out = text
    for pattern, repl in _REDACTIONS:
        out = pattern.sub(repl, out)
    return out


def _now_iso() -> str:
    """Use UTC timestamps so audit entries compare cleanly across machines."""

    return datetime.now(timezone.utc).isoformat()


class AuditLog:
    """Append-only log of run actions."""

    def __init__(self, run_id: str, persist_dir: Optional[str] = None):
        """Create a log, optionally backed by one JSONL file on disk."""

        self.run_id = run_id
        self._entries: List[Dict[str, Any]] = []
        self._path: Optional[Path] = None
        if persist_dir:
            base = Path(persist_dir)
            base.mkdir(parents=True, exist_ok=True)
            self._path = base / f"{run_id}.jsonl"

    def add(self, event: str, **fields: Any) -> Dict[str, Any]:
        """Add one redacted event to memory and the JSONL file if enabled."""

        entry: Dict[str, Any] = {"ts": _now_iso(), "event": event}
        for key, value in fields.items():
            entry[key] = redact(value) if isinstance(value, str) else value
        self._entries.append(entry)
        if self._path is not None:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        return entry

    @property
    def entries(self) -> List[Dict[str, Any]]:
        """Return a copy so callers cannot edit the real audit history."""

        return list(self._entries)
