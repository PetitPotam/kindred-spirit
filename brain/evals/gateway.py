"""The gateway the brain talks to during an eval: one local HTTP server standing in for the real one.

- AI (/chat/completions): in "stub" and "local" modes, the case's scripted answers (what the real AI
  said in the playtest); in "live" mode, passed on to the real gateway (streamed as it comes) and
  recorded. Reflection calls are never passed on: an eval is one moment, not a session to learn from.
- Memory (/memory/*): a fresh store in a temporary folder, seeded per case. The player's real
  memories are never read or written.
- Embeddings (System 0's understanding) and the knowledge base: passed on in "local" and "live"
  modes (both on this computer, free; knowledge "learn" is refused so nothing is crawled or written);
  absent in "stub" mode, like CI.
- Voice: a tiny silent WAV.

Every AI request and answer is kept (self.calls) so a run can say how many calls, rounds and tokens
an answer took, and what was forced or offered.
"""
import io
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVICES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "services")


def _memory_modules(services=None):
    services = services or SERVICES
    if services not in sys.path:
        sys.path.insert(0, services)
    import memory_store  # noqa: E402
    import kindred_gateway  # noqa: E402  (only for memory_call: the same operations as the real gateway)
    return memory_store, kindred_gateway.memory_call


def silent_wav(seconds=0.1, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * int(seconds * rate))
    return buf.getvalue()


