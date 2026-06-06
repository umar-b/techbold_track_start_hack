"""Spec for the Phoenix ERP client — auth, retries, error mapping (mocked, no network)."""
import httpx
import pytest

from app.phoenix_client import PhoenixClient, PhoenixError


def make_client(handler, retries=2):
    """Create a Phoenix client backed by an httpx mock transport."""

    return PhoenixClient(base_url="http://erp.test", token="tok", retries=retries,
                         backoff=0.0, transport=httpx.MockTransport(handler))


def test_lists_tickets_with_bearer_and_query():
    """Ticket listing should send auth and the chosen query parameters."""

    seen = {}

    def handler(req):
        """Capture auth and URL, then return one ticket."""

        seen["auth"] = req.headers.get("authorization")
        seen["url"] = str(req.url)
        return httpx.Response(200, json=[{"id": 7001, "title": "x"}])

    tickets = make_client(handler).list_tickets(status="OPEN", sort="priority")
    assert tickets[0]["id"] == 7001
    assert seen["auth"] == "Bearer tok"
    assert "status=OPEN" in seen["url"] and "sort=priority" in seen["url"]


def test_404_raises_and_is_not_retried():
    """Client errors are final because retrying bad input wastes time."""

    calls = {"n": 0}

    def handler(req):
        """Always return a client error so retry count can be checked."""

        calls["n"] += 1
        return httpx.Response(404, json={"detail": "nope"})

    with pytest.raises(PhoenixError):
        make_client(handler).get_ticket(9999)
    assert calls["n"] == 1  # client errors are surfaced, never retried


def test_5xx_is_retried_then_raises():
    """Server errors are retried a small number of times before failing."""

    calls = {"n": 0}

    def handler(req):
        """Always return a server error so retry behavior can be checked."""

        calls["n"] += 1
        return httpx.Response(503, text="busy")

    with pytest.raises(PhoenixError):
        make_client(handler, retries=2).me()
    assert calls["n"] == 3  # 1 try + 2 retries


def test_status_and_activity_use_correct_verbs_and_paths():
    """Write operations should hit the Phoenix paths required by the case."""

    seen = []

    def handler(req):
        """Record the method and path for each write request."""

        seen.append((req.method, req.url.path))
        return httpx.Response(200, json={"ok": True})

    c = make_client(handler)
    c.set_status(7001, "DONE")
    c.create_activity({"ticket_id": 7001})
    assert ("PATCH", "/api/v1/tickets/7001/status") in seen
    assert ("POST", "/api/v1/activities/create") in seen


def test_customer_system_path():
    """The customer-system endpoint should return SSH target details."""

    def handler(req):
        """Return the customer-system response shape from Phoenix."""

        return httpx.Response(200, json={"ticket_id": 7001, "system": {"ip": "1.2.3.4"}})

    out = make_client(handler).customer_system(7001)
    assert out["system"]["ip"] == "1.2.3.4"
