"""The setup guide, with scripted answers in a throwaway home folder (nothing real is touched)."""
import json
import os
import stat
import sys

import pytest

import gateway_stub  # noqa: F401  (puts services/ on the path)
import kindred_gateway as gw

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
import guide  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    for name in ("DIR", "STATE", "SECRETS", "LOCK"):
        monkeypatch.setattr(gw, name, str(tmp_path / {"DIR": "", "STATE": "gateway.json", "SECRETS": "secrets.env",
                                                         "LOCK": ".lock"}[name]).rstrip("/"))
    for var in ("GEMINI_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(guide, "detect", lambda: {"claude": False, "ollama": False, "whisper_server": True,
                                                  "brew": True, "apple_silicon": True, "ram_gb": 16,
                                                  "codex": True, "gemini_cli": False, "cursor": False})
    (tmp_path / "brain.toml").write_text('[voice]\nenabled = true               # false = subtitles only\n')
    return tmp_path


def test_gemini_with_everything_local(home):
    # AI 1 (Gemini) + key, STT 1 (local Whisper), voice 1 (Kokoro), memory 1 (local), embeddings 1 (local), save
    ask = guide.Ask(["1", "AIza-test-key", "1", "1", "1", "1", "y"])
    assert guide.run(ask, install=False, start=False) == 0
    state = gw.load()
    assert state["upstream"] == "gemini" and state["stt"]["use"] == "local_whisper"
    assert state["tts"]["use"] == "local_kokoro" and state["embeddings"]["use"] == "local"
    assert gw.secret("GEMINI_API_KEY") == "AIza-test-key"
    assert stat.S_IMODE(os.stat(gw.SECRETS).st_mode) == 0o600, "keys readable only by you"


def test_another_ai_tool_typing_and_subtitles_only(home):
    # AI 3 (a CLI), which one: 1 (Codex), model: empty; STT 4 (none); voice 3 (none); memory local; embeddings none
    ask = guide.Ask(["3", "1", "", "4", "3", "1", "2", "y"])
    guide.run(ask, install=False, start=False)
    state = gw.load()
    assert state["upstream"] == "codex" and state["upstreams"]["codex"]["type"] == "cli"
    assert state["stt"]["use"] == "none" and state["tts"]["use"] == "none" and state["embeddings"]["use"] == "none"
    assert "enabled = false" in (home / "brain.toml").read_text(), "no voice: subtitles only in the brain too"
    assert "# false = subtitles only" in (home / "brain.toml").read_text(), "its comment stays"


def test_an_api_key_reused_for_speech_and_a_key_kept(home):
    gw.change(lambda s: None)
    guide.write_secrets({"OPENAI_API_KEY": "sk-old"})
    # AI 4 (a key), service 1 (OpenAI), keep the key: y; STT 3 (OpenAI: key already set, no question);
    # voice 2 (OpenAI); memory local; embeddings: local, gemini?, openai -> 2 is OpenAI here; save
    ask = guide.Ask(["4", "1", "y", "3", "2", "1", "2", "y"])
    guide.run(ask, install=False, start=False)
    state = gw.load()
    assert state["upstream"] == "openai" and state["stt"]["use"] == "openai" and state["tts"]["use"] == "openai"
    assert state["embeddings"]["use"] == "openai" and gw.secret("OPENAI_API_KEY") == "sk-old"


def test_nothing_changes_if_you_dont_save(home):
    ask = guide.Ask(["1", "AIza-x", "1", "1", "1", "1", "n"])
    assert guide.run(ask, install=False, start=False) == 1
    assert not os.path.exists(gw.STATE) and not os.path.exists(gw.SECRETS)


def test_the_plan_installs_only_what_you_chose():
    p = guide.plan({"upstream": "claude", "secrets": {}}, {"use": "groq", "secrets": {"GROQ_API_KEY": "g"}},
                   {"use": "local_kokoro", "secrets": {}}, {"memory": "local", "embeddings": "none", "secrets": {}})
    assert p["installs"] == ["kokoro"] and p["secrets"] == {"GROQ_API_KEY": "g"}


def test_the_final_check_says_how_to_fix_what_failed(monkeypatch, capsys):
    monkeypatch.setattr(guide.subprocess, "run", lambda *a, **k: None)  # (start.sh)

    def check():
        print("FAIL AI           HTTP 401")
        print("ok   voice        65 KB of WAV")
        return 1
    monkeypatch.setattr(gw, "check", check)
    assert guide.finish() == 1
    out = capsys.readouterr().out
    assert "FAIL AI" in out and "/login" in out and "secrets.env" in out
    assert "run this guide again" in out
