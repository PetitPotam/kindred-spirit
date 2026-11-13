"""Choosing her AI in the Setup (#94): keys go to secrets.env only, every choice is tested through a real gateway
(talking to the stand-in AI), her slow thinking can be the same, another AI or off. Throwaway home, fake keys."""
import json
import os
import stat
import sys
import threading

import pytest

import gateway_stub  # noqa: F401  (puts services/ on the path)
import kindred_gateway as gw
import setup_ai
import setup_steps

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import fake_ai  # noqa: E402

FAKE_KEY = "gsk_fake0000000000000000000000robin"


@pytest.fixture
def home(tmp_path, monkeypatch):
    kh = tmp_path / ".kindred-spirit"
    (kh / "logs").mkdir(parents=True)
    for name, rel in (("DIR", ""), ("STATE", "gateway.json"), ("SECRETS", "secrets.env"), ("LOCK", ".lock"),
                      ("LOG_DIR", "logs"), ("TRANSCRIPT", "logs/gateway.jsonl")):
        monkeypatch.setattr(gw, name, str(kh / rel).rstrip("/"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))  # no real AI tools from this computer
    monkeypatch.setattr(setup_ai, "SEARCH", [])
    for var in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return kh


@pytest.fixture
def gateway(home, monkeypatch):
    """A real gateway on a free port, with Groq's address pointed at the stand-in AI."""
    ai = fake_ai.ThreadingHTTPServer(("127.0.0.1", 0), fake_ai.Handler)
    threading.Thread(target=ai.serve_forever, daemon=True).start()
    gw.change(lambda s: s["upstreams"]["groq"].update(base="http://127.0.0.1:%d/v1" % ai.server_address[1]))
    srv = gw.ThreadingHTTPServer(("127.0.0.1", 0), gw.Handler)
    monkeypatch.setattr(gw, "LISTEN_PORT", srv.server_address[1])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    ai.shutdown()


def test_a_key_goes_to_secrets_only_and_is_never_shown(gateway, home):
    r = setup_steps.run("ai", "choose", {"choice": "groq", "key": FAKE_KEY})
    assert r["ok"] and "test answer" in r["message"], r
    assert FAKE_KEY not in json.dumps(r) and FAKE_KEY not in (home / "setup.json").read_text()
    assert FAKE_KEY not in (home / "gateway.json").read_text()
    assert "GROQ_API_KEY=" + FAKE_KEY in (home / "secrets.env").read_text()
    assert stat.S_IMODE(os.stat(home / "secrets.env").st_mode) == 0o600
    assert json.loads((home / "gateway.json").read_text())["upstream"] == "groq"
    s = setup_steps.step_ai()
    assert s["status"] == "done" and "already saved" in next(c for c in s["choices"] if c["value"] == "groq")["note"]
    assert FAKE_KEY not in json.dumps(setup_steps.overview()) and FAKE_KEY not in setup_steps.help_prompt("ai")


def test_choosing_without_a_key_says_where_to_get_one(home):
    r = setup_steps.run("ai", "choose", {"choice": "gemini"})
    assert not r["ok"] and "Paste your Gemini key" in r["message"]
    assert not setup_steps.run("ai", "choose", {"choice": "groq", "key": "not a key"})["ok"]
    gemini = next(c for c in setup_steps.step_ai()["choices"] if c["value"] == "gemini")
    assert gemini["recommended"] and gemini["how"] and gemini["link"]["url"].startswith("https://aistudio.google.com")


def test_a_failing_test_says_what_to_do(home, monkeypatch):
    monkeypatch.setattr(gw, "LISTEN_PORT", 1)  # nothing listens there
    gw.change(lambda s: s.__setitem__("upstream", "groq"))
    r = setup_steps.run("ai", "test")
    assert not r["ok"] and "Wake her up" in r["message"] and "console.groq.com" in r["message"]


def test_ai_tools_are_found_where_finder_cant_see_them(home, tmp_path):
    assert not setup_steps.run("ai", "choose", {"choice": "codex"})["ok"]  # not installed
    tool = tmp_path / "bin" / "codex"
    tool.parent.mkdir()
    tool.write_text("#!/bin/sh\necho hi\n")
    tool.chmod(0o755)
    setup_ai.apply("codex")
    up = json.loads((home / "gateway.json").read_text())["upstreams"]["codex"]
    assert up["command"] == str(tool) and up["type"] == "cli" and "{prompt}" in up["args"]


def test_slow_thinking_same_other_or_off(gateway, home):
    setup_ai.apply("groq", key=FAKE_KEY)
    r = setup_steps.run("thinking", "choose", {"choice": "same"})
    assert r["ok"] and "answered" in r["message"]
    r = setup_steps.run("thinking", "choose", {"choice": "off"})
    assert r["ok"] and r["warn"] and "won't learn" in r["message"]
    state = json.loads((home / "gateway.json").read_text())
    assert state["by_kind"]["reflect"] == "off" and state["upstream"] == "groq"  # her conversation unchanged
    with pytest.raises(setup_ai.Problem, match="switched off"):  # the gateway answers "off" at once
        setup_ai.call("reflect")
    assert setup_ai.call("reply")[1]  # while her conversation still answers
    assert setup_steps.run("thinking", "choose", {"choice": "groq"})["ok"]  # a provider of its own
    assert json.loads((home / "gateway.json").read_text())["by_kind"]["reflect"] == "groq"
    assert setup_steps.run("thinking", "choose", {"choice": "same"})["ok"]
    assert "reflect" not in json.loads((home / "gateway.json").read_text())["by_kind"]


def test_the_steps_come_in_order(home):
    assert list(setup_steps.STEPS) == ["computer", "install", "start", "ai", "thinking", "instincts", "voice", "hearing", "minecraft", "hello", "login"]
    for sid in ("ai", "thinking"):
        s = setup_steps.STEPS[sid][0]()
        assert s["choices"] and s["fields"] and s["default"] and len(s["why"]) > 60
