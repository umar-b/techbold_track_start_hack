"""Markdown-graph memory (ADR-0001, ADR-0009) — the product's differentiator.

Each resolved Run appends ONE sanitized markdown note: symptom signature, root
cause, the fix as command-classes, failed attempts, verification, tags, and
`[[wiki-links]]` to related notes. On a new Run, relevant notes are retrieved by
a lexical tag/keyword prefilter plus a 1-hop link traversal (no embeddings, no
DB) and formatted as hypotheses-to-verify that SEED the proposed Plan — never as
actions to apply, and never removing an approval gate.

Notes are committed (MEMORY_DIR) so the shared brain is visible. Every field is
passed through the same `redact()` sanitizer as an Activity, so notes are
secret-free (ADR-0004).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .audit import redact
from .config import settings

log = logging.getLogger("memory")

_STOPWORDS = {
    "the", "and", "for", "are", "was", "but", "not", "you", "with", "this", "that",
    "from", "have", "has", "after", "before", "since", "they", "their", "appears",
    "please", "system", "issue", "customer", "reports", "report", "running", "again",
}
_MAX_LINKS = 3
_MAX_RETRIEVE = 3


def _dir() -> Path:
    path = Path(settings.MEMORY_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _keywords(text: str) -> set:
    tokens = re.findall(r"[a-z0-9][a-z0-9.+_-]{2,}", (text or "").lower())
    return {t for t in tokens if t not in _STOPWORDS}


def _command_bin(command: str) -> str:
    """First meaningful binary of a command (skips sudo/env-style prefixes)."""
    parts = (command or "").split()
    skip = {"sudo", "env", "time", "nice"}
    for part in parts:
        if part in skip or "=" in part:
            continue
        return part.rsplit("/", 1)[-1]
    return ""


def _tags(title: str, commands: List[str]) -> List[str]:
    tags: List[str] = []
    for cmd in commands:
        binary = _command_bin(cmd)
        if binary and binary not in tags:
            tags.append(binary)
    for kw in _keywords(title):
        if len(tags) >= 6:
            break
        if kw not in tags:
            tags.append(kw)
    return tags[:6]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:40] or "note"


# --- note model (lightweight frontmatter, no YAML dependency) --------------- #
def _parse_note(path: Path) -> Optional[Dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    meta: Dict[str, Any] = {"id": path.stem, "tags": [], "links": [], "title": "", "body": raw}
    parts = raw.split("---", 2)
    if raw.startswith("---") and len(parts) == 3:  # well-formed frontmatter only
        front, body = parts[1], parts[2]
        meta["body"] = body
        for line in front.strip().splitlines():
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip()
            if key in ("tags", "links"):
                meta[key] = [v.strip() for v in value.split(",") if v.strip()]
            elif key:
                meta[key] = value
    return meta


def _load_notes() -> List[Dict[str, Any]]:
    base = Path(settings.MEMORY_DIR)  # read path: do not create the dir
    if not base.is_dir():
        return []
    notes = []
    for path in sorted(base.glob("*.md")):
        note = _parse_note(path)
        if note:
            notes.append(note)
    return notes


def _score(query_kw: set, query_tags: set, note: Dict[str, Any]) -> int:
    note_tags = {t.lower() for t in note.get("tags", [])}
    note_kw = _keywords(note.get("title", "")) | _keywords(note.get("body", ""))
    return 2 * len(query_tags & note_tags) + len(query_kw & note_kw)


def _rank(ticket: Dict[str, Any], commands: List[str], notes: List[Dict[str, Any]],
          limit: int) -> List[Dict[str, Any]]:
    query_kw = _keywords(f"{ticket.get('title', '')} {ticket.get('description', '')}")
    query_tags = {t.lower() for t in _tags(ticket.get("title", ""), commands)}
    scored = [(n, _score(query_kw, query_tags, n)) for n in notes]
    hits = sorted([s for s in scored if s[1] > 0], key=lambda s: s[1], reverse=True)
    return [n for n, _ in hits[:limit]]


def _select(ticket: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    """Ranked related notes + 1-hop link expansion — the retrieval core. Never raises."""
    try:
        notes = _load_notes()
        if not notes:
            return []
        by_id = {n["id"]: n for n in notes}
        top = _rank(ticket, [], notes, limit)
        seen = {n["id"] for n in top}
        for note in list(top):  # 1-hop: pull in directly-linked notes
            for link in note.get("links", []):
                if link in by_id and link not in seen:
                    top.append(by_id[link])
                    seen.add(link)
        return top
    except Exception:  # noqa: BLE001
        log.exception("memory retrieval failed")
        return []


def retrieve(ticket: Dict[str, Any], system: Dict[str, Any] | None = None,
             limit: int = _MAX_RETRIEVE) -> str:
    """Related past incidents as hypotheses-to-verify (ADR-0009), or "" if none.

    Lexical prefilter over note tags/keywords, then a 1-hop expansion along the
    top matches' wiki-links. Never raises — memory must not break the run.
    """
    top = _select(ticket, limit)
    if not top:
        return ""
    return "\n".join(
        f"- [{n.get('id')}] {n.get('title', '').strip()}\n"
        f"  tags: {', '.join(n.get('tags', []))}\n"
        f"  {_summary(n.get('body', ''))}"
        for n in top
    )


def retrieve_notes(ticket: Dict[str, Any], system: Dict[str, Any] | None = None,
                   limit: int = _MAX_RETRIEVE) -> List[Dict[str, Any]]:
    """The same selection as retrieve(), as structured summaries — powers the
    per-run "seeded by N past incidents" UI chip."""
    return [{"id": n.get("id"), "title": n.get("title", "").strip(),
             "tags": n.get("tags", []), "root_cause": _summary(n.get("body", ""))}
            for n in _select(ticket, limit)]


def list_notes() -> List[Dict[str, Any]]:
    """All memory notes as summaries (newest first) for the memory browser."""
    out = [{"id": n.get("id"), "title": n.get("title", "").strip(),
            "tags": n.get("tags", []), "os": n.get("os", ""),
            "created_at": n.get("created_at", ""), "links": n.get("links", []),
            "root_cause": _summary(n.get("body", ""))}
           for n in _load_notes()]
    out.sort(key=lambda n: n.get("created_at", ""), reverse=True)
    return out


def _summary(body: str) -> str:
    """Pull the root-cause line(s) from a note body for the seed text."""
    match = re.search(r"##+\s*Root cause\s*\n(.+?)(?:\n##|\Z)", body, re.S)
    text = (match.group(1) if match else body).strip().replace("\n", " ")
    return text[:240]


def write_note(run: Dict[str, Any], ticket: Dict[str, Any], activity: Dict[str, Any],
               system: Dict[str, Any] | None = None) -> Optional[str]:
    """Append one sanitized note for a resolved Run; returns its path, or None.

    Never raises — a memory-write failure must not break submitting an Activity.
    """
    try:
        steps = run.get("steps", [])
        fixes = [redact(s.get("command", "")) for s in steps
                 if s.get("kind") == "fix" and s.get("status") == "executed" and s.get("command")]
        failed = [f"{redact(s.get('command', ''))} — {redact(s.get('safety_reason', '') or 'failed')}"
                  for s in steps
                  if s.get("kind") == "fix" and s.get("status") in ("failed", "blocked") and s.get("command")]
        title = redact(ticket.get("title", "")) or f"Ticket {run.get('ticket_id')}"
        tags = _tags(title, fixes)
        os_name = (system or {}).get("os", "") if system else ""

        # Link to the most relevant existing notes (forms the graph).
        links = [n["id"] for n in _rank(ticket, fixes, _load_notes(), _MAX_LINKS)]
        note_id = f"ticket{run.get('ticket_id')}-{_slug(run.get('id', ''))}"

        front = [
            "---",
            f"id: {note_id}",
            f"ticket_id: {run.get('ticket_id')}",
            f"title: {title}",
            f"tags: {', '.join(tags)}",
            f"os: {redact(os_name)}",
            f"created_at: {run.get('created_at', '')}",
            f"links: {', '.join(links)}",
            "---",
        ]
        fix_lines = [f"- `{c}`" for c in fixes] or ["(no state-changing fix)"]
        failed_lines = [f"- {f}" for f in failed] or ["(none)"]
        body = [
            f"# {title}",
            "",
            "## Symptom",
            redact(ticket.get("description", ""))[:600].strip() or "(none recorded)",
            "",
            "## Root cause",
            redact(activity.get("root_cause", "")).strip() or "(not recorded)",
            "",
            "## Fix (command classes)",
            *fix_lines,
            "",
            "## Failed attempts",
            *failed_lines,
            "",
            "## Verification",
            redact(activity.get("validation_result", "")).strip() or "(not recorded)",
        ]
        if links:
            body += ["", "## Related", " ".join(f"[[{link}]]" for link in links)]

        path = _dir() / f"{note_id}.md"
        path.write_text("\n".join(front) + "\n\n" + "\n".join(body) + "\n", encoding="utf-8")
        return str(path)
    except Exception:  # noqa: BLE001
        log.exception("memory note write failed")
        return None
