#!/usr/bin/env python3
"""Smoke check 3/3 — Azure OpenAI: chat, tool-calling, JSON mode.

THE critical unknown (ADR-0006): does the gpt-5.4-nano deployment support native
tool/function calling? This calls the REST API directly (stdlib only) and reports
which of the three modes work, so you know whether to use native tools or the
strict-JSON fallback BEFORE building.

Run:  python scripts/smoke/check_azure.py
"""
import json
import sys
import urllib.error
import urllib.request

from _env import load_env, require, ok, fail


def _post(endpoint: str, deployment: str, version: str, key: str, body: dict):
    url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={version}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return resp.status, json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        return e.code, None, e.read().decode()[:500]
    except Exception as e:  # noqa: BLE001
        return None, None, str(e)


def main() -> int:
    load_env()
    endpoint = require("AZURE_OPENAI_ENDPOINT")
    deployment = require("AZURE_OPENAI_DEPLOYMENT")
    version = require("AZURE_OPENAI_API_VERSION")
    key = require("AZURE_OPENAI_API_KEY")
    print(f"Azure: {endpoint}  deployment={deployment}  api-version={version}")

    # 1) plain chat
    status, body, err = _post(endpoint, deployment, version, key,
                              {"messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                               "max_completion_tokens": 16})
    if body:
        ok(f"chat -> {status}  reply={body['choices'][0]['message'].get('content','')!r}")
    else:
        fail(f"chat -> {status}  {err}")
        print("     (if it complains about a param, that's the value to fix — note it.)")
        return 1

    # 2) native tool / function calling — the make-or-break for ADR-0006
    tools = [{"type": "function", "function": {
        "name": "run_command",
        "description": "Run a read-only shell command on the server.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}},
                       "required": ["command"]}}}]
    status, body, err = _post(endpoint, deployment, version, key,
                              {"messages": [{"role": "user",
                                             "content": "Check the OS version on the Linux server using a shell command."}],
                               "tools": tools, "tool_choice": "auto", "max_completion_tokens": 100})
    if body and body["choices"][0]["message"].get("tool_calls"):
        call = body["choices"][0]["message"]["tool_calls"][0]
        ok(f"tool-calling WORKS -> {call['function']['name']}({call['function'].get('arguments','')})")
        print("     => use NATIVE tool-calling (preferred path).")
    elif body:
        fail("tool-calling: model replied with text, no tool_calls.")
        print("     => use the strict-JSON fallback (ADR-0006).")
    else:
        fail(f"tool-calling request -> {status}  {err}")
        print("     => likely unsupported on this api-version; use strict-JSON fallback.")

    # 3) JSON mode (the fallback path)
    status, body, err = _post(endpoint, deployment, version, key,
                              {"messages": [{"role": "user",
                                             "content": 'Return JSON: {"kind":"diagnose","command":"uname -a"}'}],
                               "response_format": {"type": "json_object"}, "max_completion_tokens": 60})
    if body:
        content = body["choices"][0]["message"].get("content", "")
        try:
            json.loads(content)
            ok(f"JSON mode WORKS -> {content!r}")
        except Exception:  # noqa: BLE001
            fail(f"JSON mode returned non-JSON: {content!r}")
    else:
        fail(f"JSON mode -> {status}  {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
