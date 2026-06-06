"""Spec for the LLM wrapper — JSON parsing + graceful failure (no network)."""
import types

from app import llm


def _resp(content=None):
    return types.SimpleNamespace(content=content)


def _model(fn):
    return types.SimpleNamespace(invoke=fn)


def test_returns_parsed_json_content():
    model = _model(lambda messages: _resp(content='{"action":"finish","summary":"ok"}'))
    out = llm.complete_json("sys", "usr", model=model)
    assert out["action"] == "finish"


def test_tolerates_code_fenced_json():
    model = _model(lambda messages: _resp(content='```json\n{"action":"plan"}\n```'))
    out = llm.complete_json("sys", "usr", model=model)
    assert out["action"] == "plan"


def test_returns_none_when_invoke_raises():
    def boom(messages):
        raise RuntimeError("api down")
    out = llm.complete_json("sys", "usr", model=_model(boom))
    assert out is None


def test_returns_none_when_content_is_not_a_string():
    # LangChain types content as `str | list`; non-OpenAI providers may return
    # content blocks. A non-string must yield None, never an AttributeError.
    model = _model(lambda messages: _resp(content=[{"type": "text", "text": '{"action":"plan"}'}]))
    assert llm.complete_json("sys", "usr", model=model) is None


def test_returns_none_without_credentials(monkeypatch):
    # No model passed and no creds -> None, never an exception or a network call.
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_PROVIDER", "azure-openai")
    monkeypatch.setattr(settings, "LLM_MODEL", "")
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setattr(settings, "AZURE_OPENAI_DEPLOYMENT", "")
    assert llm.complete_json("sys", "usr") is None
