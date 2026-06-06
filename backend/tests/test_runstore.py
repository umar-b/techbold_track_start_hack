"""Spec for the in-memory run store (ADR-0008)."""
from app.audit import AuditLog
from app.runstore import RunStore


def test_create_returns_run_with_id_and_initial_status(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "AUDIT_DIR", str(tmp_path))
    store = RunStore()
    run = store.create(7001)
    assert run["ticket_id"] == 7001
    assert run["status"] == "created"
    assert run["steps"] == [] and run["plan"] is None
    assert store.get(run["id"]) is run


def test_audit_log_is_per_run(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "AUDIT_DIR", str(tmp_path))
    store = RunStore()
    run = store.create(7002)
    assert isinstance(store.audit(run["id"]), AuditLog)


def test_get_unknown_run_returns_none():
    assert RunStore().get("nope") is None
