#!/usr/bin/env python3
"""Kindred gateway: the one address the brain talks to for everything it needs from the outside.

    brain -> http://127.0.0.1:11437/v1/...
      /chat/completions        AI          Gemini (default), Groq, Ollama, OpenAI, OpenRouter, Mistral, any OpenAI-compatible
      /audio/transcriptions    you -> text local Whisper (default), Groq, OpenAI, any OpenAI-compatible
      /audio/speech            text -> you local Kokoro (default), OpenAI, any OpenAI-compatible (WAV)
      /embeddings              meaning     local small model (default), Gemini, Ollama, OpenAI
      /memory/...              storage     local SQLite file (default), or another gateway deployed elsewhere

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
    },
    # ---- speech to text ----
    "stt": {"use": "local_whisper", "providers": {
        "local_whisper": {"url": "http://127.0.0.1:8083/audio/transcriptions", "key": ""},
        "groq": {"url": "https://api.groq.com/openai/v1/audio/transcriptions", "key": "env:GROQ_API_KEY", "model": "whisper-large-v3-turbo"},
        "openai": {"url": "https://api.openai.com/v1/audio/transcriptions", "key": "env:OPENAI_API_KEY", "model": "gpt-4o-mini-transcribe"},
    }},
    # ---- text to speech ----
    "tts": {"use": "local_kokoro", "providers": {
        # Pip's voice: sky and bella blended, a little brighter; "styles" change how she says each line
        "local_kokoro": {"url": "http://127.0.0.1:8885/v1/audio/speech", "key": "", "model": "kokoro",
                         "voice": "af_sky*0.5+af_bella*0.5", "speed": 1.12, "pitch": 1.08,
                         "styles": {"excited": {"speed": 1.3}, "calm": {"speed": 1.0}, "sad": {"speed": 0.95, "pitch": 1.04},
                                    "whisper": {"voice": "af_sky*0.2+af_bella*0.2+af_nicole*0.6", "speed": 0.95, "gain": 0.45}}},
        "openai": {"url": "https://api.openai.com/v1/audio/speech", "key": "env:OPENAI_API_KEY", "model": "gpt-4o-mini-tts", "voice": "coral"},
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
        return {"cleared": store.clear_docs()}
    if op == "stats":
        return store.stats()
    if op == "reembed":
        return {"reembedded": store.reembed()}
    raise LookupError("unknown memory operation " + op)


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
            else:
                self.err(404, "unknown path " + path)
        except LookupError as exc:
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
        name = state.get("upstream") or "gemini"
        if name not in state["upstreams"]:
            raise LookupError("unknown AI provider %r" % name)
        up = state["upstreams"][name]
        paused = state.get("paused")
        hint = "" if paused else state.get("hint_next", "")
        req = shape(req, dict(DEFAULT_STATE, upstreams=state["upstreams"]) if paused else state, name, hint)
        started = time.time()
        status, data, _ = http_call("POST", up["base"].rstrip("/") + "/chat/completions",
                                    json.dumps(req, ensure_ascii=False).encode("utf-8"),
                                    {"Content-Type": "application/json"}, key_of(up.get("key"), self.headers.get("Authorization", "")))
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
        if len(signatures) > 2000:
            for k in list(signatures)[:1000]:
                signatures.pop(k, None)
        log.info("ai %s %s %.1fs | %s -> %s", name, req.get("model"), time.time() - started,
                 player[-100:].replace("\n", " "), (msg.get("content") or "")[:160].replace("\n", " "))
        usage = resp.get("usage") or {}
        transcript({"upstream": name, "model": req.get("model"), "seconds": round(time.time() - started, 2),
                    "player": player, "reply": msg.get("content"),
                    "actions": [tc["function"] for tc in msg.get("tool_calls") or []],
                    # for the dashboard: what it cost, what it could do, and how it was steered
                    "tokens_in": usage.get("prompt_tokens"), "tokens_out": usage.get("completion_tokens"),
                    "messages": len(req.get("messages") or []),
                    "tools": [(t.get("function") or {}).get("name") for t in req.get("tools") or []],
                    "forced": ((req.get("tool_choice") or {}).get("function") or {}).get("name")
                    if isinstance(req.get("tool_choice"), dict) else None,
                    "controls": {k: v for k, v in (("persona", bool(state.get("persona")) and not paused),
                                                   ("facts", len(state.get("facts") or []) if not paused else 0),
                                                   ("hint", hint)) if v}})
        self.reply(200, resp)

    # -------------------------------------------------------------- speech to text
    def stt(self, state, raw):
        if speech_cleaner.is_silent(raw):
            self.reply(200, {"text": "", "silent": True})
            return
        name, p = provider(state, "stt")
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
    try:
        s, d, _ = post("/audio/speech", {"input": "Testing, one, two, three."})
        wav = d if s == 200 else None
        report("voice", s == 200, "%d KB of WAV" % (len(d) // 1024) if s == 200 else d[:160])
    except Exception as e:
        report("voice", False, str(e))
    if wav:
        try:
            boundary = "kindred" + uuid.uuid4().hex
            body = (b"--" + boundary.encode() + b'\r\nContent-Disposition: form-data; name="file"; filename="t.wav"\r\n'
                    b"Content-Type: audio/wav\r\n\r\n" + wav + b"\r\n--" + boundary.encode() + b"--\r\n")
            s, d, _ = post("/audio/transcriptions", None, body, "multipart/form-data; boundary=" + boundary)
            report("speech->text", s == 200, ("heard: %r" % json.loads(d).get("text")) if s == 200 else d[:160])
        except Exception as e:
            report("speech->text", False, str(e))
    else:
        report("speech->text", False, "skipped (needs the voice to make a test clip)")
    try:
        s, d, _ = post("/embeddings", {"input": ["a test"]})
        report("embeddings", s == 200, "%d numbers per text" % len(json.loads(d)["data"][0]["embedding"]) if s == 200 else d[:160])
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
        if len(args) != 2:
            print("usage: use ai|stt|tts|embeddings|memory PROVIDER")
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
