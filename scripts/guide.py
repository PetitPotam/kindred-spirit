#!/usr/bin/env python3
"""The setup guide: choose your companion's AI, speech-to-text, voice and memory from what you
already have, then test everything.

    scripts/setup.sh            (runs this after preparing the brain)
    brain/.venv/bin/python scripts/guide.py          run it again any time to change your choices
    brain/.venv/bin/python scripts/guide.py --check  just the final test, with how to fix what fails

Nothing is shared: every player sets up their own. Keys go in ~/.kindred-spirit/secrets.env, which
only you can read. Choices go in ~/.kindred-spirit/gateway.json (see docs/GATEWAY.md); you can
change any of them later with services/kindred_gateway.py.
"""
import contextlib
import getpass
import io
import os
import platform
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "services"))
sys.path.insert(0, os.path.join(ROOT, "brain"))
import kindred_gateway as gw  # noqa: E402

BOLD, DIM, GREEN, RED, OFF = ("\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[0m") if sys.stdout.isatty() \
    else ("", "", "", "", "")

# AI command-line tools a player may already pay for (templates: docs/GATEWAY.md)
CLI_TOOLS = {
    "codex": ("Codex (ChatGPT)", {"type": "cli", "command": "codex", "args": ["exec", "--model", "{model}", "{prompt}"]}),
    "gemini_cli": ("Gemini CLI", {"type": "cli", "command": "gemini", "args": ["--model", "{model}", "-p", "{prompt}"]}),
    "cursor": ("Cursor agent", {"type": "cli", "command": "cursor-agent", "args": ["-p", "--model", "{model}", "{prompt}"]}),
}
CLI_COMMANDS = {"codex": "codex", "gemini_cli": "gemini", "cursor": "cursor-agent"}
API_KEYS = {  # provider: (name, key variable, where to get one)
    "gemini": ("Gemini", "GEMINI_API_KEY", "https://aistudio.google.com/apikey (free tier)"),
    "openai": ("OpenAI", "OPENAI_API_KEY", "https://platform.openai.com/api-keys"),
    "anthropic": ("Claude API", "ANTHROPIC_API_KEY", "https://console.anthropic.com/settings/keys"),
    "groq": ("Groq", "GROQ_API_KEY", "https://console.groq.com/keys (free tier)"),
    "openrouter": ("OpenRouter", "OPENROUTER_API_KEY", "https://openrouter.ai/keys"),
    "mistral": ("Mistral", "MISTRAL_API_KEY", "https://console.mistral.ai/api-keys"),
}


class Ask:
    """Questions on the terminal (tests replace it with scripted answers)."""

    def __init__(self, answers=None):
        self.answers = list(answers) if answers is not None else None

    def _next(self, prompt, secret=False):
        if self.answers is not None:
            a = self.answers.pop(0) if self.answers else ""
            print(prompt + ("*****" if secret and a else a))
            return a
        return getpass.getpass(prompt) if secret else input(prompt)

    def choose(self, question, options, default=1):
        """options: [(key, label, note)]; returns the chosen key."""
        print("\n" + BOLD + question + OFF)
        for i, (_, label, note) in enumerate(options, 1):
            print("  %d) %s%s" % (i, label, (DIM + "  " + note + OFF) if note else ""))
        while True:
            a = self._next("Choose 1-%d [%d]: " % (len(options), default)).strip() or str(default)
            if a.isdigit() and 1 <= int(a) <= len(options):
                return options[int(a) - 1][0]
            print("  Type a number from 1 to %d." % len(options))

    def text(self, question, default=""):
        a = self._next("%s%s: " % (question, " [%s]" % default if default else "")).strip()
        return a or default

    def secret(self, question):
        return self._next(question + " (hidden while you type): ", secret=True).strip()

    def yes(self, question, default=True):
        a = self._next("%s [%s]: " % (question, "Y/n" if default else "y/N")).strip().lower()
        return default if not a else a.startswith("y")


# ---------------------------------------------------------------------- what this computer has

def have_secret(name):
    return bool(gw.secret(name))


