"""Minimal .env loader for the smoke checks (stdlib only — no dependencies).

Loads KEY=VALUE lines from the repo-root .env into os.environ so the smoke
scripts "just work" after you fill in .env. Throwaway dev tooling.
"""
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
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
    value = os.environ.get(name)
    if not value:
        print(f"  MISSING env var: {name} (set it in .env)", file=sys.stderr)
        sys.exit(2)
    return value


def ok(msg: str) -> None:
    print(f"  \033[32mOK\033[0m  {msg}")


def fail(msg: str) -> None:
    print(f"  \033[31mFAIL\033[0m {msg}")
