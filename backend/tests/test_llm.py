"""Spec for the LLM wrapper — JSON parsing + graceful failure (no network)."""
import sys
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


def test_reasoning_flag_routes_to_reasoning_model(monkeypatch):
    # reasoning=True builds LLM_REASONING_MODEL; reasoning=False builds the fast model (ADR-0011).
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_PROVIDER", "azure-openai")
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", "k")
    monkeypatch.setattr(settings, "AZURE_OPENAI_ENDPOINT", "https://x")
    monkeypatch.setattr(settings, "AZURE_OPENAI_DEPLOYMENT", "fast-model")
    monkeypatch.setattr(settings, "LLM_MODEL", "")
    monkeypatch.setattr(settings, "LLM_REASONING_MODEL", "strong-model")
    built: list = []
    monkeypatch.setattr(llm, "_build_model",
                        lambda name: built.append(name) or _model(lambda m: _resp(content='{"action":"plan"}')))
    llm.complete_json("sys", "usr", reasoning=True)
    llm.complete_json("sys", "usr", reasoning=False)
    assert built == ["strong-model", "fast-model"]


def test_reasoning_falls_back_to_fast_model_when_unset(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_PROVIDER", "azure-openai")
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", "k")
    monkeypatch.setattr(settings, "AZURE_OPENAI_ENDPOINT", "https://x")
    monkeypatch.setattr(settings, "AZURE_OPENAI_DEPLOYMENT", "fast-model")
    monkeypatch.setattr(settings, "LLM_MODEL", "")
    monkeypatch.setattr(settings, "LLM_REASONING_MODEL", "")
    built: list = []
    monkeypatch.setattr(llm, "_build_model",
                        lambda name: built.append(name) or _model(lambda m: _resp(content="{}")))
    llm.complete_json("sys", "usr", reasoning=True)
    assert built == ["fast-model"]


def test_returns_none_without_credentials(monkeypatch):
    # No model passed and no creds -> None, never an exception or a network call.
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_PROVIDER", "azure-openai")
    monkeypatch.setattr(settings, "LLM_MODEL", "")
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setattr(settings, "AZURE_OPENAI_DEPLOYMENT", "")
    assert llm.complete_json("sys", "usr") is None


def test_tolerates_single_line_fenced_json():
    # A single-line code fence (```{...}```) must still parse — regression guard for
    # the _loads rewrite, which previously reduced this form to an empty string.
    model = _model(lambda messages: _resp(content='```{"action":"diagnose","command":"ss -tlnp"}```'))
    out = llm.complete_json("sys", "usr", model=model)
    assert out["action"] == "diagnose"
    assert out["command"] == "ss -tlnp"


def test_tolerates_duplicated_json_object():
    # gpt-5.x with json_object mode sometimes emits the object TWICE, concatenated.
    # Parse the FIRST one instead of failing and silently degrading to the baseline.
    dup = ('{"action":"diagnose","command":"systemctl status x"}\n'
           '{"action":"diagnose","command":"systemctl status x"}')
    model = _model(lambda messages: _resp(content=dup))
    out = llm.complete_json("sys", "usr", model=model)
    assert out["action"] == "diagnose"
    assert out["command"] == "systemctl status x"


def _fake_chat_openai(record):
    """A stand-in langchain_openai module whose ChatOpenAI records its kwargs."""
    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            record(kwargs)

        def bind(self, **_kwargs):
            return self

    mod = types.ModuleType("langchain_openai")
    mod.ChatOpenAI = _FakeChatOpenAI
    return mod


def _azure_settings(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_PROVIDER", "azure-openai")
    monkeypatch.setattr(settings, "AZURE_OPENAI_ENDPOINT", "https://x")
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", "k")


def test_azure_model_is_built_without_temperature(monkeypatch):
    # gpt-5.x / o-series reasoning models reject a non-default temperature with a 400,
    # and langchain-openai<0.3.28 forwards it verbatim — so the azure path must not
    # send temperature at all (ADR-0011 regression guard for the CRITICAL bug).
    captured: dict = {}
    monkeypatch.setitem(sys.modules, "langchain_openai", _fake_chat_openai(captured.update))
    _azure_settings(monkeypatch)
    llm._model_cache.clear()

    llm._build_model("gpt-5.4")
    assert "temperature" not in captured
    assert captured["model"] == "gpt-5.4"
    llm._model_cache.clear()


def test_build_model_caches_per_model(monkeypatch):
    # The agent builds a model on every step; the client (and its connection pool)
    # must be reused, not reconstructed each call.
    calls: list = []
    monkeypatch.setitem(sys.modules, "langchain_openai",
                        _fake_chat_openai(lambda kw: calls.append(kw.get("model"))))
    _azure_settings(monkeypatch)
    llm._model_cache.clear()

    llm._build_model("gpt-5.4")
    llm._build_model("gpt-5.4")
    assert calls == ["gpt-5.4"]  # built once; second call served from cache
    llm._model_cache.clear()
