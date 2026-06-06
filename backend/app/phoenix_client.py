"""Client for the Phoenix ERP mock API (ADR-0008).

All ERP access is encapsulated here — routes and the agent never call the ERP
directly. Includes per-request timeouts and a small bounded retry for transient
5xx / network errors; client errors (401/404/422) are surfaced immediately as a
typed PhoenixError and never retried.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from .config import settings

log = logging.getLogger("phoenix")


class PhoenixError(RuntimeError):
    """Any non-2xx ERP response or network failure."""


class PhoenixClient:
    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None,
                 retries: Optional[int] = None, backoff: float = 0.5,
                 timeout: Optional[float] = None, transport: Optional[httpx.BaseTransport] = None):
        self.base_url = (base_url or settings.PHOENIX_API_BASE_URL).rstrip("/")
        self.token = token if token is not None else settings.PHOENIX_API_TOKEN
        self.retries = settings.HTTP_RETRIES if retries is None else retries
        self.backoff = backoff
        self._client = httpx.Client(timeout=timeout or settings.HTTP_TIMEOUT_SECONDS,
                                    transport=transport)

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        last: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                resp = self._client.request(method, url, headers=self._headers(), **kwargs)
                if resp.status_code >= 500:
                    raise PhoenixError(f"{method} {path} -> {resp.status_code}")
                if resp.status_code >= 400:
                    raise PhoenixError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}")
                return resp.json() if resp.content else None
            except PhoenixError as exc:
                last = exc
                transient = " -> 5" in str(exc)
                if transient and attempt < self.retries:
                    if self.backoff:
                        time.sleep(self.backoff * (attempt + 1))
                    log.warning("Phoenix %s %s transient (attempt %d), retrying", method, path, attempt + 1)
                    continue
                raise
            except httpx.HTTPError as exc:
                last = exc
                if attempt < self.retries:
                    if self.backoff:
                        time.sleep(self.backoff * (attempt + 1))
                    continue
                raise PhoenixError(f"{method} {path} network error: {exc}") from exc
        raise PhoenixError(f"{method} {path} failed after retries: {last}")

    # ---- read ----
    def me(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/me")

    def list_tickets(self, status: Optional[str] = None, priority: Optional[str] = None,
                     sort: str = "date") -> List[Dict[str, Any]]:
        params: Dict[str, str] = {"sort": sort}
        if status:
            params["status"] = status
        if priority:
            params["priority"] = priority
        return self._request("GET", "/api/v1/me/tickets", params=params)

    def get_ticket(self, ticket_id: int) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/tickets/{ticket_id}")

    def customer_system(self, ticket_id: int) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/tickets/{ticket_id}/customer-system")

    def get_customer(self, customer_id: int) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/customers/{customer_id}")

    # ---- write ----
    def set_status(self, ticket_id: int, status: str) -> Dict[str, Any]:
        return self._request("PATCH", f"/api/v1/tickets/{ticket_id}/status", json={"status": status})

    def create_activity(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/activities/create", json=payload)

    def close(self) -> None:
        self._client.close()
