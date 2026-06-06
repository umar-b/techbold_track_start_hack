"""SSH command runner with clear timeouts.

The backend uses this only after the safety layer and approval gate allow a
command. Each call is one self-contained shell command; SSH does not remember
state like `cd` between calls.
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
    """Output from one SSH command."""

    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int


class SSHError(RuntimeError):
    """Raised when connecting or running a command fails."""

    pass


def resolve_key_path(ticket_id: Optional[int] = None) -> str:
    """Choose the shared key first, then fall back to caseN_key.pem."""

    explicit = os.path.expanduser(settings.SSH_PRIVATE_KEY_PATH or "")
    if explicit and os.path.isfile(explicit):
        return explicit
    if ticket_id is not None:
        cand = os.path.join(os.path.expanduser(settings.SSH_KEY_DIR), f"case{ticket_id - 7000}_key.pem")
        if os.path.isfile(cand):
            return cand
    return explicit


def _load_key(path: str, passphrase: Optional[str]):
    """Try the common SSH key formats used by the hackathon VMs."""

    last: Optional[Exception] = None
    for loader in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return loader.from_private_key_file(path, password=passphrase or None)
        except Exception as exc:  # noqa: BLE001 - try the next key type
            last = exc
    raise SSHError(f"Could not load SSH key at {path}: {last}")


class SSHRunner:
    """Context manager that opens one SSH connection and runs commands on it."""

    def __init__(self, host: str, port: int = 22, username: Optional[str] = None,
                 key_path: Optional[str] = None, ticket_id: Optional[int] = None):
        """Store connection settings without opening the network connection yet."""

        self.host = host
        self.port = port or 22
        self.username = username or settings.SSH_USERNAME
        self.key_path = key_path or resolve_key_path(ticket_id)
        self._client: Optional[paramiko.SSHClient] = None

    def __enter__(self) -> "SSHRunner":
        """Open the SSH connection with strict timeouts and no agent fallback."""

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
        """Run one command and return stdout, stderr, exit code, and duration."""

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
        """Close the SSH connection when the run is done or aborted."""

        if self._client:
            self._client.close()
            self._client = None
