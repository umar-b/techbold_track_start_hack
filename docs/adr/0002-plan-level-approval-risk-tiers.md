# ADR-0002: Plan-level approval with SAFE / GATED / BLOCKED risk tiers

**Date**: 2026-06-06
**Status**: accepted
**Deciders**: Team (umar-b + teammates)

## Context

The rubric requires a human confirmation for "every action" and rewards a visible
plan-and-confirm step (C, 20 pts). The technician must stay in control without per-command
tedium. We need an approval model that is both safe and usable.

## Decision

The technician approves a **Plan** (a ranked root cause + an ordered list of steps), not
individual commands and not whole command categories. Each command carries a risk tier: **SAFE**
(non-mutating reads — auto-run, always logged), **GATED** (state-changing — runs only inside an
approved Plan), **BLOCKED** (hard-fail list — never runs). Two gates per Run: approve
connect + diagnostics, then approve the fix Plan. Deviating from an approved Plan requires a new
Plan and re-approval.

## Alternatives Considered

### Alternative 1: Per-category approval
- **Pros**: fewest clicks.
- **Cons**: approving the `config_edit` category blanket-authorises edits that did not exist at approval time; breaks "every action confirmed".
- **Why not**: fails the rubric's human-control intent; the safety reviewers (who built the scan) will catch it.

### Alternative 2: Per-command approval
- **Pros**: most literal "confirm every action"; bulletproof to a strict reviewer.
- **Cons**: tedious for the technician across a multi-step fix.
- **Why not**: rejected as too tedious; plan-level approval plus auto-run reads achieves control with far less friction.

## Consequences

### Positive
- A clean incident is ~two clicks; reads are frictionless; every state change is inside something a human approved.
- The risk tier is enforced in code, not by the model — the model proposes, the safety layer disposes.

### Negative
- Auto-running SAFE reads is slightly less literal than confirming every single command.

### Risks
- A strict safety reviewer could question auto-run reads. Mitigation: the connect + diagnostics
  gate explicitly authorises read-only exploration, and secret-file reads are BLOCKED regardless
  of tier (ADR-0004).
