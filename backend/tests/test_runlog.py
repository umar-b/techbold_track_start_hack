"""Spec for the durable run corpus (runlog): every outcome persisted + redacted."""
from app import runlog
from app.config import settings


def _run(**over):
    run = {
        "id": "abc123",
        "ticket_id": 7001,
        "status": "finished",
        "created_at": "2026-06-07T09:00:00Z",
        "memory_count": 2,
        "steps": [
            {"index": 0, "kind": "diagnose", "command": "systemctl status nginx",
             "rationale": "check", "risk": "SAFE", "expected": "", "status": "executed",
             "safety_reason": "", "result": {"stdout": "active", "stderr": "", "exit_code": 0,
                                              "duration_ms": 5}},
            {"index": 1, "kind": "fix", "command": "systemctl enable --now nginx",
             "rationale": "enable", "risk": "GATED", "expected": "active", "status": "executed",
             "safety_reason": "", "result": {"stdout": "", "stderr": "", "exit_code": 0,
                                             "duration_ms": 9}},
        ],
    }
    run.update(over)
    return run


def test_record_then_read_back(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "AUDIT_DIR", str(tmp_path))
    runlog.record(_run())

    snap = runlog.get("abc123")
    assert snap is not None
    assert snap["outcome"] == "finished"
    assert snap["ticket_id"] == 7001
    assert snap["counts"] == {"steps": 2, "fixes": 1, "fixes_executed": 1, "fixes_failed": 0}
    assert [s["command"] for s in snap["steps"]] == [
        "systemctl status nginx", "systemctl enable --now nginx"]
    assert "ended_at" in snap


def test_failed_and_aborted_runs_are_recorded(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "AUDIT_DIR", str(tmp_path))
    runlog.record(_run(id="aborted1", status="aborted", steps=[]))
    runlog.record(_run(id="escalated1", status="escalated"))

    outcomes = {s["id"]: s["outcome"] for s in runlog.for_ticket(7001)}
    assert outcomes == {"aborted1": "aborted", "escalated1": "escalated"}


def test_for_ticket_filters_and_orders_newest_first(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "AUDIT_DIR", str(tmp_path))
    runlog.record(_run(id="old", ticket_id=7001))
    runlog.record(_run(id="new", ticket_id=7001))
    runlog.record(_run(id="other", ticket_id=7002))

    ids = [s["id"] for s in runlog.for_ticket(7001)]
    assert set(ids) == {"old", "new"}            # 7002 excluded
    assert ids == sorted(ids, key=lambda i: {"new": 0, "old": 1}[i])  # newest ended_at first


def test_secrets_are_redacted_in_the_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "AUDIT_DIR", str(tmp_path))
    leaky = _run(steps=[{"index": 0, "kind": "fix", "command": "mysql -psup3rs3cret",
                         "rationale": "", "risk": "GATED", "expected": "", "status": "executed",
                         "safety_reason": "", "result": {"stdout": "token=abc123secret", "stderr": "",
                                                         "exit_code": 0, "duration_ms": 1}}])
    runlog.record(leaky)

    snap = runlog.get("abc123")
    assert "sup3rs3cret" not in snap["steps"][0]["command"]
    assert "abc123secret" not in snap["steps"][0]["result"]["stdout"]


def test_reads_never_raise_on_missing_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "AUDIT_DIR", str(tmp_path / "nope"))
    assert runlog.get("whatever") is None
    assert runlog.for_ticket(7001) == []
