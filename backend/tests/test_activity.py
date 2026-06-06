"""Spec for the activity documenter — deterministic fallback + redaction."""
from app import activity


def test_deterministic_draft_without_llm(monkeypatch):
    monkeypatch.setattr(activity.llm, "available", lambda: False)
    draft = activity.draft_activity(
        {"title": "Status API down"},
        [{"command": "systemctl status nginx", "stdout": "active", "exit_code": 0}],
    )
    for field in ("summary", "root_cause", "actions_taken", "commands_summary", "validation_result"):
        assert field in draft
    assert "systemctl status nginx" in draft["commands_summary"]


def test_llm_draft_fields_are_redacted(monkeypatch):
    monkeypatch.setattr(activity.llm, "available", lambda: True)
    monkeypatch.setattr(activity.llm, "complete_json", lambda *a, **k: {
        "summary": "ok", "root_cause": "leaked PASSWORD=hunter2", "actions_taken": "a",
        "commands_summary": "c", "validation_result": "v"})
    draft = activity.draft_activity({"title": "X"}, [])
    assert "[REDACTED]" in draft["root_cause"] and "hunter2" not in draft["root_cause"]
