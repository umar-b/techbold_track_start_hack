#!/usr/bin/env python3
"""Smoke check 3/3 — Azure OpenAI (Foundry v1 API): chat, tool-calling, JSON mode.

This deployment is an Azure AI Foundry project endpoint served over the OpenAI-compatible
v1 API: POST {endpoint}/openai/v1/chat/completions with `model` in the body and NO
api-version. Verifies chat + JSON mode (the path the agent uses) and reports whether
native tool-calling fires (it does not, on gpt-5.4-nano). Stdlib only.

Run:  python scripts/smoke/check_azure.py
"""
import json
import sys
import urllib.error
import urllib.request

from _env import load_env, require, ok, fail


def _post(endpoint: str, key: str, body: dict):
    """Send one raw chat/completions request to the Azure v1 endpoint."""

    url = f"{endpoint.rstrip('/')}/openai/v1/chat/completions"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return resp.status, json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        return e.code, None, e.read().decode()[:400]
    except Exception as e:  # noqa: BLE001
        return None, None, str(e)


def main() -> int:
    """Check chat, JSON mode, and whether native tool-calling fires."""

    load_env()
    endpoint = require("AZURE_OPENAI_ENDPOINT")
    key = require("AZURE_OPENAI_API_KEY")
    model = require("AZURE_OPENAI_DEPLOYMENT")
    print(f"Azure (v1): {endpoint.rstrip('/')}/openai/v1/  model={model}")
    base = {"model": model}

    status, body, err = _post(endpoint, key, {**base, "messages": [{"role": "user", "content": "Reply with: OK"}]})
    if body:
        ok(f"chat -> {status}  reply={body['choices'][0]['message'].get('content','')!r}")
    else:
        fail(f"chat -> {status}  {err}")
        return 1

    status, body, err = _post(endpoint, key, {**base,
        "messages": [{"role": "user", "content": 'Return JSON: {"action":"diagnose","command":"uname -a"}'}],
        "response_format": {"type": "json_object"}})
    if body:
        content = body["choices"][0]["message"].get("content", "")
        try:
            json.loads(content)
            ok(f"JSON mode WORKS (agent path) -> {content!r}")
        except Exception:  # noqa: BLE001
            fail(f"JSON mode returned non-JSON: {content!r}")
    else:
        fail(f"JSON mode -> {status}  {err}")

    tools = [{"type": "function", "function": {"name": "run_command",
              "parameters": {"type": "object", "properties": {"command": {"type": "string"}}}}}]
    status, body, err = _post(endpoint, key, {**base,
        "messages": [{"role": "user", "content": "Check the OS with a shell command."}],
        "tools": tools, "tool_choice": "auto"})
    if body and body["choices"][0]["message"].get("tool_calls"):
        ok("native tool-calling fired (bonus) — JSON mode is still the default path")
    elif body:
        print("  note: native tool-calling did not fire (expected on nano) — agent uses JSON mode")
    else:
        print(f"  note: tool-calling probe -> {status} {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
