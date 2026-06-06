# ADR-0010: Adopt LangChain as the agent framework (model-agnostic), replacing the custom loop

**Date**: 2026-06-06
**Status**: accepted
**Deciders**: Team (umar-b + teammates)
**Supersedes**: ADR-0006 · **Amends**: ADR-0007

## Context

The agent core is hand-rolled: a thin `llm.py` OpenAI-SDK wrapper (JSON mode), a custom
`propose_action` loop, and bespoke parse helpers (`_unwrap`, `_loads`). It works, but it is
Azure-locked (ADR-0006) and every primitive — request/parse, tool dispatch, message state,
structured output — is custom code we own. We want a standard, documented framework with
batteries-included agent/tool/structured-output abstractions, and model-agnostic provider swap
(Azure OpenAI today; Ollama / Groq / Gemini / Anthropic tomorrow) selected by config with no code
change. LangChain is open-source (MIT) and free, and its chat-model + `with_structured_output`
abstractions cover both goals.

## Decision

Rewrite the agent's model layer on **LangChain**. Replace the bespoke `llm.py` SDK wrapper with a
LangChain `BaseChatModel` built from config (`LLM_PROVIDER`, `LLM_MODEL`), defaulting to the Azure
`gpt-5.4-nano` v1 Foundry endpoint via `ChatOpenAI(base_url=…/openai/v1/)`. Keep the public
`llm.complete_json(system, user)` seam (returns a parsed dict or `None`) so the rest of the code is
unchanged; LangChain lives behind it. The deterministic safety/approval orchestration in `main.py`
(analyze → plan → approve → apply-once → verify → replan) and the single-agent design (ADR-0007)
stay — LangChain supplies the model/parse layer, not the control flow or the approval gate.

## Alternatives Considered

### Alternative 1: Keep the custom loop, add a thin provider adapter
- **Pros**: zero risk to the green test suite; portability met behind existing `llm.py`.
- **Cons**: no framework abstractions; we keep maintaining bespoke parse/tool/state code.
- **Why not**: rejected by decision — the team wants the framework itself, not just portability.

### Alternative 2: LangGraph (stateful graph) instead of plain LangChain
- **Pros**: explicit state machine matches analyze→plan→verify; checkpointing.
- **Cons**: heavier concept load; our control flow already lives cleanly in `main.py`.
- **Why not**: redundant with the existing orchestrator. Door stays open to adopt LangGraph later.

### Alternative 3: Provider-agnostic shim without a framework (LiteLLM)
- **Pros**: one-line model swap across many providers; minimal.
- **Cons**: a routing shim, not an agent framework — no tools/structured-output/agent primitives.
- **Why not**: solves portability only; the team wants the framework.

## Consequences

### Positive
- Standard, documented abstractions; less bespoke parse/dispatch code to own.
- True model-agnostic swap via config — reverses the ADR-0006 single-provider lock-in.
- Structured output handled by the framework instead of hand-rolled `_unwrap`/`_loads`.

### Negative
- Rewrites a working core; new heavy dependency tree (langchain + provider packages).
- Team takes on LangChain idioms.

### Risks
- **nano + structured output:** `with_structured_output` may route through tool-calling, which is
  unreliable on nano (ADR-0006 finding). Mitigation: use JSON mode
  (`with_structured_output(method="json_mode")` or `response_format={"type":"json_object"}`),
  keeping a tolerant parse as backstop.
- **Azure Foundry v1 parity through LangChain:** the v1 path needs a `base_url` override with no
  `api-version`. Mitigation: use `ChatOpenAI` with `base_url=endpoint+"/openai/v1/"` (not
  `AzureChatOpenAI`, which forces api-version); smoke-test before relying on it.
- **Regression:** a rewrite can break behaviour. Mitigation: port the existing test suite first and
  keep all tests green at every step; the public `complete_json` seam is preserved so blast radius
  stays in `llm.py` + its tests.
