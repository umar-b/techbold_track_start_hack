"""Minimal .env loader for smoke checks.

The smoke scripts use only the standard library, so they cannot rely on the
backend's pydantic settings loader.
"""
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    """Load KEY=VALUE lines from the repo-root .env into os.environ."""

    env_path = _REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def require(name: str) -> str:
    """Return a required env var or stop the smoke check with a clear message."""

    value = os.environ.get(name)
    if not value:
        print(f"  MISSING env var: {name} (set it in .env)", file=sys.stderr)
        sys.exit(2)
    return value


def ok(msg: str) -> None:
    """Print a green OK line for a successful smoke-check step."""

    print(f"  \033[32mOK\033[0m  {msg}")


def fail(msg: str) -> None:
    """Print a red FAIL line for a failed smoke-check step."""

    print(f"  \033[31mFAIL\033[0m {msg}")
