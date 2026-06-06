# ADR-0009: Memory seeds plans as hypotheses-to-verify, never as actions-to-apply

**Date**: 2026-06-06
**Status**: accepted
**Deciders**: Team (umar-b + teammates)

## Context

A confident memory match can mislead the agent on a fresh VM — the remembered fix may not match
the actual cause — which would lower the B score. The differentiator could hurt the metric it is
meant to help. We must define exactly how retrieved memory enters the loop. Builds on ADR-0001
(storage) and ADR-0002 (approval).

## Decision

Retrieved notes enter as **ranked hypotheses-to-verify with their evidence**, and may **pre-fill**
the proposed Plan for a high-confidence match — but never skip verification or the approval gate.
The agent confirms current evidence before a remembered fix enters the Plan, and a memory-originated
step is identical to a fresh step at every gate. If the memory plan fails: discard it and re-plan
from live evidence; after a bounded number of failed approaches, **escalate to the technician**.
Failed attempts are recorded back to the note.

## Alternatives Considered

### Alternative 1: Memory seeds actions that auto-execute on high confidence
- **Pros**: fastest resolution on repeat incidents.
- **Cons**: confident-wrong on fresh VMs; violates the plan-approval gate (ADR-0002).
- **Why not**: turns the differentiator into a B-score risk.

### Alternative 2: Memory shown to the technician only, not fed to the agent
- **Pros**: zero misdirection risk.
- **Cons**: wastes the speed-up; the agent re-derives everything.
- **Why not**: forgoes the value of memory.

## Consequences

### Positive
- Memory strictly accelerates *correct* diagnosis; it cannot cause a confident-wrong fix; pre-fill keeps the demo fast.

### Negative
- A re-plan loop adds gates when the first approach fails.

### Risks
- Infinite re-planning. Mitigation: bounded attempts then escalate; each new Plan is re-approved.
