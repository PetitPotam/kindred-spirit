"""Kindred Spirit Setup: choosing her AI (#94), for her conversation (System 1) and her slow thinking (System 2).

System 1 answers you and says things on her own (the gateway's main "upstream"). System 2 learns from what happened
and writes her story (calls of kind "reflect"): the same AI, another one (gateway.json's "by_kind"), or off.
Choices go to ~/.kindred-spirit/gateway.json, keys to ~/.kindred-spirit/secrets.env (only you can read it); a key
is never shown back, logged, or put in a help prompt. Each choice is tested with a real call through the gateway,
the way her brain makes it.

Used by setup_steps.py (the steps "ai" and "thinking"). Standard library only.
"""
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request

import kindred_gateway as gw

# What a player can choose. kind: api (a key), local (Ollama), cli (a tool they already pay for).
PROVIDERS = {
    "gemini": {"label": "Gemini, with a free key from Google", "kind": "api", "key": "GEMINI_API_KEY",
               "get": "https://aistudio.google.com/apikey",
               "note": "Fast (about a second) and free up to a daily limit. On the free tier, Google may use what "
                       "is sent to improve its products.",
               "how": ["Open Google AI Studio (the link below) and sign in with a Google account.",
                       "Press \"Create API key\" (accept the terms if asked).",
                       "Copy the key (it starts with AIza) and paste it below, then press \"Use this\"."]},
    "openai": {"label": "OpenAI (ChatGPT's models)", "kind": "api", "key": "OPENAI_API_KEY",
               "get": "https://platform.openai.com/api-keys", "note": "Paid per use, with your own OpenAI account."},
    "groq": {"label": "Groq", "kind": "api", "key": "GROQ_API_KEY", "get": "https://console.groq.com/keys",
             "note": "Very fast; a free tier with daily limits."},
    "mistral": {"label": "Mistral", "kind": "api", "key": "MISTRAL_API_KEY", "get": "https://console.mistral.ai/api-keys",
                "note": "A European provider; free and paid plans."},
    "openrouter": {"label": "OpenRouter (many models, one key)", "kind": "api", "key": "OPENROUTER_API_KEY",
                   "get": "https://openrouter.ai/keys", "note": "Paid per use; some models are free."},
    "anthropic": {"label": "Claude API (Anthropic)", "kind": "api", "key": "ANTHROPIC_API_KEY",
                  "get": "https://console.anthropic.com/settings/keys", "note": "Paid per use, with an Anthropic account."},
    "ollama": {"label": "Ollama, a model on this computer", "kind": "local", "get": "https://ollama.com/download",
               "note": "Free and offline. Needs the Ollama app and about 3 GB for the model; slower on small computers."},
    "claude": {"label": "Claude Code, with your Claude subscription", "kind": "cli", "command": "claude",
               "get": "https://claude.com/claude-code",
               "note": "Uses your plan's usage. About 2 to 3 seconds per answer."},
    "codex": {"label": "Codex, with your ChatGPT subscription", "kind": "cli", "command": "codex",
              "get": "https://developers.openai.com/codex/cli",
              "template": {"type": "cli", "command": "codex", "args": ["exec", "--model", "{model}", "{prompt}"]},
              "note": "Uses your plan's usage; slower than an API."},
    "gemini_cli": {"label": "Gemini CLI, with your Google account", "kind": "cli", "command": "gemini",
                   "get": "https://github.com/google-gemini/gemini-cli",
                   "template": {"type": "cli", "command": "gemini", "args": ["--model", "{model}", "-p", "{prompt}"]},
                   "note": "Uses your Google account's limits; slower than an API."},
}
OFF = "off"  # an upstream that answers "off", for System 2 (the gateway knows it)
SEARCH = ["/opt/homebrew/bin", "/usr/local/bin", "~/.local/bin", "~/.npm-global/bin", "~/.bun/bin", "~/.claude/local",
          "/Applications/Ollama.app/Contents/Resources"]
HELLO = "Say hello to a Minecraft player in five words or fewer."


class Problem(Exception):
    """A problem the player can act on (the Setup shows the message)."""


def find_command(name):
    """A tool's full path: the Setup starts from Finder, whose PATH doesn't include Homebrew or npm's folders."""
    found = shutil.which(name)
    if found:
        return found
    for d in SEARCH + [os.path.join(p, "bin") for p in _nvm_versions()]:
        c = os.path.join(os.path.expanduser(d), name)
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return ""


def _nvm_versions():
    root = os.path.expanduser("~/.nvm/versions/node")
    try:
        return [os.path.join(root, v) for v in sorted(os.listdir(root), reverse=True)]
    except OSError:
        return []


def have_key(var):
    return bool(gw.secret(var))


