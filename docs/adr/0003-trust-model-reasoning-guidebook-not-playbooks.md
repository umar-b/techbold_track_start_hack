# ADR-0003: Trust the model to reason; guidebook is method + knowledge, not playbooks

**Date**: 2026-06-06
**Status**: accepted
**Deciders**: Team (umar-b + teammates)

## Context

Diagnosis quality drives the 35-point B block, graded on fresh, unseen incidents that reward
generalisation over hard-coding. The available model is small (`gpt-5.4-nano`), but stronger
models may be used later. We must decide how much of the reasoning to hard-code.

## Decision

The agent diagnoses by reasoning over live evidence, using a guidebook that supplies (a) a
diagnostic *method* — gather evidence → ranked hypotheses with evidence → cheapest-first test →
minimal fix → verify — and (b) reference knowledge of common Linux failure classes as facts it
may draw on, not forced branches. Safety (ADR-0002) and persistence (ADR-0005) stay code-enforced
invariants regardless of how the model reasons.

## Alternatives Considered

### Alternative 1: Hard-coded per-failure-class playbooks
- **Pros**: safer for a weak model on anticipated incidents.
- **Cons**: brittle on unanticipated incidents; looks like the hard-coding the grader is built to defeat; needs re-tuning per model.
- **Why not**: does not generalise to fresh incidents and is not model-agnostic.

### Alternative 2: Bare prompt, no guidebook
- **Pros**: simplest.
- **Cons**: a small model mis-ranks causes and proposes fragile or hallucinated fixes.
- **Why not**: diagnosis quality too low for the B block.

## Consequences

### Positive
- Generalises to unseen incidents; model-agnostic — swapping in a stronger model strictly improves results with no rewrite.

### Negative
- A small model reasoning freely can mis-diagnose.

### Risks
- nano mis-diagnosis. Mitigation: structured hypothesis-with-evidence output, context trimming of
  noisy command output, and memory that pre-fills plans only as hypotheses-to-verify (ADR-0009),
  never actions-to-apply.
