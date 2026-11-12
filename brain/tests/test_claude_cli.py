"""The gateway's Claude provider, with a stand-in for the Claude CLI (no login, no usage)."""
import json
import os
import stat

import pytest

import gateway_stub  # noqa: F401  (puts services/ on the path)
import kindred_gateway as gw

FAKE = r'''#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
prompt = sys.stdin.read()
def arg(name):
    return args[args.index(name) + 1] if name in args else None
json.dump({"argv": args}, open(sys.argv[0] + ".last", "w"))
if "LOGIN-EXPIRED" in prompt:
    print(json.dumps({"is_error": True, "subtype": "success", "result": "Failed to authenticate: OAuth session expired"}))
    sys.exit(1)
schema = arg("--json-schema")
out = {"is_error": False, "result": "[happy][kind] Hi there!", "total_cost_usd": 0.0012,
       "usage": {"input_tokens": 1000, "cache_read_input_tokens": 2000, "output_tokens": 40}}
if schema:
    names = json.loads(schema)["properties"]["tool"]["enum"]
    if "find_animal" in names and "WHAT THE TOOL ANSWERED" not in prompt:
        out["structured_output"] = {"reply": "", "tool": "find_animal", "arguments": {"animal": "sheep"}}
    else:
        out["structured_output"] = {"reply": "[excited][kind] Two sheep, 30 blocks to your right!", "tool": None}
print(json.dumps(out))
'''


@pytest.fixture
def fake(tmp_path, monkeypatch):
    p = tmp_path / "claude"
    p.write_text(FAKE)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(gw, "CLAUDE_DIR", str(tmp_path / "cwd"))
    return {"type": "claude_cli", "command": str(p), "model": "haiku", "effort": "low",
            "by_kind": {"reflect": {"model": "sonnet", "effort": "medium"}}}, p


def last_args(p):
    return json.load(open(str(p) + ".last"))["argv"]


def chat(*msgs, tools=None, force=None):
    req = {"messages": list(msgs)}
    if tools:
        req["tools"] = [{"type": "function", "function": {"name": t, "description": "d", "parameters": {}}} for t in tools]
    if force:
        req["tool_choice"] = {"type": "function", "function": {"name": force}}
    return req


def test_a_plain_reply_with_the_fast_model(fake):
    up, p = fake
    r = gw.claude_cli_chat(up, chat({"role": "system", "content": "You are Pip."}, {"role": "user", "content": "hi"}), "reply")
    assert r["choices"][0]["message"]["content"] == "[happy][kind] Hi there!"
    assert r["usage"]["prompt_tokens"] == 3000 and r["usage"]["completion_tokens"] == 40
    a = last_args(p)
    assert a[a.index("--model") + 1] == "haiku" and a[a.index("--effort") + 1] == "low"
    assert a[a.index("--system-prompt") + 1] == "You are Pip." and "--json-schema" not in a
    assert "--no-session-persistence" in a and a[a.index("--tools") + 1] == ""


def test_learning_uses_the_stronger_model(fake):
    up, p = fake
    gw.claude_cli_chat(up, chat({"role": "user", "content": "Already known: ..."}), "reflect")
    a = last_args(p)
    assert a[a.index("--model") + 1] == "sonnet" and a[a.index("--effort") + 1] == "medium"


def test_tools_become_tool_calls_and_results_come_back(fake):
    up, _ = fake
    first = gw.claude_cli_chat(up, chat({"role": "user", "content": "where are the sheep?"},
                                        tools=["find_animal", "guide"], force="find_animal"), "reply")
    call = first["choices"][0]["message"]["tool_calls"][0]
    assert call["function"]["name"] == "find_animal" and json.loads(call["function"]["arguments"]) == {"animal": "sheep"}
    second = gw.claude_cli_chat(up, chat({"role": "user", "content": "where are the sheep?"},
                                         {"role": "assistant", "content": "", "tool_calls": [call]},
                                         {"role": "tool", "tool_call_id": call["id"], "content": '{"ok": true}'},
                                         tools=["find_animal", "guide"]), "reply")
    assert "Two sheep" in second["choices"][0]["message"]["content"]


def test_an_expired_login_says_what_to_do(fake):
    up, _ = fake
    with pytest.raises(RuntimeError, match="/login"):
        gw.claude_cli_chat(up, chat({"role": "user", "content": "LOGIN-EXPIRED"}), "reply")


def test_any_cli_from_a_template(tmp_path, monkeypatch):
    """A made-up "otherai" CLI: prompt as an argument, plain text out, tools as JSON in the text."""
    p = tmp_path / "otherai"
    p.write_text(r'''#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
json.dump(args, open(sys.argv[0] + ".last", "w"))
prompt = args[-1]
if "ONE JSON object" in prompt:
    print('Sure! {"reply": "", "tool": "find_animal", "arguments": {"animal": "cow"}}')
else:
    print("[happy][kind] Moo! Hello!")
''')
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(gw, "CLAUDE_DIR", str(tmp_path / "cwd"))
    up = {"type": "cli", "command": str(p), "args": ["exec", "--model", "{model}", "{prompt}"], "model": ""}
    r = gw.any_cli_chat(up, chat({"role": "system", "content": "You are Pip."}, {"role": "user", "content": "hi"}), "reply")
    assert r["choices"][0]["message"]["content"] == "[happy][kind] Moo! Hello!"
    args = json.load(open(str(p) + ".last"))
    assert args[0] == "exec" and "--model" not in args, "no model set: the flag is left out"
    assert args[-1].startswith("You are Pip."), "no {system}: it goes first in the prompt"
    r = gw.any_cli_chat(up, chat({"role": "user", "content": "find a cow"}, tools=["find_animal"]), "reply")
    call = r["choices"][0]["message"]["tool_calls"][0]["function"]
    assert call["name"] == "find_animal" and json.loads(call["arguments"]) == {"animal": "cow"}