def detect():
    found = {"claude": bool(_which_claude()), "ollama": bool(shutil.which("ollama")),
             "whisper_server": bool(shutil.which("whisper-server")), "brew": bool(shutil.which("brew")),
             "apple_silicon": platform.system() == "Darwin" and platform.machine() == "arm64"}
    for key, cmd in CLI_COMMANDS.items():
        found[key] = bool(shutil.which(cmd))
    try:
        found["ram_gb"] = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9)
    except (ValueError, OSError, AttributeError):
        found["ram_gb"] = 0
    return found


def _which_claude():
    try:
        return gw.claude_command("claude")
    except RuntimeError:
        return ""


def claude_logged_in():
    """A tiny real call: is the Claude CLI logged in? (uses a sliver of your plan's usage)"""
    try:
        up = gw.DEFAULT_STATE["upstreams"]["claude"]
        r = gw.claude_cli_chat(dict(up, timeout=60), {"messages": [{"role": "user", "content": "Say ok."}]}, "reply")
        return bool(r["choices"][0]["message"]["content"]), ""
    except RuntimeError as e:
        return False, str(e)


# ---------------------------------------------------------------------- the questions

def ask_ai(ask, found):
    def mark(ok, yes="found on this computer", no="not installed"):
        return yes if ok else no
    clis = [k for k in CLI_TOOLS if found.get(k)]
    options = [
        ("gemini", "Gemini with a free API key", "fast (~1 s), free tier, recommended if you have nothing else"),
        ("claude", "Your Claude subscription (Claude Code)", mark(found["claude"]) + "; uses your plan's usage, ~3 s"),
        ("cli", "Another AI you pay for, through its command-line tool",
         "found: " + ", ".join(CLI_TOOLS[k][0] for k in clis) if clis else "Codex, Gemini CLI, Cursor agent"),
        ("key", "An API key you already have", "OpenAI, Claude API, Groq, OpenRouter, Mistral"),
        ("ollama", "Free and offline, on this computer (Ollama)",
         mark(found["ollama"]) + ("; needs about 8 GB of memory" if found.get("ram_gb", 0) < 12 else "")),
    ]
    choice = ask.choose("1/4  The AI: how she thinks and talks", options,
                        default=2 if found["claude"] and not have_secret("GEMINI_API_KEY") else 1)
    out = {"secrets": {}, "upstream": None, "add_upstream": None}
    if choice == "gemini":
        out["upstream"] = "gemini"
        if not have_secret("GEMINI_API_KEY") or not ask.yes("A Gemini key is already set. Keep it?"):
            print("  Get a free key at " + API_KEYS["gemini"][2])
            out["secrets"]["GEMINI_API_KEY"] = ask.secret("  Paste your Gemini key")
    elif choice == "claude":
        out["upstream"] = "claude"
        if not found["claude"]:
            print("  Install Claude Code first (https://claude.com/claude-code), log in, then run this guide again.")
            out["note"] = "install the Claude CLI"
    elif choice == "cli":
        opts = [(k, CLI_TOOLS[k][0], mark(found.get(k))) for k in CLI_TOOLS]
        k = ask.choose("  Which one?", opts, default=next((i for i, o in enumerate(opts, 1) if found.get(o[0])), 1))
        out["upstream"], out["add_upstream"] = k, CLI_TOOLS[k][1]
        model = ask.text("  Which model should it use (empty: the tool's default)")
        if model:
            out["add_upstream"] = dict(out["add_upstream"], model=model)
        print("  " + DIM + "Note: this template comes from the tool's documentation; if the check fails, compare it "
              "with its --help (docs/GATEWAY.md)." + OFF)
    elif choice == "key":
        opts = [(k, v[0], "key already set" if have_secret(v[1]) else "") for k, v in API_KEYS.items() if k != "gemini"]
        k = ask.choose("  Which service?", opts)
        out["upstream"] = k
        name, var, where = API_KEYS[k]
        if not have_secret(var) or not ask.yes("  A %s key is already set. Keep it?" % name):
            print("  Get a key at " + where)
            out["secrets"][var] = ask.secret("  Paste your %s key" % name)
    else:
        out["upstream"] = "ollama"
        out["ollama_model"] = gw.DEFAULT_STATE["upstreams"]["ollama"]["model"]
        if not found["ollama"]:
            print("  Install Ollama first (https://ollama.com), then run this guide again.")
            out["note"] = "install Ollama"
    return out


