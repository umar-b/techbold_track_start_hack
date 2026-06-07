"""Spec for the local activity mirror (durable per-ticket resolution record)."""
from app import activity_store
from app.config import settings


def test_record_then_for_ticket_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "AUDIT_DIR", str(tmp_path))
    activity_store.record(7001, {"summary": "first", "root_cause": "a"})
    activity_store.record(7001, {"summary": "second", "root_cause": "b"})
    out = activity_store.for_ticket(7001)
    assert [a["summary"] for a in out] == ["second", "first"]


def test_for_ticket_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "AUDIT_DIR", str(tmp_path))
    assert activity_store.for_ticket(9999) == []


def test_for_ticket_skips_a_torn_line(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "AUDIT_DIR", str(tmp_path))
    activity_store.record(7002, {"summary": "ok"})
    path = tmp_path / "activities" / "7002.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")
    out = activity_store.for_ticket(7002)
    assert len(out) == 1 and out[0]["summary"] == "ok"
