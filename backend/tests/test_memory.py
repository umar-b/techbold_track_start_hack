"""Spec for the markdown-graph memory: sanitized write + lexical/1-hop retrieve."""
from app import memory
from app.config import settings

TICKET = {"id": 7001, "title": "Nginx not responding — web app down",
          "description": "502 Bad Gateway; nginx stopped after a reboot."}
SYSTEM = {"os": "Ubuntu 22.04"}
ACTIVITY = {"root_cause": "nginx was not enabled at boot", "validation_result": "HTTP 200 from localhost"}


def _setup(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "MEMORY_DIR", str(tmp_path / "mem"))
    return tmp_path / "mem"


def _resolved_run(run_id="abc123", ticket_id=7001):
    return {
        "id": run_id, "ticket_id": ticket_id, "created_at": "2026-06-06T10:00:00Z",
        "steps": [
            {"kind": "diagnose", "command": "systemctl status nginx", "status": "executed"},
            {"kind": "fix", "command": "systemctl enable --now nginx", "status": "executed"},
            {"kind": "fix", "command": "rm -rf /", "status": "blocked", "safety_reason": "blocked: destructive"},
            {"kind": "validate", "command": "curl -sI localhost", "status": "executed"},
        ],
    }


def test_write_note_captures_fields_and_redacts_secrets(monkeypatch, tmp_path):
    mem = _setup(monkeypatch, tmp_path)
    activity = {"root_cause": "auth failed: token=supersecret123 in config", "validation_result": "ok"}
    path = memory.write_note(_resolved_run(), TICKET, activity, SYSTEM)
    assert path is not None
    text = next(iter(mem.glob("*.md"))).read_text(encoding="utf-8")
    assert "systemctl enable --now nginx" in text   # the fix command-class captured
    assert "rm -rf /" in text                         # the blocked attempt captured
    assert "supersecret123" not in text               # secret redacted (ADR-0004)
    assert "[REDACTED]" in text
    assert "tags: systemctl" in text                  # tag derived from the fix binary


def test_fix_command_with_inline_password_is_redacted(monkeypatch, tmp_path):
    mem = _setup(monkeypatch, tmp_path)
    run = {"id": "r9", "ticket_id": 7003, "created_at": "2026-06-06T10:00:00Z",
           "steps": [{"kind": "fix", "command": "mysql -u root -ptopsecret -e 'FLUSH PRIVILEGES'",
                      "status": "executed"}]}
    memory.write_note(run, {"id": 7003, "title": "db reset", "description": "x"},
                      {"root_cause": "y", "validation_result": "z"}, {})
    text = (mem / "ticket7003-r9.md").read_text(encoding="utf-8")
    assert "topsecret" not in text and "-p[REDACTED]" in text


def test_retrieve_seeds_a_related_incident(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    memory.write_note(_resolved_run("r1"), TICKET, ACTIVITY, SYSTEM)
    new_ticket = {"id": 7009, "title": "nginx web server down again", "description": "site returns 502"}
    seed = memory.retrieve(new_ticket, SYSTEM)
    assert "ticket7001" in seed and "nginx" in seed.lower()
    assert "not enabled at boot" in seed             # root cause surfaced as a hypothesis


def test_retrieve_empty_when_no_notes(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    assert memory.retrieve(TICKET, SYSTEM) == ""


def test_unrelated_ticket_retrieves_nothing(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    memory.write_note(_resolved_run("r1"), TICKET, ACTIVITY, SYSTEM)
    unrelated = {"id": 7050, "title": "printer queue stuck on accounting laptop", "description": "spooler jam"}
    assert memory.retrieve(unrelated, SYSTEM) == ""


def test_notes_link_to_related_prior_notes(monkeypatch, tmp_path):
    mem = _setup(monkeypatch, tmp_path)
    memory.write_note(_resolved_run("r1", 7001), TICKET, ACTIVITY, SYSTEM)  # note A
    t2 = {"id": 7002, "title": "nginx upstream 504 timeout", "description": "nginx reverse proxy failing"}
    memory.write_note(_resolved_run("r2", 7002), t2, {"root_cause": "upstream slow", "validation_result": "ok"}, SYSTEM)
    b_text = (mem / "ticket7002-r2.md").read_text(encoding="utf-8")
    assert "ticket7001-r1" in b_text  # the second note links back to the first — a graph edge formed