def ask_stt(ask, found, ai):
    local_note = ("free and private, on your GPU" if found["apple_silicon"] else "free and private") + \
                 ", about 600 MB to download" + ("" if found["whisper_server"] or found["brew"] else
                                                 " (needs whisper.cpp installed)")
    options = [("local_whisper", "Whisper on this computer", local_note),
               ("groq", "Groq", "free tier, needs a Groq key" + (" (set)" if have_secret("GROQ_API_KEY") else "")),
               ("openai", "OpenAI", "needs an OpenAI key" + (" (set)" if have_secret("OPENAI_API_KEY") else "")),
               ("none", "None: I'll type to her", "plain chat in the game")]
    use = ask.choose("2/4  Speech-to-text: how she hears you (hold V and talk)", options)
    return {"use": use, "secrets": _key_for(ask, use, ai)}


def ask_tts(ask, found, ai):
    options = [("local_kokoro", "Kokoro on this computer", "free and private, her bright young voice, ~350 MB"),
               ("openai", "OpenAI voices", "needs an OpenAI key" + (" (set)" if have_secret("OPENAI_API_KEY") else "")),
               ("none", "None: subtitles only", "")]
    use = ask.choose("3/4  Voice: how she speaks", options)
    return {"use": use, "secrets": _key_for(ask, use, ai)}


def ask_memory(ask, found, ai):
    where = ask.choose("4/4  Memory: where she keeps what she learns", [
        ("local", "On this computer", "a small file, private (recommended)"),
        ("remote", "On a gateway I deployed elsewhere", "same memory on all your computers (docs/GATEWAY.md)")])
    out = {"memory": where, "secrets": {}}
    if where == "remote":
        out["remote_base"] = ask.text("  The address of your deployed gateway, like https://my-server.example/v1")
        out["secrets"]["KINDRED_REMOTE_KEY"] = ask.secret("  Its access key")
    have = lambda var: have_secret(var) or var in ai["secrets"]  # noqa: E731
    options = [("local", "A small model on this computer", "free, private, about 65 MB (recommended)")]
    if have("GEMINI_API_KEY"):
        options.append(("gemini", "Gemini", "uses your Gemini key"))
    if have("OPENAI_API_KEY"):
        options.append(("openai", "OpenAI", "uses your OpenAI key"))
    options.append(("none", "None: keyword search only", "she still remembers, a bit less cleverly"))
    out["embeddings"] = ask.choose("  How she finds the memories that matter (embeddings)", options)
    return out


def _key_for(ask, use, ai):
    var = {"groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY"}.get(use)
    if not var or have_secret(var) or var in ai["secrets"]:
        return {}
    print("  Get a key at " + API_KEYS["groq" if use == "groq" else "openai"][2])
    return {var: ask.secret("  Paste your %s key" % ("Groq" if use == "groq" else "OpenAI"))}


# ---------------------------------------------------------------------- applying the choices

def plan(ai, stt, tts, memory):
    """Everything to write and install, from the answers (pure: easy to test)."""
    secrets = {}
    for part in (ai, stt, tts, memory):
        secrets.update({k: v for k, v in part.get("secrets", {}).items() if v})
    installs = [name for name, needed in (("kokoro", tts["use"] == "local_kokoro"),
                                          ("embed", memory["embeddings"] == "local"),
                                          ("whisper", stt["use"] == "local_whisper")) if needed]
    return {"upstream": ai["upstream"], "add_upstream": ai.get("add_upstream"), "stt": stt["use"],
            "tts": tts["use"], "embeddings": memory["embeddings"], "memory": memory["memory"],
            "remote_base": memory.get("remote_base"), "secrets": secrets, "installs": installs,
            "ollama_model": ai.get("ollama_model"), "voice_enabled": tts["use"] != "none",
            "notes": [x.get("note") for x in (ai,) if x.get("note")]}


