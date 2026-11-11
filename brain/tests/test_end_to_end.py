"""The whole brain, over a real WebSocket, with stand-in AI / voice / speech services.

No game, no internet, no API key: this is what CI runs. It checks the same path the mod uses.
"""
import asyncio
import base64
import io
import json
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fixtures import creeper, snap
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from kindred import config
from kindred.alerts import Alerts
from kindred.server import Brain
from websockets.asyncio.server import serve

TOKEN = "test-token"


def tiny_wav(seconds=0.2, rate=16000, loud=True):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frame = (8000 if loud else 0).to_bytes(2, "little", signed=True)
        w.writeframes(frame * int(seconds * rate))
    return buf.getvalue()


class Stubs:
    """One HTTP server pretending to be the AI gateway, Kokoro and the speech cleaner."""

    def __init__(self):
        self.ai_requests = []
        stubs = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if self.path.endswith("/chat/completions"):
                    req = json.loads(body)
                    stubs.ai_requests.append(req)
                    out = json.dumps({"choices": [{"message": {"role": "assistant",
                                                               "content": "[curious] I see an oak log, three blocks ahead!"}}]})
                    self._send(200, out.encode(), "application/json")
                elif self.path.endswith("/audio/speech"):
                    self._send(200, tiny_wav(), "audio/wav")
                elif self.path.endswith("/audio/transcriptions"):
                    self._send(200, b'{"text": "what is around me?"}', "application/json")
                else:
                    self._send(404, b"{}", "application/json")

            def _send(self, code, data, ctype):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def stubs():
    s = Stubs()
    yield s
    s.close()


def make_cfg(stub_port):
    base = "http://127.0.0.1:%d" % stub_port
    return config.merge(config.DEFAULTS, {
        "ai": {"url": base + "/v1"},
        "voice": {"stt_url": base + "/audio/transcriptions", "tts_url": base + "/v1/audio/speech"},
        "behaviour": {"greet_on_join": False, "small_talk_minutes": 0},
    })


async def with_brain(cfg, scenario):
    brain = Brain(cfg, TOKEN, alerts=Alerts())
    async with serve(brain.handler, "127.0.0.1", 0, process_request=brain.check_auth, max_size=2 ** 24) as server:
        port = server.sockets[0].getsockname()[1]
        await scenario("ws://127.0.0.1:%d/" % port)


async def recv_until(ws, kind, timeout=5):
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout))
        if msg["type"] == kind:
            return msg


def test_wrong_token_is_refused(stubs):
    async def scenario(url):
        with pytest.raises(InvalidStatus):
            async with connect(url, additional_headers={"Authorization": "Bearer nope"}):
                pass
    asyncio.run(with_brain(make_cfg(stubs.port), scenario))


def test_creeper_warning_arrives_with_voice(stubs):
    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(json.dumps({"type": "hello", "mod": "test", "minecraft": "1.21.1"}))
            welcome = await recv_until(ws, "welcome")
            assert welcome["name"] == "Pip"
            await ws.send(json.dumps(snap(hostiles=[creeper(4.0, "behind")])))
            say = await recv_until(ws, "say")
            assert "creeper" in say["text"].lower() and "behind you" in say["text"]
            assert say["mood"] == "scared"
            assert say["audio"] == "" and say["more"]          # subtitle first, instantly...
            audio = await recv_until(ws, "audio")             # ...then the voice
            assert audio["line"] == say["line"]
            assert base64.b64decode(audio["audio"]).startswith(b"RIFF")
    asyncio.run(with_brain(make_cfg(stubs.port), scenario))
    assert stubs.ai_requests == []  # warnings never wait for the AI


def test_voice_question_is_heard_and_answered_with_game_state(stubs):
    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(json.dumps(snap()))
            await ws.send(json.dumps({"type": "voice", "peak": 8000,
                                      "wav": base64.b64encode(tiny_wav(1.0)).decode()}))
            assert (await recv_until(ws, "state"))["state"] == "thinking"
            heard = await recv_until(ws, "heard")
            assert heard["text"] == "what is around me?"
            say = await recv_until(ws, "say")
            assert say["text"] == "I see an oak log, three blocks ahead!" and say["mood"] == "curious"
            assert say["audio"]
    asyncio.run(with_brain(make_cfg(stubs.port), scenario))
    last = stubs.ai_requests[-1]["messages"][-1]["content"]
    assert "Looking at: oak log" in last and "biome plains" in last
    assert last.endswith("[Player]\nwhat is around me?")


def test_ai_down_gives_a_friendly_line_and_a_notice(stubs):
    cfg = make_cfg(stubs.port)
    cfg["ai"]["url"] = "http://127.0.0.1:9/v1"  # nothing listens there

    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(json.dumps({"type": "chat", "text": "hi"}))
            notice = await recv_until(ws, "notice")
            assert "AI gateway problem" in notice["text"]
            say = await recv_until(ws, "say")
            assert say["mood"] == "sad"
    asyncio.run(with_brain(cfg, scenario))
