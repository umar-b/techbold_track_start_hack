# ADR-0006: Single LLM provider (Azure OpenAI), no provider abstraction

**Date**: 2026-06-06
**Status**: accepted
**Deciders**: Team (umar-b + teammates)

## Context

No LLM credentials are provided by the track; the team brings its own. The team has an Azure
OpenAI key with a `gpt-5.4-nano` deployment. A multi-provider abstraction means building and
testing code paths we will never demo on, in a time-boxed build.

## Decision

Commit to **Azure OpenAI** as the only provider, behind a single thin `llm.py`
(`chat(messages, tools)`) so the rest of the code never imports the SDK directly. Use native
function/tool calling, with a strict-JSON-schema prompt as the fallback if tool-calling misbehaves
on the deployment. One deployment serves everything — no model routing (Azure models are
per-deployment).

## Alternatives Considered

### Alternative 1: Provider-agnostic abstraction (Anthropic / OpenAI / Azure / Ollama)
- **Pros**: swap providers freely.
- **Cons**: four code paths to build and test; only one is used at judging.
- **Why not**: gold-plating — the thin `llm.py` keeps the door open without the cost.

### Alternative 2: Per-tier model routing (cheap model for chatty steps)
- **Pros**: lower cost/latency on simple steps.
- **Cons**: each Azure model is a separate deployment we likely do not have.
- **Why not**: not available; a single capable deployment is simpler.

## Consequences

### Positive
- Minimal surface: one key, one deployment, the rest of the code provider-clean via `llm.py`.

### Negative
- Locked to Azure for the build; another provider needs a new `llm.py` path.

### Risks
- nano may not support tool calling on the given `api_version`. Mitigation: verify early; design
  the strict-JSON fallback from the start.

## Update — verified configuration (2026-06-06)

Smoke checks confirmed the deployment is an **Azure AI Foundry project** endpoint
(`…services.ai.azure.com/api/projects/…`) served over the **OpenAI-compatible v1 API**:
- Call `POST {endpoint}/openai/v1/chat/completions` with `model=<deployment>` and **no
  `api-version`** (the classic `…openai.azure.com` + api-version path returns 400). `llm.py`
  uses the `openai` SDK's `OpenAI(base_url=endpoint + "/openai/v1/")` client.
- **JSON mode works**; **native tool-calling does NOT reliably fire on nano** (returns text), so
  JSON mode is the primary path — exactly the fallback this ADR anticipated.
- Both `Authorization: Bearer` and `api-key` headers authenticate; `temperature` is accepted.
