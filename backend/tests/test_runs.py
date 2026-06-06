"""Spec for the run orchestration API (mocked ERP + SSH + agent; no network)."""
import pytest
from fastapi.testclient import TestClient

from app import main as main_mod
from app.config import settings
from app.main import create_app, get_phoenix
from app.ssh_runner import CommandResult


class FakePhoenix:
    """Tiny Phoenix fake that records status and activity writes."""

    def __init__(self):
        """Start with no writes recorded."""

        self.statuses = []
        self.activities = []

    def me(self):
        """Return a fake technician identity."""

        return {"firstname": "A", "lastname": "B", "teamname": "T"}

    def list_tickets(self, status=None, priority=None, sort="date"):
        """Return one assigned ticket; filters are not needed for these tests."""

        return [self.get_ticket(7001)]

    def get_ticket(self, tid):
        """Return the ticket shape used by the run API."""

        return {"id": tid, "title": "Status API down", "description": "health endpoint unreachable",
                "status": "OPEN", "priority": "high", "customer_name": "Nordlicht"}

    def customer_system(self, tid):
        """Return a fake SSH target for the ticket."""

        return {"system": {"ip": "1.2.3.4", "port": 22, "username": "azureuser"}}

    def set_status(self, tid, status):
        """Record ticket status changes instead of calling Phoenix."""

        self.statuses.append((tid, status))
        return {"id": tid, "status": status}

    def create_activity(self, payload):
        """Record the activity payload that would be sent to Phoenix."""

        self.activities.append(payload)
        return {"id": 1, **payload}


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Build a hermetic API client with fake ERP, fake SSH, and no LLM."""

    monkeypatch.setattr(settings, "AUDIT_DIR", str(tmp_path))
    # Keep tests hermetic: no real LLM/SSH calls even when .env has live creds.
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setattr(main_mod, "_execute",
                        lambda run, system, command, timeout=None: CommandResult("ok", "", 0, 5))
    fake = FakePhoenix()
    app = create_app()
    app.dependency_overrides[get_phoenix] = lambda: fake
    client = TestClient(app)
    yield client, fake
    app.dependency_overrides.clear()


def _script(monkeypatch, actions):
    """Make the agent return a fixed sequence of actions."""

    it = iter(actions)
    monkeypatch.setattr(main_mod.agent, "propose_action", lambda *a, **k: next(it))


def test_full_run_diagnose_plan_approve_finish(env, monkeypatch):
    """A normal run should diagnose, wait for approval, verify, and submit activity."""

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
    """Even an approved plan must not execute a BLOCKED command."""

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
    """The technician can abort while a plan is waiting for approval."""

    client, _ = env
    _script(monkeypatch, [
        {"action": "plan", "root_cause": "x", "steps": [{"command": "systemctl restart nginx"}],
         "validation": []},
    ])
    rid = client.post("/api/runs", json={"ticket_id": 7001}).json()["id"]
    run = client.post(f"/api/runs/{rid}/abort").json()
    assert run["status"] == "aborted"


def test_get_unknown_run_404(env):
    """Unknown run ids should return a 404 from the API."""

    client, _ = env
    assert client.get("/api/runs/nope").status_code == 404


def test_tickets_proxy(env):
    """Basic health and ticket proxy routes should stay wired."""

    client, _ = env
    assert client.get("/api/tickets").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}
