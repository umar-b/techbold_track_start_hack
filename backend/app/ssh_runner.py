"""SSH command runner (paramiko) with connect + per-command timeouts.

Executes a single command the technician has approved, over SSH. Connection and
command timeouts become a typed SSHError with a clear message. Per ADR's executor
note, each call is one self-contained command (paramiko `exec_command` does not
preserve shell state between calls). Key resolution supports a single shared key
or a per-VM `caseN_key.pem` convention.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import paramiko

from .config import settings


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int


class SSHError(RuntimeError):
    pass


def resolve_key_path(ticket_id: Optional[int] = None) -> str:
    """An explicit existing key wins; otherwise fall back to caseN_key.pem (N = ticket-7000)."""
    explicit = os.path.expanduser(settings.SSH_PRIVATE_KEY_PATH or "")
    if explicit and os.path.isfile(explicit):
        return explicit
    if ticket_id is not None:
        cand = os.path.join(os.path.expanduser(settings.SSH_KEY_DIR), f"case{ticket_id - 7000}_key.pem")
        if os.path.isfile(cand):
            return cand
    return explicit


def _load_key(path: str, passphrase: Optional[str]):
    last: Optional[Exception] = None
    for loader in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return loader.from_private_key_file(path, password=passphrase or None)
        except Exception as exc:  # noqa: BLE001 - try the next key type
            last = exc
    raise SSHError(f"Could not load SSH key at {path}: {last}")


class SSHRunner:
    def __init__(self, host: str, port: int = 22, username: Optional[str] = None,
                 key_path: Optional[str] = None, ticket_id: Optional[int] = None):
        self.host = host
        self.port = port or 22
        self.username = username or settings.SSH_USERNAME
        self.key_path = key_path or resolve_key_path(ticket_id)
        self._client: Optional[paramiko.SSHClient] = None

    @property
    def is_connected(self) -> bool:
        """True only if the channel is live — probes the transport, not just the handle."""
        if self._client is None:
            return False
        transport = self._client.get_transport()
        return transport is not None and transport.is_active()

    def ensure_connected(self, attempts: int = 2) -> "SSHRunner":
        """Connect if not already, tolerating a transient banner timeout.

        Holds the connect-retry policy that used to live in the route layer, so
        callers ask for a live runner without inspecting internals.
        """
        if self.is_connected:
            return self
        last: Optional[Exception] = None
        for _ in range(max(1, attempts)):
            try:
                return self.__enter__()
            except SSHError as exc:
                last = exc
        raise last  # type: ignore[misc]

    def __enter__(self) -> "SSHRunner":
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=self.host, port=self.port, username=self.username,
                pkey=_load_key(self.key_path, settings.SSH_KEY_PASSPHRASE),
                timeout=settings.SSH_CONNECT_TIMEOUT,
                banner_timeout=settings.SSH_CONNECT_TIMEOUT,
                auth_timeout=settings.SSH_CONNECT_TIMEOUT,
                look_for_keys=False, allow_agent=False,
            )
        except SSHError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SSHError(f"SSH connect to {self.username}@{self.host}:{self.port} failed: {exc}") from exc
        self._client = client
        return self

    def run(self, command: str, timeout: Optional[float] = None) -> CommandResult:
        if not self._client:
            raise SSHError("Not connected")
        timeout = timeout or settings.SSH_COMMAND_TIMEOUT
        start = time.time()
        try:
            _stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            code = stdout.channel.recv_exit_status()
        except Exception as exc:  # noqa: BLE001
            raise SSHError(f"Command failed or timed out: {exc}") from exc
        return CommandResult(out, err, code, int((time.time() - start) * 1000))

    def __exit__(self, *exc) -> None:
        if self._client:
            self._client.close()
            self._client = None
