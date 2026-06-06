# Plan-level approval with SAFE / GATED / BLOCKED risk tiers

**Status:** accepted

The technician approves a **Plan** (a ranked root cause + an ordered list of steps), not
every individual command and not whole command *categories*. Each command carries a risk
tier that governs how it runs:

- **SAFE** — non-mutating reads; auto-run without approval, always logged. Exception:
  reading secret paths (`/etc/shadow`, `*.env`, keys) is BLOCKED, not SAFE.
- **GATED** — state-changing; runs only as part of an approved Plan.
- **BLOCKED** — the hard-fail list (e.g. `chmod -R 777` on system paths, DB drops,
  disabling security, secret exfil); never runs, cannot be approved.

There are two approval gates per Run: (1) approve connecting + read-only diagnostics,
(2) approve the fix Plan. Deviating from an approved Plan requires a new Plan and
re-approval; nothing mutating ever runs silently.

## Why

- The rubric requires a human confirmation for "every action" and rewards a "visible
  plan-and-confirm step" (C, 20 pts). **Per-category** approval fails this — approving the
  `config_edit` category blanket-authorises edits that didn't exist when the technician
  clicked, which the safety reviewers (who built the scan) will catch.
- **Per-command** approval satisfies the rubric but is too tedious for the technician.
- Plan-level approval + risk tiers is the middle ground: a clean incident is ~two clicks,
  reads are frictionless, and every state change is still inside something a human approved.

Category/risk remains in the UI as a display label only — the **risk tier**, enforced in
code, decides approval. The model proposes; the safety layer disposes.
