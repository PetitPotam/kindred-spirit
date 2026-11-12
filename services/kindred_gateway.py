#!/usr/bin/env python3
"""Kindred gateway: the one address the brain talks to for everything it needs from the outside.

    brain -> http://127.0.0.1:11437/v1/...
      /chat/completions        AI          Gemini (default), Groq, Ollama, OpenAI, OpenRouter, Mistral, any OpenAI-compatible
      /audio/transcriptions    you -> text local Whisper (default), Groq, OpenAI, any OpenAI-compatible
      /audio/speech            text -> you local Kokoro (default), OpenAI, any OpenAI-compatible (WAV)
      /embeddings              meaning     local small model (default), Gemini, Ollama, OpenAI
      /memory/...              storage     local SQLite file (default), or another gateway deployed elsewhere
      /knowledge/search        Minecraft   the local knowledge base (services/knowledge, docs/KNOWLEDGE.md)

Every part is chosen in ~/.kindred-spirit/gateway.json (re-read on each request, no restart) or
with the CLI below; keys live in ~/.kindred-spirit/secrets.env. The full guide is
docs/GATEWAY.md. The same program can run on another computer or server ("deployed"): set
KINDRED_GATEWAY_HOST=0.0.0.0 and an access key, and point a local gateway's memory (or the
brain itself) at it.

Things learned the hard way, handled here:
  * Gemini 3 needs each tool call's "thought_signature" sent back; many clients drop it. The
    gateway remembers them by tool-call id and puts them back.
  * Speech-to-text invents words from silence ("Thank you."): silent clips are answered with
    "" before reaching any service, and transcripts are cleaned into one line.
  * Voices must come back as WAV (the game plays WAV): the gateway asks providers for WAV.

CLI:
    kindred_gateway.py serve                       run it
    kindred_gateway.py status                      what each part uses
    kindred_gateway.py check                       test every part (AI, voice, speech, embeddings, memory)
    kindred_gateway.py use ai|stt|tts|embeddings|memory PROVIDER
    kindred_gateway.py voice NAME | model NAME | temp 0.9    (--clear to undo)
    kindred_gateway.py hint|persona|fact "text"    steer the AI (persona/fact: --clear)
    kindred_gateway.py pause | resume              AI pass-through only / controls on
    kindred_gateway.py log [N]                     last AI exchanges

Needs only Python's standard library (numpy makes memory search faster if present).
"""
import contextlib
import copy
import http.client
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import fcntl
except ImportError:  # Windows: single-user tool, locking is a nicety
    fcntl = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import memory_store  # noqa: E402
import speech_cleaner  # noqa: E402

