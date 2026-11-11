"""The brain's WebSocket server: the mod connects here, sends what it sees, and gets lines to say.

Messages (JSON, one per WebSocket frame):
  mod -> brain   hello, snapshot, event {join|leave}, chat {text}, voice {wav: base64, peak}
  brain -> mod   welcome {name, mood}, say {line, text, mood, audio: base64 WAV or "", more},
                 audio {line, audio}, heard {text}, mood {mood}, state {thinking|idle}, notice {text}

A line's voice is streamed sentence by sentence: "say" carries the whole subtitle and the first
sentence's audio, then "audio" messages carry the rest, so the companion starts talking after one
short synthesis instead of the whole reply. Danger warnings send "say" with no audio at once
(the subtitle appears instantly) and the voice follows. Each line has a number; a newer line
interrupts an older one and the mod ignores audio for lines it has moved past.

Only one game at a time, on 127.0.0.1, and only with the token from ~/.kindred-spirit/token.
"""
import asyncio
import base64
import hmac
import json
import logging
import re
import time

from websockets.asyncio.server import serve

from . import voice
from .alerts import Alerts, ambient_mood
from .mind import AIError, Mind

log = logging.getLogger("kindred.brain")
MAX_MESSAGE = 16 * 2 ** 20  # 30 s of 16 kHz audio is ~1.3 MB in base64; leave room


def sentences(text, min_chars=25):
    """Split for streaming; tiny sentences ("Oh!") are kept with the next one."""
    parts = [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]
    out = []
    for p in parts:
        if out and len(out[-1]) < min_chars:
            out[-1] += " " + p
        else:
            out.append(p)
    return out or [text]


