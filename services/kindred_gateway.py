#!/usr/bin/env python3
"""Kindred gateway: the one AI address the brain talks to, with live controls.

    Kindred brain -> POST http://127.0.0.1:11437/v1/chat/completions (OpenAI format)
                  -> this gateway (re-reads ~/.kindred-spirit/gateway.json on every request)
                  -> the selected upstream: Gemini (default), Groq, Ollama, OpenAI,
                     OpenRouter, Mistral, or any OpenAI-compatible server you add

Why a gateway:
  * Bring your own AI: switch provider or model here ("upstream ollama"); the brain and the mod
    do not change.
  * Live controls while playing, with no restart: standing personality rules, facts, a one-shot
    hint, model and temperature overrides.
  * Gemini 3 compatibility: Gemini attaches a "thought_signature" to each tool call and rejects
    the next request (HTTP 400) if it is missing from the history. Many OpenAI clients drop it,
    so the gateway remembers signatures by tool-call id and puts them back (Google's documented
    placeholder for calls it never saw).

Keys: each upstream has a "key": "env:NAME" reads that environment variable, or the same name
in ~/.kindred-spirit/secrets.env (KEY=value lines, readable only by you); "client" uses the
bearer token the caller sent; any other string is the key itself; "" means no key.

CLI:
    kindred_gateway.py serve                      run the gateway
    kindred_gateway.py status                     show the current controls
    kindred_gateway.py hint "text"                one-shot hidden instruction for the next reply
    kindred_gateway.py persona "text" | --clear   standing extra rules for every reply
    kindred_gateway.py fact "text" | --clear      add a standing fact
    kindred_gateway.py model NAME | --clear       override the model
    kindred_gateway.py temp 0.9 | --clear         override the temperature
    kindred_gateway.py upstream NAME              switch provider (gemini, groq, ollama, ...)
    kindred_gateway.py pause | resume             pass-through only / controls on
    kindred_gateway.py log [N]                    last N exchanges (default 10)

Standard library only (Python 3.8+).
"""
import contextlib
import copy
import http.client
import json
import logging
import os
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import fcntl
except ImportError:  # Windows: single-user tool, locking is a nicety
    fcntl = None

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = int(os.environ.get("KINDRED_GATEWAY_PORT", "11437"))
HOME = os.path.expanduser("~")
DIR = os.environ.get("KINDRED_HOME") or os.path.join(HOME, ".kindred-spirit")
STATE = os.path.join(DIR, "gateway.json")
SECRETS = os.path.join(DIR, "secrets.env")
LOCK = os.path.join(DIR, ".gateway.lock")
LOG_DIR = os.path.join(DIR, "logs")
TRANSCRIPT = os.path.join(LOG_DIR, "gateway.jsonl")
DUMMY_SIGNATURE = "skip_thought_signature_validator"

DEFAULT_STATE = {
    "upstream": "gemini",
    "paused": False,
    "model": "",
    "temperature": None,
    "reasoning_effort": "",
    "persona": "",
    "facts": [],
    "hint_next": "",
    "upstreams": {
        "gemini": {"base": "https://generativelanguage.googleapis.com/v1beta/openai", "key": "env:GEMINI_API_KEY",
                   "model": "gemini-3.1-flash-lite"},
        "groq": {"base": "https://api.groq.com/openai/v1", "key": "env:GROQ_API_KEY", "model": "llama-3.3-70b-versatile"},
        "ollama": {"base": "http://127.0.0.1:11434/v1", "key": "", "model": "qwen3.5:4b"},
        "openai": {"base": "https://api.openai.com/v1", "key": "env:OPENAI_API_KEY", "model": "gpt-5-mini"},
        "openrouter": {"base": "https://openrouter.ai/api/v1", "key": "env:OPENROUTER_API_KEY", "model": ""},
        "mistral": {"base": "https://api.mistral.ai/v1", "key": "env:MISTRAL_API_KEY", "model": "mistral-small-latest"},
    },
}

log = logging.getLogger("kindred-gateway")
signatures = {}          # tool_call id -> Gemini thought_signature


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


