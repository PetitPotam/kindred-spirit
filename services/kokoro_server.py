#!/usr/bin/env python3
"""Local Kokoro voice for the Kindred brain: OpenAI-style /v1/audio/speech, answered on this
machine (kokoro-onnx), so it is free, private and works offline.

    POST http://127.0.0.1:8885/v1/audio/speech
    {"input": "Hello!", "voice": "af_heart", "speed": 1.0}   ->  audio/wav

Light on purpose, because it runs next to Minecraft: one synthesis at a time and a capped number
of CPU threads (KINDRED_TTS_THREADS, chosen by scripts/start.sh from your hardware).

Run with a Python that has kokoro-onnx and soundfile (scripts/setup.sh makes one):
    python kokoro_server.py [--models DIR]
DIR holds voices-v1.0.bin and kokoro-v1.0.int8.onnx (default ~/.kindred-spirit/kokoro). The int8
model is ~2.3x faster and 3.5x smaller in memory than kokoro-v1.0.onnx, with near-identical sound;
the full model is used only if it is the one present (or KINDRED_KOKORO_MODEL names it).
"""
import argparse
import io
import json
import logging
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import onnxruntime as rt
import soundfile as sf
from kokoro_onnx import Kokoro

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = int(os.environ.get("KINDRED_KOKORO_PORT", "8885"))
THREADS = int(os.environ.get("KINDRED_TTS_THREADS", "2"))
DEFAULT_VOICE = os.environ.get("KINDRED_TTS_VOICE", "af_heart")
MAX_CHARS = 800
LOG_DIR = os.path.join(os.path.expanduser("~"), ".kindred-spirit", "logs")

log = logging.getLogger("kindred-kokoro")
_engine = None
_voices = set()
_lock = threading.Lock()  # one synthesis at a time keeps CPU use predictable while gaming


def clean_text(text):
    text = re.sub(r"\[[^\]]*\]", " ", text or "")   # [mood] tags
    text = re.sub(r"[*_`#~]+", "", text)
    return re.sub(r"\s+", " ", text).strip()[:MAX_CHARS]


def synthesize(text, voice, speed):
    lang = "en-gb" if voice.startswith("b") else "en-us"
    with _lock:
        audio, rate = _engine.create(text, voice=voice, speed=speed, lang=lang)
    buf = io.BytesIO()
    sf.write(buf, audio, rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "kindred-kokoro/1.0"

    def log_message(self, fmt, *args):
        log.debug("%s %s", self.address_string(), fmt % args)

    def reply(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def error(self, status, message):
        self.reply(status, json.dumps({"error": {"message": message}}).encode(), "application/json")

    def do_GET(self):
        path = self.path.rstrip("/")
        if path in ("", "/health", "/v1"):
            self.reply(200, b'{"status":"ok"}', "application/json")
        elif path.endswith("/voices"):
            self.reply(200, json.dumps({"voices": sorted(_voices)}).encode(), "application/json")
        else:
            self.error(404, "not found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not self.path.rstrip("/").endswith("audio/speech"):
            self.error(404, "only /v1/audio/speech is served")
            return
        try:
            req = json.loads(raw or b"{}")
        except ValueError:
            self.error(400, "body is not JSON")
            return
        text = clean_text(req.get("input"))
        if not text:
            self.error(400, "nothing to say")
            return
        voice = (req.get("voice") or DEFAULT_VOICE).strip()
        if voice not in _voices:
            voice = DEFAULT_VOICE if DEFAULT_VOICE in _voices else sorted(_voices)[0]
        try:
            speed = min(max(float(req.get("speed") or 1.0), 0.5), 2.0)
        except (TypeError, ValueError):
            speed = 1.0
        started = time.time()
        try:
            wav = synthesize(text, voice, speed)
        except Exception as exc:
            log.exception("synthesis failed")
            self.error(500, "Kokoro failed: %s" % exc)
            return
        log.info("spoke %d chars with %s in %.2fs", len(text), voice, time.time() - started)
        self.reply(200, wav, "audio/wav")


def main():
    global _engine, _voices
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=os.environ.get("KINDRED_KOKORO_DIR")
                    or os.path.join(os.path.expanduser("~"), ".kindred-spirit", "kokoro"))
    args = ap.parse_args()
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(os.path.join(LOG_DIR, "kokoro.log")),
                                  logging.StreamHandler(sys.stderr)])
    opts = rt.SessionOptions()
    opts.intra_op_num_threads = max(1, THREADS)
    opts.inter_op_num_threads = 1
    model = os.environ.get("KINDRED_KOKORO_MODEL") or next(
        (m for m in ("kokoro-v1.0.int8.onnx", "kokoro-v1.0.onnx") if os.path.exists(os.path.join(args.models, m))),
        "kokoro-v1.0.int8.onnx")
    session = rt.InferenceSession(os.path.join(args.models, model), sess_options=opts,
                                  providers=["CPUExecutionProvider"])
    _engine = Kokoro.from_session(session, os.path.join(args.models, "voices-v1.0.bin"))
    _voices = set(_engine.get_voices())
    synthesize("Hi.", DEFAULT_VOICE if DEFAULT_VOICE in _voices else sorted(_voices)[0], 1.0)  # warm up
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    server.daemon_threads = True
    log.info("kokoro on http://%s:%d/v1/audio/speech (%s, %d voices, %d threads)", LISTEN_HOST, LISTEN_PORT,
             model, len(_voices), THREADS)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
