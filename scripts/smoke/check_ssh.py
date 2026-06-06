#!/usr/bin/env python3
"""Smoke check 2/3 — SSH into a customer VM and run a read-only command.

By default it pulls the SSH target from your first ticket's customer-system via
Phoenix, then connects and runs `uname -a` + `id`. Override with --host.

Run:  python scripts/smoke/check_ssh.py
      python scripts/smoke/check_ssh.py --host 10.0.0.5 --port 22
      python scripts/smoke/check_ssh.py --ticket 7001
"""
import argparse
import json
import sys
import urllib.request

from _env import load_env, require, ok, fail


def _phoenix_system(ticket_id=None):
    """Find the SSH target from Phoenix when the user did not pass --host."""

    base = require("PHOENIX_API_BASE_URL").rstrip("/")
    token = require("PHOENIX_API_TOKEN")
    hdr = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if ticket_id is None:
        req = urllib.request.Request(f"{base}/api/v1/me/tickets", headers=hdr)
        with urllib.request.urlopen(req, timeout=15) as r:
            tickets = json.loads(r.read().decode())
        if not tickets:
            fail("No tickets to derive an SSH target from. Use --host.")
            sys.exit(1)
        ticket_id = tickets[0]["id"]
    req = urllib.request.Request(f"{base}/api/v1/tickets/{ticket_id}/customer-system", headers=hdr)
    with urllib.request.urlopen(req, timeout=15) as r:
        sysinfo = json.loads(r.read().decode()).get("system", {})
    print(f"  target from ticket #{ticket_id}: {sysinfo.get('ip')}:{sysinfo.get('port')} ({sysinfo.get('os')})")
    return sysinfo.get("ip"), sysinfo.get("port", 22), sysinfo.get("username")


def main() -> int:
    """Connect to a VM and run only read-only commands."""

    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--host")
    ap.add_argument("--port", type=int, default=22)
    ap.add_argument("--ticket", type=int)
    args = ap.parse_args()

    try:
        import paramiko
    except ImportError:
        fail("paramiko not installed. Run: pip install paramiko")
        return 2

    key_path = require("SSH_PRIVATE_KEY_PATH")
    username = require("SSH_USERNAME")
    if args.host:
        host, port = args.host, args.port
    else:
        host, port, sys_user = _phoenix_system(args.ticket)
        username = sys_user or username
    if not host:
        fail("No host. Pass --host or ensure the ticket has a customer-system.")
        return 1

    print(f"SSH: {username}@{host}:{port}  key={key_path}")
    key = None
    for loader in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            key = loader.from_private_key_file(key_path)
            break
        except Exception:  # noqa: BLE001
            continue
    if key is None:
        fail(f"Could not load SSH key at {key_path} (tried Ed25519/RSA/ECDSA).")
        return 1

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(hostname=host, port=port, username=username, pkey=key,
                       timeout=15, banner_timeout=15, auth_timeout=15,
                       look_for_keys=False, allow_agent=False)
    except Exception as e:  # noqa: BLE001
        fail(f"connect failed: {e}. Check key, username (azureuser?), and reachability.")
        return 1

    for cmd in ("uname -a", "id", "sudo -n true && echo 'passwordless-sudo: yes' || echo 'passwordless-sudo: no'"):
        _in, out, err = client.exec_command(cmd, timeout=15)
        text = (out.read().decode() + err.read().decode()).strip()
        ok(f"$ {cmd}\n       {text}")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