def apply(p):
    """Writes gateway.json, secrets.env and brain.toml's voice switch."""
    def edit(s):
        if p["add_upstream"]:
            s["upstreams"][p["upstream"]] = dict(s["upstreams"].get(p["upstream"], {}), **p["add_upstream"])
        s["upstream"] = p["upstream"]
        for part in ("stt", "tts", "embeddings", "memory"):
            s[part]["use"] = p[part]
        if p["memory"] == "remote" and p.get("remote_base"):
            s["memory"]["providers"]["remote"].update(base=p["remote_base"], key="env:KINDRED_REMOTE_KEY")
    os.makedirs(gw.DIR, exist_ok=True)
    gw.change(edit)
    write_secrets(p["secrets"])
    toml = os.path.join(gw.DIR, "brain.toml")
    if not os.path.exists(toml):
        try:  # the brain's own template, as on its first start
            from kindred import config
            config.load(toml)
        except ImportError:
            pass
    old = set_toml(toml, "voice", "enabled", "true" if p["voice_enabled"] else "false")
    return {"voice_changed": old is not None and old != ("true" if p["voice_enabled"] else "false")}


def write_secrets(values):
    """Adds or replaces KEY=value lines in secrets.env, readable only by you."""
    if not values:
        return
    lines = []
    try:
        with open(gw.SECRETS, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        lines = ["# API keys for the Kindred gateway. Only readable by you; never commit or share it."]
    for k, v in values.items():
        rx = re.compile(r"^\s*#?\s*%s\s*=" % re.escape(k))
        line = "%s=%s" % (k, v)
        for i, old in enumerate(lines):
            if rx.match(old):
                lines[i] = line
                break
        else:
            lines.append(line)
    old_umask = os.umask(0o077)
    try:
        with open(gw.SECRETS + ".tmp", "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        os.chmod(gw.SECRETS + ".tmp", 0o600)
        os.replace(gw.SECRETS + ".tmp", gw.SECRETS)
    finally:
        os.umask(old_umask)


def set_toml(path, section, key, value):
    """Sets key = value in [section] of a simple TOML file (creates the line or the section if needed).
    Returns the old value, or None if there was none."""
    old = None
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        return None  # the brain writes brain.toml on its first start, with the voice on by default
    start = next((i for i, x in enumerate(lines) if x.strip() == "[%s]" % section), None)
    if start is None:
        lines += ["", "[%s]" % section, "%s = %s" % (key, value)]
    else:
        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))
        for i in range(start + 1, end):
            if re.match(r"^\s*%s\s*=" % re.escape(key), lines[i]):
                old = lines[i].split("=", 1)[1].split("#", 1)[0].strip()
                comment = lines[i][lines[i].index("#"):] if "#" in lines[i] else ""
                lines[i] = ("%s = %s" % (key, value)).ljust(29 if comment else 0) + comment
                break
        else:
            lines.insert(start + 1, "%s = %s" % (key, value))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return old


# ---------------------------------------------------------------------- the guide

NAMES = {
    "gemini": "Gemini (your key)", "claude": "your Claude subscription (Claude Code)", "ollama": "Ollama, on this computer",
    "openai": "OpenAI (your key)", "anthropic": "the Claude API (your key)", "groq": "Groq (your key)",
    "openrouter": "OpenRouter (your key)", "mistral": "Mistral (your key)", "codex": "Codex (ChatGPT)",
    "gemini_cli": "Gemini CLI", "cursor": "Cursor agent",
    "stt:local_whisper": "Whisper, on this computer", "stt:groq": "Groq", "stt:openai": "OpenAI",
    "stt:none": "none (you type to her)", "tts:local_kokoro": "Kokoro, on this computer", "tts:openai": "OpenAI",
    "tts:none": "none (subtitles only)", "mem:local": "on this computer", "mem:remote": "on your deployed gateway",
    "emb:local": "understood by a small local model", "emb:gemini": "understood by Gemini",
    "emb:openai": "understood by OpenAI", "emb:none": "keyword search",
}

FIXES = {
    "AI": "the AI isn't answering. A key: check it in ~/.kindred-spirit/secrets.env. Claude: run claude in a "
          "terminal and /login. Ollama: is it running (ollama serve) with the model pulled? Another tool: compare "
          "its template with its --help (docs/GATEWAY.md).",
    "voice": "the voice isn't working: run scripts/setup.sh --install kokoro, or pick another voice with this guide.",
    "speech->text": "speech-to-text isn't working: run scripts/setup.sh --install whisper (needs whisper.cpp: "
                    "brew install whisper-cpp), or pick another option with this guide.",
    "embeddings": "embeddings aren't working: run scripts/setup.sh --install embed, or choose none (memory still works).",
    "memory": "memory isn't working: is the gateway running? For a remote memory, check its address and key.",
}