LISTEN_HOST = os.environ.get("KINDRED_GATEWAY_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("KINDRED_GATEWAY_PORT", "11437"))
HOME = os.path.expanduser("~")
DIR = os.environ.get("KINDRED_HOME") or os.path.join(HOME, ".kindred-spirit")
STATE = os.path.join(DIR, "gateway.json")
SECRETS = os.path.join(DIR, "secrets.env")
LOCK = os.path.join(DIR, ".gateway.lock")
LOG_DIR = os.path.join(DIR, "logs")
TRANSCRIPT = os.path.join(LOG_DIR, "gateway.jsonl")
DUMMY_SIGNATURE = "skip_thought_signature_validator"

GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_STATE = {
    # who may use this gateway: "" = anyone on this computer; "env:NAME" = callers must send that key
    "access_key": "",
    # ---- AI (chat) ----
    "upstream": "gemini",
    # another AI for some kinds of call: {"reflect": "claude"} = learn with Claude, talk with the main one
    # (kinds: reply, own, reflect, fold). `use ai claude --for reflect`; `--for reflect --clear` to undo.
    "by_kind": {},
    "paused": False,
    "model": "",
    "temperature": None,
    "reasoning_effort": "",
    "persona": "",
    "facts": [],
    "hint_next": "",
    "upstreams": {
        "gemini": {"base": GEMINI, "key": "env:GEMINI_API_KEY", "model": "gemini-3.1-flash-lite"},
        "groq": {"base": "https://api.groq.com/openai/v1", "key": "env:GROQ_API_KEY", "model": "llama-3.3-70b-versatile"},
        "ollama": {"base": "http://127.0.0.1:11434/v1", "key": "", "model": "qwen3.5:4b"},
        "openai": {"base": "https://api.openai.com/v1", "key": "env:OPENAI_API_KEY", "model": "gpt-5-mini"},
        "openrouter": {"base": "https://openrouter.ai/api/v1", "key": "env:OPENROUTER_API_KEY", "model": ""},
        "mistral": {"base": "https://api.mistral.ai/v1", "key": "env:MISTRAL_API_KEY", "model": "mistral-small-latest"},
        # Claude through the Claude CLI on this computer and your Claude subscription (its usage limits):
        # a fast model at low effort for talking, a stronger one for learning (by kind of call)
        "claude": {"type": "claude_cli", "command": "claude", "model": "haiku", "effort": "low",
                   "by_kind": {"reflect": {"model": "sonnet", "effort": "medium"}}},
        # Claude through the API with a key (pay per use): Anthropic's OpenAI-compatible endpoint
        "anthropic": {"base": "https://api.anthropic.com/v1", "key": "env:ANTHROPIC_API_KEY", "model": "claude-haiku-5-5"},
    },
    # ---- speech to text ----
    "stt": {"use": "local_whisper", "providers": {
        "local_whisper": {"url": "http://127.0.0.1:8083/audio/transcriptions", "key": ""},
        "groq": {"url": "https://api.groq.com/openai/v1/audio/transcriptions", "key": "env:GROQ_API_KEY", "model": "whisper-large-v3-turbo"},
        "openai": {"url": "https://api.openai.com/v1/audio/transcriptions", "key": "env:OPENAI_API_KEY", "model": "gpt-4o-mini-transcribe"},
        "none": {},  # no voice input: you type to her
    }},
    # ---- text to speech ----
    "tts": {"use": "local_kokoro", "providers": {
        # Pip's voice: sky and bella blended, a little brighter; "styles" change how she says each line
        "local_kokoro": {"url": "http://127.0.0.1:8885/v1/audio/speech", "key": "", "model": "kokoro",
                         "voice": "af_sky*0.5+af_bella*0.5", "speed": 1.12, "pitch": 1.08,
                         "styles": {"excited": {"speed": 1.3}, "calm": {"speed": 1.0}, "sad": {"speed": 0.95, "pitch": 1.04},
                                    "whisper": {"voice": "af_sky*0.2+af_bella*0.2+af_nicole*0.6", "speed": 0.95, "gain": 0.45}}},
        "openai": {"url": "https://api.openai.com/v1/audio/speech", "key": "env:OPENAI_API_KEY", "model": "gpt-4o-mini-tts", "voice": "coral"},
        "none": {},  # no voice: subtitles only
    }},
    # ---- embeddings (what memories mean) ----
    "embeddings": {"use": "local", "providers": {
        "local": {"url": "http://127.0.0.1:8891/v1/embeddings", "key": "", "model": "bge-small-en-v1.5"},
        "gemini": {"url": GEMINI + "/embeddings", "key": "env:GEMINI_API_KEY", "model": "gemini-embedding-001"},
        "ollama": {"url": "http://127.0.0.1:11434/v1/embeddings", "key": "", "model": "nomic-embed-text"},
        "openai": {"url": "https://api.openai.com/v1/embeddings", "key": "env:OPENAI_API_KEY", "model": "text-embedding-3-small"},
        "none": {},
    }},
    # ---- memory storage ----
    "memory": {"use": "local", "providers": {
        "local": {"path": os.path.join(DIR, "memory", "kindred.db")},
        "remote": {"base": "https://your-server.example/v1", "key": "env:KINDRED_REMOTE_KEY"},
    }},
}
SECTIONS = {"stt": "stt", "tts": "tts", "embeddings": "embeddings", "memory": "memory"}

log = logging.getLogger("kindred-gateway")
signatures = {}          # tool_call id -> Gemini thought_signature
_stores = {}             # (path, embedding provider) -> memory_store.Store


# ---------------------------------------------------------------- state file

@contextlib.contextmanager
def locked():
    os.makedirs(DIR, exist_ok=True)
    if fcntl is None:
        yield
        return
    with open(LOCK, "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def deep_merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _read():
    try:
        with open(STATE, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        data = {}
    except ValueError as exc:
        log.error("gateway.json is not valid JSON (%s); using defaults until fixed", exc)
        data = {}
    return deep_merge(DEFAULT_STATE, data)


def _write(state):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, STATE)


def load():
    with locked():
        return _read()


def change(fn):
    with locked():
        state = _read()
        fn(state)
        _write(state)
        return state


# ---------------------------------------------------------------- helpers

def secret(name):
    if os.environ.get(name):
        return os.environ[name]
    try:
        with open(SECRETS, encoding="utf-8") as fh:
            for line in fh:
                k, sep, v = line.strip().partition("=")
                if sep and k.strip() == name:
                    return v.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def key_of(spec, caller_auth=""):
    spec = spec or ""
    if spec == "client":
        return caller_auth[7:] if caller_auth.lower().startswith("bearer ") else ""
    if spec.startswith("env:"):
        return secret(spec[4:])
    return spec


def http_call(method, url, body=None, headers=None, key="", timeout=120):
    u = urllib.parse.urlsplit(url)
    cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
    conn = cls(u.netloc, timeout=timeout)
    h = dict(headers or {})
    if key:
        h["Authorization"] = "Bearer " + key
    try:
        conn.request(method, u.path + (("?" + u.query) if u.query else ""), body=body, headers=h)
        resp = conn.getresponse()
        return resp.status, resp.read(), resp.getheader("Content-Type", "")
    finally:
        conn.close()


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def transcript(entry):
    entry["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(TRANSCRIPT, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def provider(state, section):
    sec = state[section]
    name = sec.get("use")
    if name not in sec["providers"]:
        raise LookupError("%s provider %r is not configured (have: %s)" % (section, name, ", ".join(sec["providers"])))
    return name, sec["providers"][name]


# ---------------------------------------------------------------- AI request shaping

def controls_block(state, hint):
    parts = []
    if state.get("persona"):
        parts.append("Additional standing rules for how you behave and speak:\n" + state["persona"])
    if state.get("facts"):
        parts.append("Facts you know to be true (use them naturally when relevant):\n"
                     + "\n".join("- " + f for f in state["facts"]))
    if hint:
        parts.append("For your next reply only: " + hint)
    return "\n\n".join(parts)


def shape(req, state, upstream_name, hint):
    up = state["upstreams"][upstream_name]
    if state.get("model"):
        req["model"] = state["model"]
    elif up.get("model") and (upstream_name != "gemini" or not req.get("model")):
        req["model"] = up["model"]
    if state.get("temperature") is not None:
        req["temperature"] = state["temperature"]
    if state.get("reasoning_effort"):
        req["reasoning_effort"] = state["reasoning_effort"]
    msgs = req.get("messages") or []
    block = controls_block(state, hint)
    if block:
        sys_msg = next((m for m in msgs if m.get("role") == "system"), None)
        if sys_msg is None:
            msgs.insert(0, {"role": "system", "content": block})
        else:
            sys_msg["content"] = text_of(sys_msg.get("content")) + "\n\n" + block
    if up.get("base", "").startswith(GEMINI):
        for m in msgs:
            for tc in m.get("tool_calls") or []:
                tc.setdefault("extra_content", {}).setdefault("google", {}).setdefault(
                    "thought_signature", signatures.get(tc.get("id"), DUMMY_SIGNATURE))
    req["messages"] = msgs
    return req


# ---------------------------------------------------------------- Claude through the Claude CLI

CLAUDE_DIR = os.path.join(DIR, "claude")  # an empty folder to run it in: no project files, no CLAUDE.md


def claude_command(spec):
    """The claude executable: as configured, on PATH, or where its installer puts it."""
    for c in (os.path.expanduser(spec or "claude"), shutil.which(spec or "claude") or "",
              os.path.expanduser("~/.local/bin/claude"), os.path.expanduser("~/.claude/local/claude"),
              "/opt/homebrew/bin/claude", "/usr/local/bin/claude"):
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    raise RuntimeError("the Claude CLI wasn't found: install Claude Code, or set \"command\" for the claude provider")


def claude_prompt(req):
    """An OpenAI-style chat request as a system prompt, one prompt and (with tools) a JSON schema."""
    msgs = req.get("messages") or []
    system = "\n\n".join(text_of(m.get("content")) for m in msgs if m.get("role") == "system")
    lines = []
    for m in msgs:
        role, content = m.get("role"), text_of(m.get("content"))
        if role == "user":
            lines.append("PLAYER (with the game state):\n" + content)
        elif role == "assistant":
            calls = ["(you used the tool %s with %s)" % ((tc.get("function") or {}).get("name"),
                                                        (tc.get("function") or {}).get("arguments"))
                     for tc in m.get("tool_calls") or []]
            lines.append("YOU:\n" + "\n".join(x for x in [content] + calls if x))
        elif role == "tool":
            lines.append("WHAT THE TOOL ANSWERED:\n" + content)
    tools = [t.get("function") or {} for t in req.get("tools") or []]
    forced = ((req.get("tool_choice") or {}).get("function") or {}).get("name") \
        if isinstance(req.get("tool_choice"), dict) else None
    schema = None
    if tools:
        names = [t.get("name") for t in tools]
        system += ("\n\nTools you can use. To use one, answer with \"tool\" set to its name, \"arguments\" "
                   "as an object, and \"reply\" empty: you'll get the result and then answer in words. To just "
                   "talk, set \"tool\" to null and write your answer in \"reply\" (with your usual tags).\n"
                   + "\n".join("- %s: %s Arguments: %s" % (t.get("name"), t.get("description", ""),
                                                          json.dumps(t.get("parameters") or {})) for t in tools))
        if forced and not any(m.get("role") == "tool" for m in msgs):
            system += "\nThis time you must use the tool %s." % forced
            names = [forced]
        schema = {"type": "object", "required": ["reply", "tool"], "properties": {
            "reply": {"type": "string"}, "tool": {"type": ["string", "null"], "enum": names + [None]},
            "arguments": {"type": "object"}}}
    elif (req.get("response_format") or {}).get("type") == "json_object":
        system += "\n\nAnswer with one JSON object and nothing else."
    prompt = "\n\n".join(lines) + "\n\nNow write your next answer."
    return system, prompt, schema


def any_cli_chat(up, req, kind):
    """Any command-line AI the player already has (Codex, Gemini CLI, Cursor's agent...), from a
    template: {"type": "cli", "command": "codex", "args": ["exec", "--model", "{model}", "{prompt}"],
    "output": "text" | "json", "result_field": "result"}. Placeholders: {model} {effort} {system}
    {prompt}; without {prompt} the prompt goes to standard input, without {system} it goes first in
    the prompt. Her tools are asked for as JSON in the answer and read back from it."""
    choice = dict(up, **((up.get("by_kind") or {}).get(kind) or {}))
    system, prompt, schema = claude_prompt(req)
    if schema:
        system += ("\n\nAnswer with ONE JSON object and nothing else: {\"reply\": \"...\", \"tool\": null or a "
                   "tool name, \"arguments\": {...}}")
    args = up.get("args") or ["{prompt}"]
    if "{system}" not in " ".join(args):
        prompt = system + "\n\n" + prompt
    values = {"model": choice.get("model") or "", "effort": choice.get("effort") or "", "system": system,
              "prompt": prompt}
    cmd = [claude_command(up.get("command")) if up.get("command") == "claude" else
           (shutil.which(up.get("command") or "") or os.path.expanduser(up.get("command") or ""))]
    for a in args:
        if a in ("{model}", "{effort}") and not values[a[1:-1]] and cmd and cmd[-1].startswith("-"):
            cmd.pop()  # "--model {model}" with no model: leave both out
            continue
        cmd.append(re.sub(r"\{(model|effort|system|prompt)\}", lambda m: values[m.group(1)], a))
    os.makedirs(CLAUDE_DIR, exist_ok=True)
    try:
        out = subprocess.run(cmd, input=None if "{prompt}" in " ".join(args) else prompt, capture_output=True,
                             text=True, timeout=int(up.get("timeout", 120)), cwd=CLAUDE_DIR)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError("%s: %s" % (up.get("command"), e))
    text = out.stdout.strip()
    if out.returncode != 0 and not text:
        raise RuntimeError("%s failed: %s" % (up.get("command"), out.stderr.strip()[:300]))
    if up.get("output") == "json":
        try:
            text = str(json.loads(text).get(up.get("result_field", "result")) or "")
        except (ValueError, AttributeError):
            pass
    message = {"role": "assistant", "content": text}
    if schema:
        m = re.search(r"\{.*\}", text, re.S)
        try:
            answer = json.loads(m.group(0)) if m else {}
        except ValueError:
            answer = {}
        if answer.get("tool"):
            message = {"role": "assistant", "content": answer.get("reply") or "", "tool_calls": [
                {"id": "call_" + uuid.uuid4().hex[:12], "type": "function",
                 "function": {"name": answer["tool"], "arguments": json.dumps(answer.get("arguments") or {})}}]}
        elif answer:
            message["content"] = answer.get("reply") or ""
    return {"id": "cli-" + uuid.uuid4().hex[:12], "object": "chat.completion", "model": choice.get("model") or
            up.get("command"), "choices": [{"index": 0, "message": message,
                                            "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
            "usage": {"effort": choice.get("effort")}}


def claude_cli_chat(up, req, kind):
    """Answers one chat request with the Claude CLI and returns it in OpenAI's format."""
    choice = dict(up, **((up.get("by_kind") or {}).get(kind) or {}))
    system, prompt, schema = claude_prompt(req)
    cmd = [claude_command(up.get("command")), "-p", "--output-format", "json", "--no-session-persistence",
           "--tools", "", "--strict-mcp-config", "--setting-sources", "user",
           "--model", choice.get("model") or "haiku", "--system-prompt", system]
    if choice.get("effort"):
        cmd += ["--effort", choice["effort"]]
    if schema:
        cmd += ["--json-schema", json.dumps(schema)]
    os.makedirs(CLAUDE_DIR, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    try:
        out = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=int(up.get("timeout", 90)),
                             cwd=CLAUDE_DIR, env=env)
    except subprocess.TimeoutExpired:
        raise RuntimeError("the Claude CLI took too long")
    try:
        r = json.loads(out.stdout)
    except ValueError:
        raise RuntimeError("the Claude CLI failed: %s" % (out.stderr or out.stdout)[:300])
    if r.get("is_error"):
        why = str(r.get("result") or r.get("subtype"))
        if "auth" in why.lower() or "login" in why.lower():
            why += " (run claude in a terminal and /login)"
        raise RuntimeError("Claude CLI: " + why[:300])
    message = {"role": "assistant", "content": r.get("result") or ""}
    if schema:
        answer = r.get("structured_output")
        if not isinstance(answer, dict):
            m = re.search(r"\{.*\}", r.get("result") or "", re.S)
            try:
                answer = json.loads(m.group(0)) if m else {}
            except ValueError:
                answer = {}
        if answer.get("tool"):
            message = {"role": "assistant", "content": answer.get("reply") or "", "tool_calls": [
                {"id": "call_" + uuid.uuid4().hex[:12], "type": "function",
                 "function": {"name": answer["tool"], "arguments": json.dumps(answer.get("arguments") or {})}}]}
        else:
            message["content"] = answer.get("reply") or r.get("result") or ""
    u = r.get("usage") or {}
    tokens_in = sum(u.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    return {"id": "claude-" + uuid.uuid4().hex[:12], "object": "chat.completion", "model": choice.get("model"),
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
            "usage": {"prompt_tokens": tokens_in, "completion_tokens": u.get("output_tokens") or 0,
                      "total_tokens": tokens_in + (u.get("output_tokens") or 0),
                      "cost_usd": r.get("total_cost_usd"), "effort": choice.get("effort")}}


# ---------------------------------------------------------------- embeddings and memory

def embed_texts(state, texts, query=False):
    name, p = provider(state, "embeddings")
    if name == "none" or not p.get("url"):
        return None
    body = {"model": p.get("model", ""), "input": texts}
    if name == "local":
        body["input_type"] = "query" if query else "passage"
    status, data, _ = http_call("POST", p["url"], json.dumps(body).encode(), {"Content-Type": "application/json"},
                                key_of(p.get("key")), timeout=30)
    if status != 200:
        raise RuntimeError("embeddings %s HTTP %s: %s" % (name, status, data[:200]))
    return [d["embedding"] for d in sorted(json.loads(data)["data"], key=lambda d: d["index"])]


def store_for(state):
    name, p = provider(state, "memory")
    if name != "local":
        return None
    ename, ep = provider(state, "embeddings")
    path = os.path.expanduser(p.get("path") or DEFAULT_STATE["memory"]["providers"]["local"]["path"])
    model = "" if ename == "none" else "%s:%s" % (ename, ep.get("model", ""))
    key = (path, model)
    if key not in _stores:
        _stores[key] = memory_store.Store(path, embed=(lambda texts, query=False: embed_texts(load(), texts, query))
                                          if model else None, model_name=model)
    return _stores[key]


def memory_call(store, op, req):
    if op == "add":
        mid, merged = store.add(req.get("kind", "note"), req.get("text", ""), req.get("world"),
                                req.get("importance", 5), req.get("meta"), req.get("dedupe"))
        return {"id": mid, "merged": merged}
    if op == "search":
        return {"results": store.search(req.get("query", ""), req.get("kinds"), req.get("world"), req.get("k", 8),
                                        all_worlds=bool(req.get("all_worlds")), strict=bool(req.get("strict")))}
    if op == "list":
        return {"results": store.list(req.get("kinds"), req.get("world"), req.get("limit", 50), req.get("order", "recent"),
                                      all_worlds=bool(req.get("all_worlds")), strict=bool(req.get("strict")))}
    if op == "update":
        return {"ok": store.update(req["id"], req.get("text"), req.get("importance"), req.get("meta"))}
    if op == "delete":
        return {"deleted": store.delete(req.get("id"), req.get("kinds"), req.get("world"), req.get("contains"),
                                        strict=bool(req.get("strict")))}
    if op == "doc":
        return {"value": store.doc(req["key"], req.get("value"))}
    if op == "docs":  # the saved documents (keys, sizes, when), for the dashboard
        return {"docs": store.docs(req.get("prefix", ""))}
    if op == "clear_docs":
        return {"cleared": store.clear_docs(req.get("prefix", ""))}
    if op == "stats":
        return store.stats()
    if op == "reembed":
        return {"reembedded": store.reembed()}
    raise LookupError("unknown memory operation " + op)


# ---------------------------------------------------------------- knowledge base (docs/KNOWLEDGE.md)

def knowledge_call(state, op, req):
    """/v1/knowledge/search|stats|sources: services/knowledge/api.py, with this gateway's embedder."""
    from knowledge import api as knowledge_api
    ename, ep = provider(state, "embeddings")
    model = "" if ename == "none" else "%s:%s" % (ename, ep.get("model", ""))
    return knowledge_api.call(op, req, embed=lambda texts, query=False: embed_texts(load(), texts, query), model=model)


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "kindred-gateway/2.0"

    def log_message(self, fmt, *args):
        log.debug("%s %s", self.address_string(), fmt % args)

    def reply(self, status, obj, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def err(self, status, message):
        self.reply(status, {"error": {"message": message}})

    def allowed(self, state):
        need = key_of(state.get("access_key", ""))
        if not need:
            return True
        auth = self.headers.get("Authorization", "")
        return auth == "Bearer " + need

    def route(self):
        p = self.path.split("?")[0].rstrip("/")
        return p[3:] if p.startswith("/v1") else p

    def do_GET(self):
        state = load()
        path = self.route()
        if path in ("", "/health"):
            self.reply(200, {"status": "ok", "ai": state.get("upstream"), "stt": state["stt"]["use"],
                             "tts": state["tts"]["use"], "embeddings": state["embeddings"]["use"],
                             "memory": state["memory"]["use"], "paused": state.get("paused")})
            return
        if not self.allowed(state):
            self.err(401, "this gateway needs an access key")
            return
        if path == "/models":
            name, up = state.get("upstream") or "gemini", state["upstreams"].get(state.get("upstream") or "gemini", {})
            try:
                status, data, _ = http_call("GET", up["base"].rstrip("/") + "/models", key=key_of(up.get("key")))
            except OSError as exc:
                self.err(502, "%s not reachable: %s" % (name, exc))
                return
            self.reply(status, data)
            return
        self.err(404, "not found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        state = load()
        if not self.allowed(state):
            self.err(401, "this gateway needs an access key")
            return
        path = self.route()
        try:
            if path == "/chat/completions":
                self.chat(state, raw)
            elif path == "/audio/transcriptions":
                self.stt(state, raw)
            elif path == "/audio/speech":
                self.tts(state, raw)
            elif path == "/embeddings":
                req = json.loads(raw or b"{}")
                texts = req.get("input")
                vecs = embed_texts(state, [texts] if isinstance(texts, str) else texts, req.get("input_type") == "query")
                if vecs is None:
                    self.err(503, "no embedding provider configured")
                    return
                self.reply(200, {"object": "list", "data": [{"object": "embedding", "index": i, "embedding": v}
                                                            for i, v in enumerate(vecs)]})
            elif path.startswith("/memory/"):
                self.memory(state, path[len("/memory/"):], raw)
            elif path.startswith("/knowledge/"):  # the Minecraft knowledge base (services/knowledge, read-only)
                self.reply(200, knowledge_call(state, path[len("/knowledge/"):], json.loads(raw or b"{}")))
            elif path == "/control":  # the special instructions, from the game (/kindred persona ...)
                self.reply(200, control(json.loads(raw or b"{}")))
            else:
                self.err(404, "unknown path " + path)
        except LookupError as exc:
            log.warning("%s refused: %r", path, exc)
            self.err(400, str(exc))
        except (OSError, RuntimeError) as exc:
            log.error("%s failed: %s", path, exc)
            self.err(502, str(exc))
        except ValueError as exc:
            self.err(400, "bad request: %s" % exc)

    # -------------------------------------------------------------- AI
    def chat(self, state, raw):
        req = json.loads(raw or b"{}")
        msgs = req.get("messages") or []
        player = next((text_of(m.get("content")) for m in reversed(msgs) if m.get("role") == "user"), "")
        kind = self.headers.get("X-Kindred-Kind") or "reply"  # reply, own, reflect, fold (from the brain)
        name = pick_upstream(state, kind)
        if name not in state["upstreams"]:
            raise LookupError("unknown AI provider %r" % name)
        up = state["upstreams"][name]
        paused = state.get("paused")
        hint = "" if paused else state.get("hint_next", "")
        req = shape(req, dict(DEFAULT_STATE, upstreams=state["upstreams"]) if paused else state, name, hint)
        by_kind = (up.get("by_kind") or {}).get(kind) or {}
        if by_kind.get("model") and not state.get("model") and up.get("type") not in ("claude_cli", "cli"):
            req["model"] = by_kind["model"]
        started = time.time()
        stream = bool(req.get("stream"))
        if up.get("type") in ("claude_cli", "cli"):  # an AI command-line tool the player already has
            req.pop("stream", None)
            resp = (claude_cli_chat if up["type"] == "claude_cli" else any_cli_chat)(up, req, kind)
            req["model"] = resp["model"]
            status, data = 200, json.dumps(resp).encode()
        elif stream:  # her words as they're written: the brain starts speaking at the first sentence
            req["stream_options"] = {"include_usage": True}
            return self.chat_stream(state, up, req, name, kind, player, hint, paused, started)
        else:
            status, data, _ = http_call("POST", up["base"].rstrip("/") + "/chat/completions",
                                        json.dumps(req, ensure_ascii=False).encode("utf-8"),
                                        {"Content-Type": "application/json"},
                                        key_of(up.get("key"), self.headers.get("Authorization", "")))
        if status != 200:
            log.error("%s HTTP %s: %s", name, status, data[:400])
            self.reply(status, data)
            return
        if hint:
            change(lambda s: s.__setitem__("hint_next", ""))
        try:
            resp = json.loads(data)
            msg = resp["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError):
            self.reply(status, data)
            return
        for tc in msg.get("tool_calls") or []:
            sig = ((tc.pop("extra_content", None) or {}).get("google") or {}).get("thought_signature")
            if sig and tc.get("id"):
                signatures[tc["id"]] = sig
        msg.pop("extra_content", None)
        self.log_ai(state, req, name, kind, player, hint, paused, started, msg.get("content"),
                    [tc["function"] for tc in msg.get("tool_calls") or []], resp.get("usage") or {})
        if stream:  # (a provider that can't stream: the whole answer as one piece)
            return self.sse_whole(resp)
        self.reply(200, resp)

    def chat_stream(self, state, up, req, name, kind, player, hint, paused, started):
        """Passes the AI's answer through as it is written (server-sent events), and keeps what the
        non-streaming path keeps: the transcript, tool calls, Gemini's thought signatures, usage."""
        u = urllib.parse.urlsplit(up["base"].rstrip("/") + "/chat/completions")
        conn = (http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection)(u.netloc, timeout=120)
        headers = {"Content-Type": "application/json"}
        key = key_of(up.get("key"), self.headers.get("Authorization", ""))
        if key:
            headers["Authorization"] = "Bearer " + key
        try:
            conn.request("POST", u.path, body=json.dumps(req, ensure_ascii=False).encode("utf-8"), headers=headers)
            resp = conn.getresponse()
            if resp.status != 200:
                data = resp.read()
                log.error("%s HTTP %s: %s", name, resp.status, data[:400])
                self.reply(resp.status, data)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            if hint:
                change(lambda s: s.__setitem__("hint_next", ""))
            content, calls, ids, usage = [], {}, {}, {}
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except ValueError:
                    continue
                usage = chunk.get("usage") or usage
                for ch in chunk.get("choices") or []:
                    d = ch.get("delta") or {}
                    content.append(d.get("content") or "")
                    for tc in d.get("tool_calls") or []:
                        i = tc.get("index", 0)
                        ids[i] = tc.get("id") or ids.get(i)
                        sig = ((tc.pop("extra_content", None) or {}).get("google") or {}).get("thought_signature")
                        if sig and ids.get(i):
                            signatures[ids[i]] = sig
                        c = calls.setdefault(i, {"name": "", "arguments": ""})
                        f = tc.get("function") or {}
                        c["name"] += f.get("name") or ""
                        c["arguments"] += f.get("arguments") or ""
                    d.pop("extra_content", None)
                self.wfile.write(("data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n").encode("utf-8"))
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (OSError, http.client.HTTPException) as exc:
            log.error("%s stream failed: %s", name, exc)
            return
        finally:
            conn.close()
        self.log_ai(state, req, name, kind, player, hint, paused, started, "".join(content),
                    [calls[i] for i in sorted(calls)], usage)

    def sse_whole(self, resp):
        msg = resp["choices"][0]["message"]
        delta = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            delta["tool_calls"] = [dict(tc, index=i) for i, tc in enumerate(msg["tool_calls"])]
        chunk = {"choices": [{"index": 0, "delta": delta, "finish_reason": resp["choices"][0].get("finish_reason")}],
                 "usage": resp.get("usage")}
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self.wfile.write(("data: %s\n\ndata: [DONE]\n\n" % json.dumps(chunk, ensure_ascii=False)).encode("utf-8"))
        self.wfile.flush()

    def log_ai(self, state, req, name, kind, player, hint, paused, started, content, actions, usage):
        if len(signatures) > 2000:
            for k in list(signatures)[:1000]:
                signatures.pop(k, None)
        log.info("ai %s %s %.1fs%s | %s -> %s", name, req.get("model"), time.time() - started,
                 " streamed" if req.get("stream") else "", player[-100:].replace("\n", " "),
                 (content or "")[:160].replace("\n", " "))
        transcript({"upstream": name, "model": req.get("model"), "seconds": round(time.time() - started, 2),
                    "player": player, "reply": content, "actions": actions, "streamed": bool(req.get("stream")),
                    # for the dashboard: what it cost, what it could do, and how it was steered
                    "tokens_in": usage.get("prompt_tokens"), "tokens_out": usage.get("completion_tokens"),
                    "kind": kind, "cost_usd": usage.get("cost_usd"), "effort": usage.get("effort"),
                    "messages": len(req.get("messages") or []),
                    "tools": [(t.get("function") or {}).get("name") for t in req.get("tools") or []],
                    "forced": ((req.get("tool_choice") or {}).get("function") or {}).get("name")
                    if isinstance(req.get("tool_choice"), dict) else None,
                    "controls": {k: v for k, v in (("persona", bool(state.get("persona")) and not paused),
                                                   ("facts", len(state.get("facts") or []) if not paused else 0),
                                                   ("hint", hint)) if v}})

    # -------------------------------------------------------------- speech to text
    def stt(self, state, raw):
        if speech_cleaner.is_silent(raw):
            self.reply(200, {"text": "", "silent": True})
            return
        name, p = provider(state, "stt")
        if name == "none" or not p.get("url"):
            self.err(503, "speech-to-text is off (none): type to her instead")
            return
        ctype = self.headers.get("Content-Type", "")
        body = speech_cleaner.with_model(raw, ctype, p.get("model", ""))
        started = time.time()
        status, data, rtype = http_call("POST", p["url"], body, {"Content-Type": ctype}, key_of(p.get("key")))
        if status != 200:
            log.error("stt %s HTTP %s: %s", name, status, data[:300])
            self.reply(status, data, rtype or "application/json")
            return
        try:
            text = speech_cleaner.clean(json.loads(data).get("text", ""))
        except ValueError:
            text = speech_cleaner.clean(data.decode("utf-8", "replace"))
        log.info("stt %s %.2fs: %r", name, time.time() - started, text)
        self.reply(200, {"text": text})

    # -------------------------------------------------------------- text to speech
    def tts(self, state, raw):
        req = json.loads(raw or b"{}")
        name, p = provider(state, "tts")
        if name == "none" or not p.get("url"):
            self.err(503, "the voice is off (none): subtitles only")
            return
        text = re.sub(r"\[[^\]]*\]|\{[a-z_]+\}|[*_`#~]+", " ", req.get("input") or "")  # mood/gesture tags
        text = re.sub(r"\s+", " ", text).strip()[:800]
        if not text:
            self.err(400, "nothing to say")
            return
        body = {"model": p.get("model", ""), "input": text, "voice": req.get("voice") or p.get("voice", ""),
                "response_format": "wav", "speed": req.get("speed") or p.get("speed", 1.0)}
        for k in ("pitch", "gain"):  # extras only some providers understand (local Kokoro does)
            if p.get(k):
                body[k] = p[k]
        style = (p.get("styles") or {}).get(req.get("style") or "")
        if style:  # how she says it: excited, calm, sad, whisper...
            body.update(style)
        started = time.time()
        status, data, rtype = http_call("POST", p["url"], json.dumps(body).encode(), {"Content-Type": "application/json"},
                                        key_of(p.get("key")), timeout=60)
        if status != 200 or not data.startswith(b"RIFF"):
            log.error("tts %s HTTP %s (%s): %s", name, status, rtype, data[:200])
            self.err(502 if status == 200 else status, "the voice service did not return WAV audio")
            return
        log.info("tts %s %.2fs, %d chars", name, time.time() - started, len(text))
        self.reply(200, data, "audio/wav")

    # -------------------------------------------------------------- memory
    def memory(self, state, op, raw):
        req = json.loads(raw or b"{}")
        name, p = provider(state, "memory")
        if name != "local":  # a gateway deployed elsewhere keeps the memories
            status, data, rtype = http_call("POST", p["base"].rstrip("/") + "/memory/" + op, raw,
                                            {"Content-Type": "application/json"}, key_of(p.get("key")), timeout=30)
            self.reply(status, data, rtype or "application/json")
            return
        self.reply(200, memory_call(store_for(state), op, req))


def serve():
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(os.path.join(LOG_DIR, "gateway.log")), logging.StreamHandler(sys.stderr)])
    if not os.path.exists(STATE):
        change(lambda s: None)
    state = load()
    if LISTEN_HOST not in ("127.0.0.1", "localhost") and not key_of(state.get("access_key", "")):
        log.warning("listening on %s WITHOUT an access key: anyone who can reach it can use your AI keys. "
                    "Set \"access_key\": \"env:KINDRED_GATEWAY_KEY\" in gateway.json.", LISTEN_HOST)
    ThreadingHTTPServer.request_queue_size = 128  # the brain asks 6 memory questions at once; 5 waiting was too few
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    server.daemon_threads = True
    log.info("kindred gateway on http://%s:%d/v1 | ai %s, stt %s, tts %s, embeddings %s, memory %s", LISTEN_HOST,
             LISTEN_PORT, state["upstream"], state["stt"]["use"], state["tts"]["use"], state["embeddings"]["use"],
             state["memory"]["use"])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------- CLI

def show(state):
    print("AI           %s (model %s)" % (state["upstream"], state.get("model") or state["upstreams"][state["upstream"]].get("model")))
    for sec, label in (("stt", "speech->text"), ("tts", "voice"), ("embeddings", "embeddings"), ("memory", "memory")):
        name = state[sec]["use"]
        p = state[sec]["providers"].get(name, {})
        extra = p.get("voice") or p.get("model") or p.get("path") or p.get("base") or p.get("url") or ""
        print("%-12s %s %s" % (label, name, "(%s)" % extra if extra else ""))
        print("%-12s   options: %s" % ("", ", ".join(state[sec]["providers"])))
    print("AI options:  " + ", ".join(state["upstreams"]))
    controls = {k: state[k] for k in ("persona", "facts", "hint_next", "temperature", "paused") if state.get(k)}
    if controls:
        print("controls:    " + json.dumps(controls, ensure_ascii=False))


def check():
    """Tests each part through the running gateway, like the brain would."""
    base = "http://127.0.0.1:%d/v1" % LISTEN_PORT
    key = key_of(load().get("access_key", ""))
    ok = True

    def post(path, obj, raw=None, ctype="application/json"):
        return http_call("POST", base + path, raw if raw is not None else json.dumps(obj).encode(),
                         {"Content-Type": ctype}, key, timeout=60)

    def report(name, good, detail):
        nonlocal ok
        ok = ok and good
        print("%s %-12s %s" % ("ok  " if good else "FAIL", name, detail))

    try:
        s, d, _ = post("/chat/completions", {"model": "", "max_tokens": 20,
                                             "messages": [{"role": "user", "content": "Say hello in three words."}]})
        report("AI", s == 200, json.loads(d)["choices"][0]["message"]["content"].strip()[:60] if s == 200 else d[:160])
    except Exception as e:
        report("AI", False, str(e))
    wav = None
    state = load()
    if state["tts"]["use"] == "none":
        report("voice", True, "off, by your choice (subtitles only)")
    else:
        try:
            s, d, _ = post("/audio/speech", {"input": "Testing, one, two, three."})
            wav = d if s == 200 else None
            report("voice", s == 200, "%d KB of WAV" % (len(d) // 1024) if s == 200 else d[:160])
        except Exception as e:
            report("voice", False, str(e))
    if state["stt"]["use"] == "none":
        report("speech->text", True, "off, by your choice (you type to her)")
    elif wav:
        try:
            boundary = "kindred" + uuid.uuid4().hex
            body = (b"--" + boundary.encode() + b'\r\nContent-Disposition: form-data; name="file"; filename="t.wav"\r\n'
                    b"Content-Type: audio/wav\r\n\r\n" + wav + b"\r\n--" + boundary.encode() + b"--\r\n")
            s, d, _ = post("/audio/transcriptions", None, body, "multipart/form-data; boundary=" + boundary)
            report("speech->text", s == 200, ("heard: %r" % json.loads(d).get("text")) if s == 200 else d[:160])
        except Exception as e:
            report("speech->text", False, str(e))
    elif state["tts"]["use"] == "none":
        report("speech->text", True, "not tested (it needs her voice to make a test clip); talk to her to try it")
    else:
        report("speech->text", False, "skipped (needs the voice to make a test clip)")
    if state["embeddings"]["use"] == "none":
        report("embeddings", True, "off, by your choice (memory uses keyword search)")
    else:
        try:
            s, d, _ = post("/embeddings", {"input": ["a test"]})
            report("embeddings", s == 200,
                   "%d numbers per text" % len(json.loads(d)["data"][0]["embedding"]) if s == 200 else d[:160])
        except Exception as e:
            report("embeddings", False, str(e))
    try:
        s, d, _ = post("/memory/add", {"kind": "test", "text": "gateway check, please ignore"})
        mid = json.loads(d)["id"]
        s2, d2, _ = post("/memory/search", {"query": "gateway check", "kinds": ["test"], "all_worlds": True, "k": 1})
        found = json.loads(d2)["results"]
        post("/memory/delete", {"id": mid, "kinds": ["test"]})
        report("memory", bool(found) and found[0]["id"] == mid, "stored, found and removed a test memory")
    except Exception as e:
        report("memory", False, str(e))
    return 0 if ok else 1


def pick_upstream(state, kind):
    """Which AI answers this kind of call: its own choice in by_kind, else the main one."""
    name = (state.get("by_kind") or {}).get(kind)
    return name if name in state["upstreams"] else state.get("upstream") or "gemini"


def control(req):
    """Change the special instructions: {"op": persona|fact|hint|model|temp|pause|resume|status,
    "text": "...", "clear": bool}. Returns what they are now."""
    op, text, clear = req.get("op", "status"), (req.get("text") or "").strip(), bool(req.get("clear"))
    if op == "persona":
        change(lambda s: s.__setitem__("persona", "" if clear else text))
    elif op == "fact":
        change(lambda s: s.__setitem__("facts", []) if clear else s["facts"].append(text))
    elif op == "hint":
        change(lambda s: s.__setitem__("hint_next", "" if clear else text))
    elif op == "model":
        change(lambda s: s.__setitem__("model", "" if clear else text))
    elif op == "temp":
        change(lambda s: s.__setitem__("temperature", None if clear or not text else float(text)))
    elif op in ("pause", "resume"):
        change(lambda s: s.__setitem__("paused", op == "pause"))
    elif op != "status":
        raise LookupError("unknown control %r" % op)
    s = load()
    return {"persona": s.get("persona", ""), "facts": s.get("facts", []), "hint_next": s.get("hint_next", ""),
            "model": s.get("model", ""), "temperature": s.get("temperature"), "paused": bool(s.get("paused")),
            "ai": s.get("upstream")}


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    text = " ".join(args)
    clear = args[:1] == ["--clear"]
    if cmd == "serve":
        serve()
    elif cmd == "status":
        show(load())
    elif cmd == "check":
        return check()
    elif cmd == "use":
        kind = args[args.index("--for") + 1] if "--for" in args and args.index("--for") + 1 < len(args) else None
        clear = clear or "--clear" in args
        args = [a for i, a in enumerate(args) if a not in ("--for", "--clear") and (i == 0 or args[i - 1] != "--for")]
        if kind:  # one kind of call to another AI: use ai claude --for reflect
            if kind not in ("reply", "own", "reflect", "fold"):
                print("kinds: reply (answering you), own (things she says on her own), reflect (learning), fold (summaries)")
                return 2
            state = load()
            name = args[1] if len(args) == 2 else ""
            if name and name not in state["upstreams"]:
                print("unknown AI provider; choose one of: " + ", ".join(state["upstreams"]))
                return 2
            change(lambda s: s.setdefault("by_kind", {}).__setitem__(kind, name) if name and not clear
                   else s.setdefault("by_kind", {}).pop(kind, None))
            print("%s calls now use %s" % (kind, name if name and not clear else "the main AI (%s)" % load()["upstream"]))
            return 0
        if len(args) != 2:
            print("usage: use ai|stt|tts|embeddings|memory PROVIDER   (or: use ai PROVIDER --for reflect)")
            return 2
        part, name = args
        state = load()
        if part == "ai":
            if name not in state["upstreams"]:
                print("unknown AI provider; choose one of: " + ", ".join(state["upstreams"]))
                return 2
            change(lambda s: s.__setitem__("upstream", name))
        elif part in SECTIONS:
            if name not in state[part]["providers"]:
                print("unknown %s provider; choose one of: %s" % (part, ", ".join(state[part]["providers"])))
                return 2
            change(lambda s: s[part].__setitem__("use", name))
        else:
            print("parts: ai, stt, tts, embeddings, memory")
            return 2
        print("%s now uses %s" % (part, name))
    elif cmd == "upstream":  # old name for "use ai"
        return main(["use", "ai"] + args)
    elif cmd == "voice":
        def setv(s):
            name, _ = provider(s, "tts")
            s["tts"]["providers"][name]["voice"] = "" if clear else text
        change(setv)
        print("Voice: " + ("provider default" if clear else text))
    elif cmd == "hint":
        change(lambda s: s.__setitem__("hint_next", text))
        print("Hint queued for the next reply.")
    elif cmd == "persona":
        change(lambda s: s.__setitem__("persona", "" if clear else text))
        print("Persona cleared." if clear else "Persona set.")
    elif cmd == "fact":
        change(lambda s: s.__setitem__("facts", []) if clear else s["facts"].append(text))
        print("Facts cleared." if clear else "Fact added.")
    elif cmd == "model":
        change(lambda s: s.__setitem__("model", "" if clear else text))
        print("Model override cleared." if clear else "Model: " + text)
    elif cmd == "temp":
        change(lambda s: s.__setitem__("temperature", None if clear else float(text)))
        print("Temperature override cleared." if clear else "Temperature: " + text)
    elif cmd in ("pause", "resume"):
        change(lambda s: s.__setitem__("paused", cmd == "pause"))
        print("Controls paused (pass-through)." if cmd == "pause" else "Controls active.")
    elif cmd == "log":
        n = int(args[0]) if args else 10
        try:
            with open(TRANSCRIPT, encoding="utf-8") as fh:
                lines = fh.readlines()[-n:]
        except FileNotFoundError:
            lines = []
        for line in lines:
            e = json.loads(line)
            print("%s  (%s, %ss)" % (e["time"], e.get("model"), e.get("seconds")))
            print("   asked: %s" % (e.get("player") or "")[-200:])
            print("   reply: %s" % e.get("reply"))
    else:
        print("unknown command %r (try --help)" % cmd)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
