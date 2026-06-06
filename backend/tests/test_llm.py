"""Spec for the LLM wrapper — dual-mode parsing + graceful failure (no network)."""
import types

from app import llm


def _resp(content=None, tool_args=None):
    msg = types.SimpleNamespace(content=content, tool_calls=None)
    if tool_args is not None:
        fn = types.SimpleNamespace(arguments=tool_args)
        msg.tool_calls = [types.SimpleNamespace(function=fn)]
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


def _client(fn):
    return types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=fn)))


def test_returns_parsed_tool_call_arguments():
    client = _client(lambda **kw: _resp(tool_args='{"action":"diagnose","command":"uname -a"}'))
    out = llm.complete_json("sys", "usr", tool={"name": "x", "parameters": {}}, client=client)
    assert out["action"] == "diagnose" and out["command"] == "uname -a"


def test_falls_back_to_json_content_when_no_tool_calls():
    client = _client(lambda **kw: _resp(content='{"action":"finish","summary":"ok"}'))
    out = llm.complete_json("sys", "usr", tool={"name": "x", "parameters": {}}, client=client)
    assert out["action"] == "finish"


def test_tolerates_code_fenced_json():
    client = _client(lambda **kw: _resp(content='```json\n{"action":"plan"}\n```'))
    out = llm.complete_json("sys", "usr", client=client)
    assert out["action"] == "plan"


def test_returns_none_when_client_raises():
    def boom(**kw):
        raise RuntimeError("api down")
    out = llm.complete_json("sys", "usr", tool={"name": "x", "parameters": {}}, client=_client(boom))
    assert out is None


def test_returns_none_without_credentials(monkeypatch):
    # No client passed and no Azure creds -> None, never an exception or a network call.
    from app.config import settings
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "AZURE_OPENAI_ENDPOINT", "")
    assert llm.complete_json("sys", "usr") is None