def _read():
    try:
        with open(STATE, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        data = {}
    except ValueError as exc:
        log.error("gateway.json is not valid JSON (%s); using defaults until fixed", exc)
        return copy.deepcopy(DEFAULT_STATE)
    state = copy.deepcopy(DEFAULT_STATE)
    ups = state["upstreams"]
    for name, up in (data.get("upstreams") or {}).items():
        ups[name] = dict(ups.get(name, {}), **up)
    state.update(data)
    state["upstreams"] = ups
    return state


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
    if upstream_name == "gemini":
        for m in msgs:
            for tc in m.get("tool_calls") or []:
                tc.setdefault("extra_content", {}).setdefault("google", {}).setdefault(
                    "thought_signature", signatures.get(tc.get("id"), DUMMY_SIGNATURE))
    req["messages"] = msgs
    return req


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "kindred-gateway/1.0"

    def log_message(self, fmt, *args):
        log.debug("%s %s", self.address_string(), fmt % args)

    def reply(self, status, obj):
        body = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def upstream(self, state):
        name = state.get("upstream") or "gemini"
        if name not in state["upstreams"]:
            log.error("unknown upstream %r; using gemini", name)
            name = "gemini"
        up = state["upstreams"][name]
        key = up.get("key", "")
        if key == "client":
            auth = self.headers.get("Authorization", "")
            key = auth[7:] if auth.lower().startswith("bearer ") else ""
        elif key.startswith("env:"):
            key = secret(key[4:])
        return name, up["base"].rstrip("/"), key

    @staticmethod
    def send_upstream(method, base, key, path, body=None):
        u = urllib.parse.urlsplit(base + path)
        cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
        conn = cls(u.netloc, timeout=120)
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        try:
            conn.request(method, u.path + (("?" + u.query) if u.query else ""), body=body, headers=headers)
            resp = conn.getresponse()
            return resp.status, resp.read()
        finally:
            conn.close()

    def do_GET(self):
        state = load()
        if self.path.rstrip("/") in ("", "/health"):
            self.reply(200, {"status": "ok", "upstream": state.get("upstream"), "paused": state.get("paused")})
            return
        name, base, key = self.upstream(state)
        try:
            status, data = self.send_upstream("GET", base, key, "/models")
        except OSError as exc:
            self.reply(502, {"error": {"message": "%s not reachable: %s" % (name, exc)}})
            return
        self.reply(status, data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self.reply(404, {"error": {"message": "only /v1/chat/completions is served"}})
            return
        try:
            req = json.loads(raw or b"{}")
        except ValueError:
            self.reply(400, {"error": {"message": "invalid JSON"}})
            return

        state = load()
        msgs = req.get("messages") or []
        player = next((text_of(m.get("content")) for m in reversed(msgs) if m.get("role") == "user"), "")
        name, base, key = self.upstream(state)
        paused = state.get("paused")
        hint = "" if paused else state.get("hint_next", "")
        req = shape(req, dict(DEFAULT_STATE, upstreams=state["upstreams"]) if paused else state, name, hint)
        started = time.time()
        try:
            status, data = self.send_upstream("POST", base, key, "/chat/completions",
                                              json.dumps(req, ensure_ascii=False).encode("utf-8"))
        except OSError as exc:
            log.error("%s not reachable: %s", name, exc)
            self.reply(502, {"error": {"message": "%s not reachable: %s" % (name, exc)}})
            return
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
        log.info("%s %s %.1fs | %s -> %s", name, req.get("model"), time.time() - started,
                 player[-120:].replace("\n", " "), (msg.get("content") or "")[:200].replace("\n", " "))
        transcript({"upstream": name, "model": req.get("model"), "seconds": round(time.time() - started, 2),
                    "player": player, "reply": msg.get("content"),
                    "actions": [tc["function"] for tc in msg.get("tool_calls") or []]})
        self.reply(200, resp)


def serve():
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(os.path.join(LOG_DIR, "gateway.log")),
                                  logging.StreamHandler(sys.stderr)])
    if not os.path.exists(STATE):
        change(lambda s: None)
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    server.daemon_threads = True
    log.info("kindred gateway on http://%s:%d/v1 -> %s (controls: %s)", LISTEN_HOST, LISTEN_PORT,
             load().get("upstream"), STATE)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------- CLI

def show(state):
    shown = {k: v for k, v in state.items() if k != "upstreams"}
    shown["upstreams available"] = sorted(state["upstreams"])
    print(json.dumps(shown, indent=2, ensure_ascii=False))


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
    elif cmd == "upstream":
        if text not in load()["upstreams"]:
            print("unknown upstream; choose one of: " + ", ".join(sorted(load()["upstreams"])))
            return 2
        change(lambda s: s.__setitem__("upstream", text))
        print("Upstream: " + text)
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
