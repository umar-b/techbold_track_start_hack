#!/usr/bin/env python3
"""Smoke check 1/3 — Phoenix ERP auth + tickets.

Verifies the token works and you can list your assigned tickets.
Run:  python scripts/smoke/check_phoenix.py
"""
import json
import sys
import urllib.error
import urllib.request

from _env import load_env, require, ok, fail


def _get(base: str, path: str, token: str):
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, json.loads(resp.read().decode())


def main() -> int:
    load_env()
    base = require("PHOENIX_API_BASE_URL")
    token = require("PHOENIX_API_TOKEN")
    print(f"Phoenix: {base}")
    try:
        status, me = _get(base, "/api/v1/me", token)
        ok(f"/me -> {status}  {me.get('firstname','?')} {me.get('lastname','')} ({me.get('teamname','?')})")
    except urllib.error.HTTPError as e:
        fail(f"/me -> {e.code} {e.reason}. 401 => bad PHOENIX_API_TOKEN.")
        return 1
    except Exception as e:  # noqa: BLE001
        fail(f"/me unreachable: {e}. Check PHOENIX_API_BASE_URL / network.")
        return 1

    try:
        status, tickets = _get(base, "/api/v1/me/tickets", token)
        ok(f"/me/tickets -> {status}  {len(tickets)} ticket(s)")
        for t in tickets[:5]:
            print(f"     #{t.get('id')}  [{t.get('priority')}/{t.get('status')}]  {t.get('title')}")
    except Exception as e:  # noqa: BLE001
        fail(f"/me/tickets failed: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
