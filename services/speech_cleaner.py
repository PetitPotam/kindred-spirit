#!/usr/bin/env python3
"""Speech cleaner: sits between the Kindred brain and the real speech-to-text service.

    brain -> POST /audio/transcriptions (multipart WAV) -> this cleaner on :8090
          -> upstream: local whisper-server on :8083 (default), or any OpenAI-compatible
             transcription API (Groq, OpenAI, ...) set with KINDRED_STT_URL / KINDRED_STT_KEY
          <- {"text": "..."} as one clean line

Why it exists:
  * Whisper invents words from silence ("Thank you.", "you"), for example when the key was
    tapped by accident or the microphone permission is missing. Silent clips are answered
    with "" here and never reach the model.
  * Transcripts can hold line breaks, control characters, "[BLANK_AUDIO]" or "(music)" markers.
    They are cleaned into one line, at most 256 characters (the length of a Minecraft chat line).

Settings (environment):
  KINDRED_STT_PORT      listen port (8090)
  KINDRED_WHISPER_PORT  local whisper-server port (8083)
  KINDRED_STT_URL       full URL of a cloud transcription endpoint (unset = local whisper)
  KINDRED_STT_KEY       its API key; KINDRED_STT_MODEL its model (e.g. whisper-large-v3-turbo)

Standard library only (Python 3.8+); macOS, Windows and Linux.
"""
import array
import http.client
import io
import json
import logging
import os
import re
import sys
import urllib.parse
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = int(os.environ.get("KINDRED_STT_PORT", "8090"))
WHISPER_PORT = int(os.environ.get("KINDRED_WHISPER_PORT", "8083"))
CLOUD_URL = os.environ.get("KINDRED_STT_URL", "").strip()
CLOUD_KEY = os.environ.get("KINDRED_STT_KEY", "").strip()
CLOUD_MODEL = os.environ.get("KINDRED_STT_MODEL", "").strip()
LINE_LIMIT = 256
LOG_DIR = os.path.join(os.path.expanduser("~"), ".kindred-spirit", "logs")

log = logging.getLogger("kindred-stt")


def clean(text):
    text = text or ""
    text = re.sub(r"[\x00-\x1f\x7f   ]", " ", text)  # line breaks, tabs, control chars
    text = text.replace("§", "")                                 # Minecraft formatting code
    text = re.sub(r"\[(?:BLANK_AUDIO|MUSIC|NOISE|SILENCE)\]|\((?:music|silence|noise)\)", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return drop_repeats(text)[:LINE_LIMIT]


def drop_repeats(text):
    """Whisper sometimes says the last sentence twice ("What now? What now?"); keep one."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    out = []
    for p in parts:
        if not out or p.strip().lower() != out[-1].strip().lower():
            out.append(p)
    return " ".join(out)


SILENCE_PEAK = 1200   # int16 peak below this (~3.7% of full scale) = nobody spoke
SILENCE_RMS = 150


def is_silent(body):
    """True if the WAV inside the multipart body has no speech-level audio."""
    start = body.find(b"RIFF")
    if start == -1:
        return False
    try:
        with wave.open(io.BytesIO(body[start:])) as w:
            if w.getsampwidth() != 2:
                return False
            frames = w.readframes(w.getnframes())
    except Exception:
        return False
    samples = array.array("h")
    samples.frombytes(frames[: len(frames) - len(frames) % 2])
    if sys.byteorder == "big":
        samples.byteswap()
    if not samples:
        return True
    peak = max(abs(min(samples)), abs(max(samples)))
    step = samples[::4]
    rms = (sum(s * s for s in step) / max(1, len(step))) ** 0.5
    return peak < SILENCE_PEAK and rms < SILENCE_RMS


def with_model(body, content_type, model):
    """Adds a "model" form field to a multipart body (cloud APIs require one)."""
    m = re.search(r"boundary=([^;]+)", content_type or "")
    if not m or not model or b'name="model"' in body:
        return body
    boundary = m.group(1).strip('"').encode()
    field = b"--" + boundary + b'\r\nContent-Disposition: form-data; name="model"\r\n\r\n' + model.encode() + b"\r\n"
    return field + body


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "kindred-stt/1.0"

    def log_message(self, fmt, *args):
        log.debug("%s %s", self.address_string(), fmt % args)

    def reply(self, status, body, ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def forward(self, body):
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "content-length", "connection", "transfer-encoding", "authorization")}
        if CLOUD_URL:
            u = urllib.parse.urlsplit(CLOUD_URL)
            conn = http.client.HTTPSConnection(u.netloc, timeout=60) if u.scheme == "https" \
                else http.client.HTTPConnection(u.netloc, timeout=60)
            path = u.path
            if CLOUD_KEY:
                headers["Authorization"] = "Bearer " + CLOUD_KEY
            body = with_model(body, self.headers.get("Content-Type"), CLOUD_MODEL)
        else:
            conn = http.client.HTTPConnection("127.0.0.1", WHISPER_PORT, timeout=120)
            path = "/audio/transcriptions"
        try:
            conn.request("POST", path, body=body, headers=headers)
            resp = conn.getresponse()
            return resp.status, resp.read(), resp.getheader("Content-Type", "application/json")
        finally:
            conn.close()

    def do_GET(self):
        self.reply(200, json.dumps({"status": "ok", "upstream": CLOUD_URL or "whisper:%d" % WHISPER_PORT}).encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if is_silent(body):
            log.info("silent clip: nothing sent upstream")
            self.reply(200, b'{"text": "", "silent": true}')
            return
        try:
            status, data, ctype = self.forward(body)
        except OSError as exc:
            self.reply(502, json.dumps({"error": "speech-to-text is not reachable (%s)" % exc}).encode())
            return
        if status == 200 and "json" in (ctype or ""):
            try:
                payload = json.loads(data)
                if isinstance(payload, dict) and "text" in payload:
                    text = clean(payload["text"])
                    log.info("transcription: %r", text)
                    data = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
            except ValueError:
                pass
        elif status != 200:
            log.error("upstream returned HTTP %s: %s", status, data[:300])
        self.reply(status, data, "application/json")


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(os.path.join(LOG_DIR, "speech-cleaner.log")),
                                  logging.StreamHandler(sys.stderr)])
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    server.daemon_threads = True
    log.info("speech cleaner on http://%s:%d -> %s", LISTEN_HOST, LISTEN_PORT,
             CLOUD_URL or "whisper-server on :%d" % WHISPER_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
