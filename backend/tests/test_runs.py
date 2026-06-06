"""Spec for the run orchestration API (mocked ERP + SSH + agent; no network)."""
import pytest
from fastapi.testclient import TestClient

from app import main as main_mod
from app.config import settings
from app.main import create_app, get_phoenix
from app.ssh_runner import CommandResult


class FakePhoenix:
    def __init__(self):
        self.statuses = []
        self.activities = []

    def me(self):
        return {"firstname": "A", "lastname": "B", "teamname": "T"}

    def list_tickets(self, status=None, priority=None, sort="date"):
        return [self.get_ticket(7001)]

    def get_ticket(self, tid):
        return {"id": tid, "title": "Status API down", "description": "health endpoint unreachable",
                "status": "OPEN", "priority": "high", "customer_name": "Nordlicht"}

    def customer_system(self, tid):
        return {"system": {"ip": "1.2.3.4", "port": 22, "username": "azureuser"}}

    def set_status(self, tid, status):
        self.statuses.append((tid, status))
        return {"id": tid, "status": status}

    def create_activity(self, payload):
        self.activities.append(payload)
        return {"id": 1, **payload}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "AUDIT_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "MEMORY_DIR", str(tmp_path / "memory"))
    # Keep tests hermetic: no real LLM/SSH calls even when .env has live creds.
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setattr(main_mod, "_execute",
                        lambda run, system, command, timeout=None: CommandResult("ok", "", 0, 5))
    # Run the background run-loop inline (with the same guard/cleanup) so assertions
    # made right after a POST see the converged state.
    monkeypatch.setattr(main_mod, "_submit", lambda fn, *a: main_mod._guarded(fn, *a))
    # The store is a module singleton — isolate each test.
    main_mod.store._runs.clear()
    main_mod.store._audits.clear()
    main_mod.store._sessions.clear()
    fake = FakePhoenix()
    app = create_app()
    app.dependency_overrides[get_phoenix] = lambda: fake
    client = TestClient(app)
    yield client, fake
    app.dependency_overrides.clear()


def _script(monkeypatch, actions):
    it = iter(actions)
    monkeypatch.setattr(main_mod.agent, "propose_action", lambda *a, **k: next(it))


def test_full_run_diagnose_plan_approve_finish(env, monkeypatch):
    client, fake = env
    _script(monkeypatch, [
        {"action": "diagnose", "command": "systemctl status nginx", "rationale": "check"},
        {"action": "diagnose", "command": "systemctl is-enabled nginx", "rationale": "enabled?"},
        {"action": "plan", "root_cause": "nginx not enabled",
         "steps": [{"command": "systemctl enable --now nginx", "expected": "active"}],
         "validation": ["curl -s http://localhost/health"]},
    ])
    run = client.post("/api/runs", json={"ticket_id": 7001}).json()
    rid = run["id"]
    assert run["status"] == "awaiting_plan_approval"
    assert run["plan"]["root_cause"] == "nginx not enabled"
    assert (7001, "PENDING") in fake.statuses
    assert len([s for s in run["steps"] if s["kind"] == "diagnose" and s["status"] == "executed"]) == 2

    run = client.post(f"/api/runs/{rid}/approve", json={}).json()
    assert run["status"] == "finished"
    fix = [s for s in run["steps"] if s["kind"] == "fix"]
    assert fix and fix[0]["status"] == "executed"
    assert any(s["kind"] == "validate" for s in run["steps"])

    draft = client.get(f"/api/runs/{rid}/activity-draft").json()
    assert "summary" in draft and "root_cause" in draft

    resp = client.post(f"/api/runs/{rid}/submit-activity",
                       json={"summary": "s", "root_cause": "r", "actions_taken": "a",
                             "commands_summary": "c", "validation_result": "v"}).json()
    assert resp["activity"]["ticket_id"] == 7001
    assert (7001, "DONE") in fake.statuses


