#!/usr/bin/env python3
"""Local embeddings for the companion's memory: OpenAI-style /v1/embeddings, answered on this
machine with a small model (BAAI/bge-small-en-v1.5 via fastembed: 384 numbers per text, ~65 MB,
a few milliseconds per sentence on a laptop CPU). Free, private, offline.

    POST http://127.0.0.1:8891/v1/embeddings   {"input": ["text", ...], "model": "bge-small"}

Run with a Python that has fastembed (scripts/setup.sh makes one):
    python embed_server.py [--cache DIR]       (default ~/.kindred-spirit/embed/models)
"""
import argparse
import json
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastembed import TextEmbedding

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = int(os.environ.get("KINDRED_EMBED_PORT", "8891"))
THREADS = int(os.environ.get("KINDRED_EMBED_THREADS", "2"))
MODEL = os.environ.get("KINDRED_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
LOG_DIR = os.path.join(os.path.expanduser("~"), ".kindred-spirit", "logs")

log = logging.getLogger("kindred-embed")
_model = None
_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)

    def reply(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.reply(200, {"status": "ok", "model": MODEL})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self.reply(400, {"error": {"message": "body is not JSON"}})
            return
        texts = req.get("input")
        if isinstance(texts, str):
            texts = [texts]
        if not texts or not all(isinstance(t, str) for t in texts):
            self.reply(400, {"error": {"message": "input must be a string or a list of strings"}})
            return
        query = req.get("input_type") == "query"  # bge works a little better with a query prefix
        with _lock:
            vecs = list(_model.query_embed(texts) if query else _model.embed(texts))
        self.reply(200, {"object": "list", "model": MODEL,
                         "data": [{"object": "embedding", "index": i, "embedding": [round(float(x), 6) for x in v]}
                                  for i, v in enumerate(vecs)]})


def main():
    global _model
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.path.join(os.path.expanduser("~"), ".kindred-spirit", "embed", "models"))
    args = ap.parse_args()
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(os.path.join(LOG_DIR, "embed.log")), logging.StreamHandler(sys.stderr)])
    _model = TextEmbedding(MODEL, cache_dir=args.cache, threads=THREADS)
    list(_model.embed(["warm up"]))
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    server.daemon_threads = True
    log.info("embeddings on http://%s:%d/v1/embeddings (%s, %d threads)", LISTEN_HOST, LISTEN_PORT, MODEL, THREADS)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