def run(ask=None, install=True, start=True):
    ask = ask or Ask()
    found = detect()
    print(BOLD + "\nKindred Spirit setup" + OFF)
    print("Your companion needs four things: an AI to think, speech-to-text to hear you, a voice, and a memory.\n"
          "For each, pick what you already have. Everything is yours: keys stay in ~/.kindred-spirit/secrets.env\n"
          "(only you can read it), and you can run this guide again any time to change your choices.")
    ai = ask_ai(ask, found)
    if ai["upstream"] == "claude" and found["claude"]:
        print("  Checking that the Claude CLI is logged in...")
        ok, why = claude_logged_in()
        print("  " + (GREEN + "Logged in." + OFF if ok else RED + "Not ready: " + why + OFF))
        if not ok:
            ai["note"] = "log in to Claude Code: run claude, then /login"
    stt = ask_stt(ask, found, ai)
    tts = ask_tts(ask, found, ai)
    memory = ask_memory(ask, found, ai)
    p = plan(ai, stt, tts, memory)

    print("\n" + BOLD + "Your setup" + OFF)
    print("  The AI:          " + NAMES.get(p["upstream"], p["upstream"]))
    print("  Speech-to-text:  " + NAMES["stt:" + p["stt"]])
    print("  Voice:           " + NAMES["tts:" + p["tts"]])
    print("  Memory:          " + NAMES["mem:" + p["memory"]] + ", " + NAMES["emb:" + p["embeddings"]])
    if p["installs"]:
        print("  To install on this computer: " + ", ".join(p["installs"]))
    if not ask.yes("Save this?"):
        print("Nothing changed.")
        return 1
    changed = apply(p)
    print(GREEN + "Saved." + OFF)
    if install:
        for name in p["installs"]:
            print("\n" + BOLD + "Installing " + name + OFF, flush=True)
            subprocess.run([os.path.join(ROOT, "scripts", "setup.sh"), "--install", name], check=False)
        if p["upstream"] == "ollama" and shutil.which("ollama") and p.get("ollama_model"):
            print("\n" + BOLD + "Getting the Ollama model " + p["ollama_model"] + OFF, flush=True)
            subprocess.run(["ollama", "pull", p["ollama_model"]], check=False)
    if not start:
        return 0
    return finish(p, changed)


def finish(p=None, changed=None):
    """Starts what isn't running yet, tests every part like the brain uses it, and says how to fix
    what failed."""
    p = p or {"notes": []}
    print("\n" + BOLD + "Starting what's needed and testing each part" + OFF, flush=True)
    # (the gateway reads its settings on every request, so a running one already uses the new choices;
    # start.sh starts whatever isn't running yet, like a voice you just installed)
    subprocess.run([os.path.join(ROOT, "scripts", "start.sh"), "--background"], check=False)
    print()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = gw.check()
    lines = buf.getvalue().splitlines()
    for line in lines:
        print("  " + (GREEN if line.startswith("ok") else RED) + line + OFF)
    failed = [line.split()[1] for line in lines if line.startswith("FAIL")]
    for name in failed:
        print("  -> " + FIXES.get(name, "see docs/GATEWAY.md"))
    for note in p["notes"]:
        print("  -> still to do: " + note)
    if changed and changed["voice_changed"]:
        print("  " + DIM + "If the brain was already running, restart it to apply the voice switch: scripts/stop.sh, "
              "then scripts/start.sh" + OFF)
    if code == 0 and not p["notes"]:
        print("\n" + GREEN + BOLD + "All set." + OFF + " Next: python3 scripts/install_profile.py (with the Minecraft "
              "Launcher closed), then play with the \"Kindred Spirit\" profile.\nWatch her think at http://127.0.0.1:11440")
    else:
        print("\nFix what's listed, then run this guide again (or just the test: "
              "brain/.venv/bin/python services/kindred_gateway.py check).")
    return code


if __name__ == "__main__":
    try:
        sys.exit(finish() if sys.argv[1:] == ["--check"] else run())
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. Nothing after the last \"Saved.\" was changed.")
        sys.exit(1)
