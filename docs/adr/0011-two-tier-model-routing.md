# ADR-0011: Two-tier model routing — fast model for diagnosis, reasoning model for planning

**Date**: 2026-06-06
**Status**: accepted
**Deciders**: Team (umar-b + teammates)
**Refines**: ADR-0010 · **Revisits**: ADR-0006 (which ruled out routing when only one deployment existed)

## Context

Live testing showed `gpt-5.4-nano` diagnoses competently but does not reliably converge to a
fix — it over-diagnoses and rarely commits to a correct, persistent plan (the score bottleneck is
reasoning quality at the planning step, not infrastructure). The track later provided a second,
stronger deployment, `gpt-5.4`, on the same Azure resource and key. Verified live: `gpt-5.4`
answers on the same OpenAI-compatible `/chat/completions` path with `response_format=json_object`
— identical to the nano path — so routing costs no new code path. The stronger model is more
expensive, so it must be used sparingly.

## Decision

Route by step. Diagnosis (frequent, cheap, read-only evidence gathering) uses the **fast** model
(`LLM_MODEL` / `AZURE_OPENAI_DEPLOYMENT`, e.g. `gpt-5.4-nano`). The **plan/replan** step — where
the agent synthesises evidence into a root cause and an ordered fix — uses the **reasoning** model
(`LLM_REASONING_MODEL`, e.g. `gpt-5.4`). `llm.complete_json(..., reasoning: bool)` selects the
model; the agent passes `reasoning=must_plan`, so only the forced-convergence and replan calls pay
for the stronger model. Empty `LLM_REASONING_MODEL` disables routing (fast model everywhere). Both
tiers use the same provider/endpoint/key and the same JSON-mode path (ADR-0010).

## Alternatives Considered

### Alternative 1: One model for everything (status quo, ADR-0006)
- **Pros**: simplest; one deployment.
- **Cons**: nano under-converges on planning; gpt-5.4 everywhere burns tokens on cheap diagnosis steps.
- **Why not**: routing targets the exact bottleneck (planning) while keeping diagnosis cheap.

### Alternative 2: Strong model for every step
- **Pros**: best raw quality.
- **Cons**: token cost on a long diagnose loop (`AGENT_MAX_STEPS=25`); the track explicitly warned to use the strong model sparingly.
- **Why not**: most steps are read-only diagnostics where nano is adequate.

### Alternative 3: Let the model self-select / a separate "should I plan yet?" call
- **Pros**: could pick the tier per content.
- **Cons**: an extra round-trip per step, more latency and tokens, more failure surface.
- **Why not**: `must_plan` (forced convergence after the diagnose soft-limit) is a good-enough, deterministic routing signal.

## Consequences

### Positive
- Stronger reasoning exactly where convergence was failing, at minimal added token cost.
- Zero new code path: same provider/endpoint/key/JSON-mode seam, just a different model string.
- Model-agnostic (ADR-0010) preserved — the reasoning tier works for any provider via `LLM_REASONING_MODEL`.

### Negative
- Two model names to configure; a misconfigured reasoning model silently falls back to the fast one.
- Plans proposed by nano *before* the soft-limit still use the fast model (acceptable — forced convergence catches the rest).

### Risks
- `gpt-5.4` latency/quota on the plan step could slow a run. Mitigation: it fires only on plan/replan, not per diagnostic; existing timeouts apply.
- Embeddings (`text-embedding-3-large`) are available on the same resource but remain **unwired** —
  memory is a markdown graph (ADR-0001) and is not on the scoring path. Config keys exist so
  semantic recall is a later config-plus-small-client change, not a rework. Revisit only if recall
  quality demands it.
