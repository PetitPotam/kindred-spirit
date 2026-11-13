#!/usr/bin/env python3
"""A stand-in AI for install tests: answers every chat with the same friendly line, so the whole chain
(game -> brain -> gateway -> AI -> voice/subtitles) can be checked without a key or a network.

    python3 brain/tools/fake_ai.py [--port 11599]

Point the gateway at it with gateway.json: {"upstream": "fake", "upstreams": {"fake": {"base":
"http://127.0.0.1:11599/v1", "key": "", "model": "fake"}}}. OpenAI-compatible, streaming or not.
Used by scripts/test-install.sh. Standard library only.
"""
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ANSWER = "Hi! I'm Pip, and this is a test answer: everything is connected."


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"object": "list", "data": [{"id": "fake", "object": "model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        usage = {"prompt_tokens": 10, "completion_tokens": 14, "total_tokens": 24}
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self.send_error(404)
            return
        if req.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for i, word in enumerate(ANSWER.split(" ")):
                chunk = {"id": "fake", "object": "chat.completion.chunk", "created": int(time.time()), "model": "fake",
                         "choices": [{"index": 0, "delta": {"content": ("" if i == 0 else " ") + word}, "finish_reason": None}]}
                self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            end = {"id": "fake", "object": "chat.completion.chunk", "model": "fake",
                   "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": usage}
            self.wfile.write(b"data: " + json.dumps(end).encode() + b"\n\ndata: [DONE]\n\n")
            return
        body = json.dumps({"id": "fake", "object": "chat.completion", "created": int(time.time()), "model": "fake",
                           "choices": [{"index": 0, "message": {"role": "assistant", "content": ANSWER},
                                        "finish_reason": "stop"}], "usage": usage}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=11599)
    a = ap.parse_args()
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