def write_secret(var, value):
    """Adds or replaces VAR=value in secrets.env, readable only by you (never logged or shown)."""
    value = (value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-.:+/=]{8,400}", value):
        raise Problem("That doesn't look like a key: copy it again (it's one long word, no spaces) and paste it.")
    try:
        with open(gw.SECRETS, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        lines = ["# API keys for the Kindred gateway. Only you can read this file; never share it."]
    rx = re.compile(r"^\s*#?\s*%s\s*=" % re.escape(var))
    for i, line in enumerate(lines):
        if rx.match(line):
            lines[i] = "%s=%s" % (var, value)
            break
    else:
        lines.append("%s=%s" % (var, value))
    os.makedirs(gw.DIR, exist_ok=True)
    old = os.umask(0o077)
    try:
        with open(gw.SECRETS + ".tmp", "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        os.chmod(gw.SECRETS + ".tmp", 0o600)
        os.replace(gw.SECRETS + ".tmp", gw.SECRETS)
    finally:
        os.umask(old)


def describe(name):
    """A provider as a choice on the page, with what this computer has."""
    p = PROVIDERS[name]
    note = p["note"]
    if p["kind"] == "api" and have_key(p["key"]):
        note += " A key is already saved."
    elif p["kind"] == "cli":
        note += " Found on this computer." if find_command(p["command"]) else " Not installed yet (see the link)."
    elif p["kind"] == "local":
        note += " Found on this computer." if find_command("ollama") else " Not installed yet (see the link)."
    out = {"value": name, "label": p["label"], "note": note, "link": {"label": "Get it" if p["kind"] != "api" else
                                                                       "Get a key", "url": p["get"]}}
    if p.get("how"):
        out["how"] = p["how"]
    return out


def apply(name, key="", model="", kind=None):
    """Saves the choice for her conversation (kind None) or for her slow thinking (kind "reflect")."""
    if name not in PROVIDERS:
        raise Problem("Choose one of the options.")
    p = PROVIDERS[name]
    extra = {}
    if p["kind"] == "api":
        if key:
            write_secret(p["key"], key)
        elif not have_key(p["key"]):
            raise Problem("Paste your %s key first (the link shows where to get one)." % p["label"].split(",")[0])
    elif p["kind"] == "cli":
        path = find_command(p["command"])
        if not path:
            raise Problem("%s isn't installed on this computer: install it (the link), sign in once, then choose it "
                          "again." % p["label"].split(",")[0])
        extra = dict(p.get("template") or {}, command=path)
    elif p["kind"] == "local" and not find_command("ollama"):
        raise Problem("Ollama isn't installed: get it from ollama.com (the link), open it once, then choose it again.")
    model = (model or "").strip()

    def edit(s):
        if extra:
            s["upstreams"][name] = dict(s["upstreams"].get(name, {}), **extra)
        if model:
            s["upstreams"][name]["model"] = model
        if kind:
            s.setdefault("by_kind", {})[kind] = name
        else:
            s["upstream"] = name
    gw.change(edit)


def thinking_choice(choice):
    """System 2: "same" (the conversation's AI), "off", or a provider of its own."""
    def edit(s):
        by = s.setdefault("by_kind", {})
        if choice == "same":
            by.pop("reflect", None)
        elif choice == OFF:
            s["upstreams"][OFF] = {"type": "off"}
            by["reflect"] = OFF
    gw.change(edit)


def current():
    s = gw.load()
    reflect = (s.get("by_kind") or {}).get("reflect")
    return s.get("upstream") or "gemini", ("same" if not reflect else reflect), s


def call(kind="reply", timeout=120):
    """One small call through the running gateway, as her brain makes it: (seconds, text, tokens)."""
    body = json.dumps({"model": "", "max_tokens": 40, "messages": [{"role": "user", "content": HELLO}]}).encode()
    req = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % gw.LISTEN_PORT, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "X-Kindred-Kind": kind})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        try:
            detail = json.loads(detail).get("error", {}).get("message") or detail
        except (ValueError, AttributeError):
            pass
        raise Problem("The AI answered with an error (HTTP %d): %s" % (e.code, detail))
    except (urllib.error.URLError, OSError) as e:
        raise Problem("The gateway isn't answering (%s). Wake her up first (the step \"Wake her up\")."
                      % getattr(e, "reason", e))
    text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return round(time.time() - t, 1), text.strip(), (data.get("usage") or {}).get("total_tokens")


def explain(name, error):
    """What to do about a failed test, in plain words."""
    p = PROVIDERS.get(name, {})
    hints = {"api": "Check the key: copy it again from %s and paste it, then press \"Use this\"." % p.get("get", ""),
             "cli": "Open Terminal, run %s once and sign in, then test again." % p.get("command", ""),
             "local": "Open the Ollama app, and download the model (\"Download the model\")."}
    return "%s %s" % (error, hints.get(p.get("kind"), ""))


def ollama_model():
    return (gw.load()["upstreams"].get("ollama") or {}).get("model") or "qwen3.5:4b"


def ollama_has_model(model):
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
            return any(m.get("name", "").split(":latest")[0] == model.split(":latest")[0]
                       for m in json.loads(r.read()).get("models", []))
    except (urllib.error.URLError, OSError, ValueError):
        return None  # Ollama isn't running


def pull_ollama_model():
    """Starts `ollama pull` in the background (progress in logs/ollama-pull.out)."""
    path = find_command("ollama")
    if not path:
        raise Problem("Ollama isn't installed: get it from ollama.com first.")
    log = os.path.join(gw.DIR, "logs", "ollama-pull.out")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    with open(log, "ab") as out:
        subprocess.Popen([path, "pull", ollama_model()], stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    return log
