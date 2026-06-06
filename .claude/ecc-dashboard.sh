#!/usr/bin/env bash
# Launch the ECC Tkinter dashboard (Agents / Skills / Commands / Rules / Settings).
# The dashboard must run from the ECC repo root so its `scripts.lib.*` imports resolve.
set -euo pipefail

ECC_REPO="${ECC_REPO:-$HOME/.claude/plugins/marketplaces/ecc}"

if [[ ! -f "$ECC_REPO/ecc_dashboard.py" ]]; then
  echo "ECC repo not found at: $ECC_REPO" >&2
  echo "Set ECC_REPO to your ECC marketplace/clone path and retry." >&2
  exit 1
fi

cd "$ECC_REPO"
exec python3 ./ecc_dashboard.py