class EvalGateway:
    def __init__(self, mode="stub", upstream="http://127.0.0.1:11437/v1", key="", services=None):
        self.mode, self.upstream, self.key = mode, upstream.rstrip("/"), key
        memory_store, self._memory_call = _memory_modules(services)
        self.store = memory_store.Store(os.path.join(tempfile.mkdtemp(prefix="kindred-eval-"), "m.db"))
        self.script, self.calls, self.lock = [], [], threading.Lock()
        self.wav = silent_wav()
        gw = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                try:
                    gw.route(self, body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def send_bytes(self, code, data, ctype):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        ThreadingHTTPServer.request_queue_size = 128
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        self.url = "http://127.0.0.1:%d/v1" % self.port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()

    # ------------------------------------------------------------------ per case

    def begin(self, script):
        with self.lock:
            self.script = [dict(m) for m in script or []]
            self.calls = []

    def seed(self, world, history=(), memories=(), docs=None):
        """What she already knows when the moment starts: the conversation so far and some memories."""
        if history:
            self.store.doc("world:%s:history" % world, [{"role": r, "content": c} for r, c in history])
        for m in memories or ():
            self.store.add(m.get("kind", "player"), m["text"], world, m.get("importance", 6), m.get("meta") or {}, None)
        for k, v in (docs or {}).items():
            self.store.doc(k % {"world": world}, v)

    # ------------------------------------------------------------------ routes

    def route(self, h, body):
        path = h.path
        if "/memory/" in path:
            out = self._memory_call(self.store, path.rsplit("/", 1)[1], json.loads(body or b"{}"))
            return h.send_bytes(200, json.dumps(out).encode(), "application/json")
        if path.endswith("/audio/speech"):
            return h.send_bytes(200, self.wav, "audio/wav")
        if path.endswith("/embeddings") or "/knowledge/" in path:
            if self.mode == "stub" or path.endswith("/knowledge/learn"):
                if "/knowledge/" in path:
                    return h.send_bytes(200, b'{"covered": false, "best": 0.0, "results": []}', "application/json")
                return h.send_bytes(503, b'{"error": "no embeddings in stub mode"}', "application/json")
            return self.forward(h, path, body)
        if path.endswith("/chat/completions"):
            return self.chat(h, body)
        h.send_bytes(404, b"{}", "application/json")

    def forward(self, h, path, body):
        code, data, ctype = self._post(path, body, {})
        h.send_bytes(code, data, ctype)

    def _post(self, path, body, headers):
        url = self.upstream + path[path.index("/v1") + 3:] if "/v1" in path else self.upstream + path
        req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
        for k, v in headers.items():
            req.add_header(k, v)
        if self.key:
            req.add_header("Authorization", "Bearer " + self.key)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read(), r.headers.get("Content-Type") or "application/json"
        except urllib.error.HTTPError as e:
            return e.code, e.read(), "application/json"
        except (urllib.error.URLError, OSError) as e:
            return 502, json.dumps({"error": str(e)}).encode(), "application/json"

    def chat(self, h, body):
        req = json.loads(body or b"{}")
        kind = h.headers.get("X-Kindred-Kind", "")
        call = {"kind": kind, "at": time.time(), "request": req}
        with self.lock:
            self.calls.append(call)
        if kind == "reflect":  # (learning and her instinct lines: not part of a moment)
            call["answer"] = {"role": "assistant", "content": "{}"}
            return h.send_bytes(200, json.dumps({"choices": [{"message": call["answer"]}]}).encode(), "application/json")
        if self.mode != "live":
            with self.lock:
                msg = self.script.pop(0) if self.script else {"role": "assistant", "content": "[calm] Hm."}
                msg = self.obey(req, msg)
            call["answer"], call["seconds"] = msg, 0.0
            return h.send_bytes(200, json.dumps({"choices": [{"message": msg}]}).encode(), "application/json")
        return self.stream_live(h, body, kind, call)

    def obey(self, req, msg):
        """A forced tool (System 0's tool_choice) is what a real AI must call: the scripted answer gives
        way to it (with the script's arguments for that tool, if it has some), and its words come next."""
        tc = req.get("tool_choice")
        forced = ((tc or {}).get("function") or {}).get("name") if isinstance(tc, dict) else None
        if not forced or not req.get("tools"):
            return msg
        if any((c.get("function") or {}).get("name") == forced for c in msg.get("tool_calls") or []):
            return msg
        scripted = [c for m in [msg] + self.script for c in m.get("tool_calls") or []
                    if (c.get("function") or {}).get("name") == forced]
        args = scripted[0]["function"]["arguments"] if scripted else "{}"
        if not msg.get("tool_calls"):
            self.script.insert(0, msg)  # (its words, after the tool)
        return {"role": "assistant", "content": "", "tool_calls": [
            {"id": "forced", "type": "function", "function": {"name": forced, "arguments": args}}]}

    def stream_live(self, h, body, kind, call):
        url = self.upstream + "/chat/completions"
        req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
        if kind:
            req.add_header("X-Kindred-Kind", kind)
        if self.key:
            req.add_header("Authorization", "Bearer " + self.key)
        started = time.time()
        try:
            r = urllib.request.urlopen(req, timeout=90)
        except urllib.error.HTTPError as e:
            data = e.read()
            call["error"] = data[:300].decode("utf-8", "replace")
            return h.send_bytes(e.code, data, "application/json")
        except (urllib.error.URLError, OSError) as e:
            call["error"] = str(e)
            return h.send_bytes(502, json.dumps({"error": str(e)}).encode(), "application/json")
        with r:
            ctype = r.headers.get("Content-Type") or ""
            if "event-stream" not in ctype:
                data = r.read()
                try:
                    whole = json.loads(data)
                    call["answer"] = (whole.get("choices") or [{}])[0].get("message")
                    call["usage"] = whole.get("usage") or {}
                except ValueError:
                    pass
                call["seconds"] = round(time.time() - started, 2)
                return h.send_bytes(r.status, data, ctype or "application/json")
            h.send_response(200)
            h.send_header("Content-Type", "text/event-stream")
            h.send_header("Connection", "close")
            h.end_headers()
            h.close_connection = True
            content, calls, usage = "", {}, {}
            for raw in r:
                h.wfile.write(raw)
                h.wfile.flush()
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                    continue
                try:
                    chunk = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if "first_token" not in call and chunk.get("choices"):
                    call["first_token"] = round(time.time() - started, 2)
                usage = chunk.get("usage") or usage
                for ch in chunk.get("choices") or []:
                    d = ch.get("delta") or {}
                    content += d.get("content") or ""
                    for tc in d.get("tool_calls") or []:
                        c = calls.setdefault(tc.get("index", len(calls)), {"name": "", "arguments": ""})
                        f = tc.get("function") or {}
                        c["name"] += f.get("name") or ""
                        c["arguments"] += f.get("arguments") or ""
            call["answer"] = {"role": "assistant", "content": content,
                              "tool_calls": [{"function": calls[i]} for i in sorted(calls)]}
            call["usage"], call["seconds"] = usage, round(time.time() - started, 2)


def ask(upstream, messages, kind="reflect", key="", max_tokens=900, timeout=180):
    """One plain call to the real gateway (the judge uses it)."""
    body = {"model": "", "temperature": 0.0, "max_tokens": max_tokens, "messages": messages}
    req = urllib.request.Request(upstream.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 method="POST", headers={"Content-Type": "application/json", "X-Kindred-Kind": kind})
    if key:
        req.add_header("Authorization", "Bearer " + key)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    return (out.get("choices") or [{}])[0].get("message", {}).get("content") or "", out.get("usage") or {}
