"""Command safety layer (ADR-0002, ADR-0004).

Classifies every proposed shell command into a risk tier BEFORE it can run:

  SAFE    - non-mutating reads; may auto-run, always logged.
  GATED   - state-changing; runs only inside a technician-approved Plan.
  BLOCKED - dangerous or secret-exposing; never runs, cannot be approved.

The model proposes, this layer disposes. Classification ignores a leading
`sudo`/`env` prefix so privilege escalation cannot smuggle a command past the
checks. Only *blanket* operations on system roots are BLOCKED — a targeted op on
a narrow application path (e.g. `chown -R app /var/www/app/uploads`) is GATED, so
the technician can still approve it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class RiskTier(str, Enum):
    """Risk levels shown to the technician and enforced by the backend."""

    SAFE = "SAFE"
    GATED = "GATED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class SafetyVerdict:
    """The safety decision for one proposed command."""

    tier: RiskTier
    reason: str = ""

    @property
    def allowed(self) -> bool:
        """Convenience flag for code that only needs blocked vs not blocked."""

        return self.tier is not RiskTier.BLOCKED


# A system root as the *whole* target, or DB/log data dirs at any depth.
# Deliberately does NOT match deep app paths like /var/www/app/uploads.
_BLANKET = (
    r"(?:"
    r"/(?:\s|$)"
    r"|/(?:etc|usr|var|bin|sbin|boot|lib|lib64|sys|proc|root|srv|home|opt)/?(?=\s|$|[;&|])"
    r"|/var/lib/(?:postgresql|mysql)\S*"
    r"|/var/log(?:/\S*)?"
    r")"
)
_RECURSIVE = r"(?:-\w*[rR]\w*|--recursive)"

# Checked against the whole normalized command because these are always unsafe.
_BLOCK_WHOLE = [
    (r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "Fork bomb"),
    (r"\bmkfs(?:\.\w+)?\b", "Filesystem format"),
    (r"\bdd\b.*\bof=/dev/", "Raw write to a block device"),
    (r"\b(?:drop|truncate)\s+(?:database|table|schema)\b", "Destroying database objects"),
    (r"\b(?:dropdb|pg_resetwal|initdb)\b", "Reinitialising a database"),
    (r"\bsystemctl\s+(?:stop|disable|mask)\s+(?:ufw|firewalld|auditd|apparmor|ssh|sshd)\b",
     "Disabling a security/SSH service"),
    (r"\bufw\s+disable\b", "Disabling the firewall"),
    (r"\bhistory\s+-c\b", "Clearing shell history (hiding actions)"),
]

# Checked per shell segment so one target does not accidentally affect another.
_BLOCK_SEG = [
    (rf"\brm\b.*{_RECURSIVE}.*{_BLANKET}", "Recursive delete of a system path"),
    (rf"\bchmod\b(?=.*{_RECURSIVE})(?=.*\b0?777\b).*{_BLANKET}", "Blanket chmod 777 on a system path"),
    (rf"\bchown\b.*{_RECURSIVE}.*{_BLANKET}", "Recursive chown of a system path"),
]

# Any reference to these paths is treated as secret access and BLOCKED.
_SECRET_PATH = re.compile(
    r"(?:/etc/g?shadow\b|\bid_rsa\b|\bid_dsa\b|\bid_ecdsa\b|\bid_ed25519\b"
    r"|/etc/ssh/ssh_host_\w+_key\b|\S+\.pem\b|\S+\.key\b|(?:^|[/\s])\.env\b|/[\w./-]*\.env\b)",
    re.IGNORECASE,
)

# Commands in this set can be SAFE, but some subcommands below are still writes.
_SAFE_BINS = {
    "cat", "ls", "head", "tail", "grep", "egrep", "fgrep", "zgrep", "less", "more",
    "wc", "cut", "sort", "uniq", "tr", "stat", "file", "readlink", "realpath",
    "df", "du", "free", "ps", "uptime", "uname", "hostname", "whoami", "id", "w",
    "who", "date", "env", "printenv", "getent", "dig", "nslookup", "host", "ss",
    "netstat", "lsof", "lsblk", "pgrep", "dmesg", "journalctl", "vmstat", "iostat",
    "echo", "pwd", "cd", "which", "type", "true", "test", "lsmod", "ip", "ifconfig",
    "ping", "curl", "tracepath", "traceroute", "find", "awk", "sed",
    "systemctl", "service", "apt", "apt-get", "dpkg", "pip", "pip3",
}

# Prefixes do not change the real command, so strip them before classifying.
_PREFIX = {"sudo", "env", "time", "nice", "nohup", "ionice"}


def _split_segments(cmd: str) -> list:
    """Split on shell operators (; | || &&) that are OUTSIDE quotes.

    Quote-aware so operators inside an awk/sed program or a quoted string don't
    fracture the command (which would mis-classify a read-only pipeline as GATED).
    A single `&` (e.g. `2>&1`, backgrounding) is kept, not treated as a separator.
    """
    segs, buf, quote, i = [], "", None, 0
    while i < len(cmd):
        c = cmd[i]
        if quote:
            buf += c
            if c == quote:
                quote = None
            i += 1
        elif c in ("'", '"'):
            quote = c
            buf += c
            i += 1
        elif c == ";":
            segs.append(buf)
            buf = ""
            i += 1
        elif c == "|":
            segs.append(buf)
            buf = ""
            i += 2 if cmd[i:i + 2] == "||" else 1
        elif cmd[i:i + 2] == "&&":
            segs.append(buf)
            buf = ""
            i += 2
        else:
            buf += c
            i += 1
    segs.append(buf)
    return [s for s in segs if s.strip()]


def _strip_prefix(seg: str) -> str:
    """Remove harmless command prefixes before checking the real command."""

    toks = seg.split()
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in _PREFIX or (t and t[0].isalpha() and "=" in t):
            i += 1
        elif i > 0 and toks[i - 1] == "sudo" and t.startswith("-"):
            i += 1
        else:
            break
    return " ".join(toks[i:])


def _segment_safe(seg: str) -> bool:
    """Return True when one shell segment looks read-only."""

    s = _strip_prefix(seg).strip()
    if not s:
        return True
    # A redirection to a real file (not 2>&1 / >/dev/null) or tee is a write.
    if re.search(r"(?<!2)>>?\s*(?!/dev/null\b)\S", s) or re.search(r"\btee\b", s):
        return False
    toks = s.split()
    binexe = toks[0].rsplit("/", 1)[-1]
    if binexe not in _SAFE_BINS:
        return False
    sub = toks[1] if len(toks) > 1 else ""
    if binexe == "systemctl":
        # The verb is the first NON-option token; options may precede it
        # (`systemctl --type=service --state=running` , `systemctl --no-pager status x`).
        verb = next((t for t in toks[1:] if not t.startswith("-")), "")
        # No verb at all -> an implied `list-units` (read-only). Otherwise allow the
        # read-only verbs only; anything else (start/stop/enable/restart/…) is GATED.
        return verb == "" or verb in {
            "status", "is-active", "is-enabled", "is-failed", "is-system-running",
            "list-units", "list-unit-files", "list-timers", "list-sockets",
            "list-dependencies", "show", "cat", "show-environment",
        }
    if binexe == "service":
        return sub == "status" or s.endswith(" status")
    if binexe == "sed":
        return not any(t == "-i" or t.startswith("-i") for t in toks)
    if binexe in {"ip", "ifconfig"}:
        return not re.search(r"\b(add|del|delete|set|flush|up|down|change|replace)\b", s)
    if binexe in {"apt", "apt-get"}:
        return sub in {"list", "show", "policy"}
    if binexe == "dpkg":
        return any(f in toks for f in ("-l", "-L", "-s", "--list", "--status"))
    if binexe in {"pip", "pip3"}:
        return sub in {"list", "show", "freeze"}
    if binexe == "curl":
        if re.search(r"\s-(?:d|F|T|o|O)\b|--data|--output|--upload-file", s):
            return False
        if re.search(r"-X\s*(?:POST|PUT|DELETE|PATCH)", s, re.IGNORECASE):
            return False
        return True
    if binexe == "find":
        return not re.search(r"\b-(?:delete|exec|execdir|fprint|fputs)\b", s)
    return True


def check_command(command: str) -> SafetyVerdict:
    """Classify a proposed shell command into a SAFE / GATED / BLOCKED verdict."""

    cmd = " ".join((command or "").split())
    if not cmd:
        return SafetyVerdict(RiskTier.BLOCKED, "Empty command")
    if _SECRET_PATH.search(cmd):
        return SafetyVerdict(RiskTier.BLOCKED, "Accessing a secret/credential path")
    for pat, reason in _BLOCK_WHOLE:
        if re.search(pat, cmd, re.IGNORECASE):
            return SafetyVerdict(RiskTier.BLOCKED, reason)
    segments = _split_segments(cmd)
    for seg in segments:
        for pat, reason in _BLOCK_SEG:
            if re.search(pat, seg, re.IGNORECASE):
                return SafetyVerdict(RiskTier.BLOCKED, reason)
    if segments and all(_segment_safe(s) for s in segments):
        return SafetyVerdict(RiskTier.SAFE, "Read-only diagnostic")
    return SafetyVerdict(RiskTier.GATED, "State-changing — requires an approved plan")