class Brain:
    def __init__(self, cfg, token, mind=None, alerts=None, clock=time.monotonic):
        self.cfg = cfg
        self.token = token
        self.mind = mind or Mind(cfg)
        self.alerts = alerts or Alerts()
        self.clock = clock
        self.ws = None
        self.snapshot = {}
        self.in_world = False
        self.mood = "happy"
        self.mood_until = 0.0
        self.last_talk = clock()
        self.talk_lock = asyncio.Lock()
        self.greet_task = None
        self.line = 0

    # ------------------------------------------------------------------ plumbing

    def check_auth(self, connection, request):
        auth = request.headers.get("Authorization", "")
        given = auth[7:] if auth.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(given.encode(), self.token.encode()):
            log.warning("refused a connection with a wrong token")
            return connection.respond(401, "bad token\n")
        return None

    async def send(self, msg):
        ws = self.ws
        if ws is None:
            return
        try:
            await ws.send(json.dumps(msg))
        except Exception as e:  # connection closed mid-send
            log.debug("send failed: %s", e)

    async def handler(self, ws):
        if self.ws is not None:
            log.info("a new game connected; dropping the old connection")
            await self.ws.close()
        self.ws = ws
        log.info("game connected")
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                await self.on_message(msg)
        finally:
            if self.ws is ws:
                self.ws = None
                self.in_world = False
                log.info("game disconnected")

    # ------------------------------------------------------------------ messages

    async def on_message(self, msg):
        kind = msg.get("type")
        if kind == "hello":
            log.info("mod %s on Minecraft %s", msg.get("mod"), msg.get("minecraft"))
            await self.send({"type": "welcome", "name": self.cfg["name"], "mood": self.mood})
        elif kind == "snapshot":
            await self.on_snapshot(msg)
        elif kind == "event":
            await self.on_event(msg.get("event"))
        elif kind == "chat":
            asyncio.create_task(self.answer(msg.get("text", "")))
        elif kind == "voice":
            asyncio.create_task(self.on_voice(msg))

    async def on_event(self, name):
        if name == "join":
            self.in_world = True
            self.last_talk = self.clock()
            if self.cfg["behaviour"].get("greet_on_join") and (self.greet_task is None or self.greet_task.done()):
                self.greet_task = asyncio.create_task(self.greet())
        elif name == "leave":
            self.in_world = False
            self.snapshot = {}

    async def on_snapshot(self, s):
        self.snapshot = s
        if "health" in s:
            self.in_world = True
        now = self.clock()
        if self.cfg["behaviour"].get("alerts", True):
            alert = self.alerts.check(s, now)
            if alert:
                log.info("alert %s: %s", alert.kind, alert.text)
                self.mind.note_said(alert.text, alert.mood)
                asyncio.create_task(self.say(alert.text, alert.mood, instant=True))
                return
        if now >= self.mood_until:
            await self.set_mood(ambient_mood(s))

    async def set_mood(self, mood, hold=0.0):
        if hold:
            self.mood_until = self.clock() + hold
        if mood != self.mood:
            self.mood = mood
            await self.send({"type": "mood", "mood": mood})

    # ------------------------------------------------------------------ talking

    async def say(self, text, mood, instant=False):
        """Speak a line: subtitle plus voice streamed sentence by sentence.

        instant=True shows the subtitle right away and lets the voice follow (danger warnings)."""
        self.line += 1
        line = self.line
        self.mood = mood or self.mood
        self.mood_until = self.clock() + 20
        chunks = sentences(text) if self.cfg["voice"].get("enabled", True) else []
        first = ""
        if chunks and not instant:
            first = await self._voice(chunks.pop(0))
            if first is None:
                chunks = []
                first = ""
        if line != self.line:
            return  # a newer line (a warning) took over while we were synthesizing
        await self.send({"type": "say", "line": line, "text": text, "mood": self.mood, "audio": first,
                         "more": bool(chunks)})
        for chunk in chunks:
            audio = await self._voice(chunk)
            if audio is None or line != self.line:
                return
            await self.send({"type": "audio", "line": line, "audio": audio})

    async def _voice(self, text):
        try:
            return base64.b64encode(await voice.speak(self.cfg, text)).decode("ascii")
        except voice.VoiceError as e:
            log.warning("%s (subtitle only)", e)
            return None

    async def answer(self, text):
        text = (text or "").strip()
        if not text:
            return
        self.last_talk = self.clock()
        await self.send({"type": "state", "state": "thinking"})
        async with self.talk_lock:
            try:
                reply, mood = await self.mind.reply(self.snapshot, text)
            except AIError as e:
                log.error("AI error: %s", e)
                await self.send({"type": "notice", "text": "AI gateway problem: %s" % str(e)[:120]})
                await self.say("Hmm, my thoughts are fuzzy right now. Can you check my AI connection?", "sad")
                return
            log.info("you: %s | %s: [%s] %s", text, self.cfg["name"], mood, reply)
            await self.say(reply, mood or "happy")
            self.last_talk = self.clock()

    async def on_voice(self, msg):
        await self.send({"type": "state", "state": "thinking"})
        try:
            wav = base64.b64decode(msg.get("wav", ""))
            text = await voice.transcribe(self.cfg, wav)
        except (ValueError, voice.VoiceError) as e:
            log.error("speech-to-text failed: %s", e)
            await self.send({"type": "notice", "text": "Speech-to-text problem: %s" % str(e)[:120]})
            await self.send({"type": "state", "state": "idle"})
            return
        if not text:
            hint = ("Your microphone sent silence. On macOS, start the Minecraft Launcher from Terminal "
                    "so it can use the mic." if msg.get("peak", 1000) < 300 else "I didn't catch that. Try again?")
            await self.send({"type": "notice", "text": hint})
            await self.send({"type": "state", "state": "idle"})
            return
        await self.send({"type": "heard", "text": text})
        await self.answer(text)

    async def greet(self):
        await asyncio.sleep(2.5)  # wait for the first snapshot
        if not self.in_world or self.ws is None:
            return
        async with self.talk_lock:
            try:
                text, mood = await self.mind.initiative(
                    self.snapshot, "The player just joined the world. Greet them warmly in one short sentence, "
                                   "maybe noticing one thing about where they are.")
            except AIError as e:
                log.error("AI error while greeting: %s", e)
                await self.send({"type": "notice", "text": "AI gateway problem: %s" % str(e)[:120]})
                return
        self.last_talk = self.clock()
        await self.say(text, mood or "happy")

    async def small_talk_loop(self, every=20.0):
        while True:
            await asyncio.sleep(every)
            minutes = self.cfg["behaviour"].get("small_talk_minutes", 0)
            if not minutes or not self.in_world or self.ws is None or self.talk_lock.locked():
                continue
            if self.clock() - self.last_talk < minutes * 60:
                continue
            if any(m.get("distance", 99) <= 16 for m in self.snapshot.get("hostiles") or []):
                continue  # busy fighting: not the moment
            self.last_talk = self.clock()
            async with self.talk_lock:
                try:
                    text, mood = await self.mind.initiative(
                        self.snapshot, "You have been quiet for a while. Say one short, friendly thing about what "
                                       "the player is doing or where they are: a tip, a question, or something you "
                                       "would like to see together. Don't repeat yourself.")
                except AIError as e:
                    log.error("AI error during small talk: %s", e)
                    continue
            await self.say(text, mood or "happy")


async def run(cfg, token):
    brain = Brain(cfg, token)
    host, port = cfg["server"].get("host", "127.0.0.1"), int(cfg["server"]["port"])
    async with serve(brain.handler, host, port, process_request=brain.check_auth, max_size=MAX_MESSAGE,
                     ping_interval=20, ping_timeout=20):
        log.info("%s's brain is listening on ws://%s:%d (AI: %s, model %s)", cfg["name"], host, port,
                 cfg["ai"]["url"], cfg["ai"]["model"])
        await brain.small_talk_loop()