def test_blocked_command_in_approved_plan_never_runs(env, monkeypatch):
    client, _ = env
    _script(monkeypatch, [
        {"action": "plan", "root_cause": "x", "steps": [{"command": "rm -rf /"}], "validation": []},
        {"action": "finish", "summary": "done"},
    ])
    rid = client.post("/api/runs", json={"ticket_id": 7001}).json()["id"]
    run = client.post(f"/api/runs/{rid}/approve", json={}).json()
    fix = [s for s in run["steps"] if s["kind"] == "fix"][0]
    assert fix["status"] == "blocked" and fix["risk"] == "BLOCKED"
    # blocked fix -> verification fails -> agent re-plans; here it can't, so it escalates
    assert run["status"] == "escalated"


def test_abort_from_plan_gate(env, monkeypatch):
    client, _ = env
    _script(monkeypatch, [
        {"action": "plan", "root_cause": "x", "steps": [{"command": "systemctl restart nginx"}],
         "validation": []},
    ])
    rid = client.post("/api/runs", json={"ticket_id": 7001}).json()["id"]
    run = client.post(f"/api/runs/{rid}/abort").json()
    assert run["status"] == "aborted"


def test_get_unknown_run_404(env):
    client, _ = env
    assert client.get("/api/runs/nope").status_code == 404


def test_reject_on_non_awaiting_returns_409(env, monkeypatch):
    client, _ = env
    _script(monkeypatch, [{"action": "finish", "summary": "already healthy"}])
    rid = client.post("/api/runs", json={"ticket_id": 7001}).json()["id"]
    # the run finished during analysis — there is nothing to reject
    assert client.post(f"/api/runs/{rid}/reject", json={}).status_code == 409


def test_start_run_returns_immediately_before_analysis(env, monkeypatch):
    client, _ = env
    # Defer the background loop: the POST must return at once, before diagnostics run.
    monkeypatch.setattr(main_mod, "_submit", lambda fn, *a: None)
    run = client.post("/api/runs", json={"ticket_id": 7001}).json()
    assert run["status"] == "analyzing"
    assert run["steps"] == [] and run["plan"] is None


def test_set_plan_keeps_no_plan_when_run_already_aborted():
    # abort-during-analysis race: transition must raise before the plan is written
    from app.runstate import IllegalTransition
    run = {"id": "x", "ticket_id": 7001, "status": "aborted", "steps": [], "plan": None}
    with pytest.raises(IllegalTransition):
        main_mod._set_plan(run, {"root_cause": "c", "steps": [], "validation": []})
    assert run["plan"] is None


def test_second_concurrent_run_for_ticket_is_rejected(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(main_mod, "_submit", lambda fn, *a: None)  # leave the first run active
    assert client.post("/api/runs", json={"ticket_id": 7001}).status_code == 200
    assert client.post("/api/runs", json={"ticket_id": 7001}).status_code == 409


def test_unreachable_host_escalates_instead_of_looping(env, monkeypatch):
    client, _ = env
    # Every diagnostic fails (host unreachable) and the agent only ever wants to probe.
    monkeypatch.setattr(main_mod.agent, "propose_action",
                        lambda *a, **k: {"action": "diagnose", "command": "systemctl status x", "rationale": "probe"})
    monkeypatch.setattr(main_mod, "_execute",
                        lambda run, system, command, timeout=None: CommandResult("", "unreachable", 1, 5))
    run = client.post("/api/runs", json={"ticket_id": 7001}).json()
    assert run["status"] == "escalated"
    assert len([s for s in run["steps"] if s["kind"] == "diagnose"]) >= main_mod.DIAGNOSE_HARD_LIMIT


def test_finish_with_no_successful_evidence_escalates(env, monkeypatch):
    client, _ = env
    actions = iter([
        {"action": "diagnose", "command": "systemctl status x", "rationale": "probe"},
        {"action": "finish", "summary": "looks fine"},
    ])
    monkeypatch.setattr(main_mod.agent, "propose_action", lambda *a, **k: next(actions))
    monkeypatch.setattr(main_mod, "_execute",
                        lambda run, system, command, timeout=None: CommandResult("", "no route to host", 1, 5))
    run = client.post("/api/runs", json={"ticket_id": 7001}).json()
    assert run["status"] == "escalated"  # all diagnostics failed -> can't report "resolved"


def test_tickets_proxy(env):
    client, _ = env
    assert client.get("/api/tickets").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}
