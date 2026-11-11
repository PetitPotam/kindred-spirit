"""The brain's WebSocket server: the mod connects here, sends what it sees, and gets lines to say.

Messages (JSON, one per WebSocket frame):
  mod -> brain   hello, snapshot, event {join|leave|petted}, chat {text}, voice {wav: base64, peak}
  brain -> mod   welcome {name, mood}, say {line, text, mood, audio: base64 WAV or "", more, emote},
                 audio {line, audio}, heard {text}, mood {mood}, state {thinking|idle}, notice {text},
                 act {move: stay|follow|come, side: left|right|above|auto,
                      look: me|there|ahead|up|down|around, emote: spin|nod|..., seconds}

"act" moves or poses the companion right away when you ask ("stay here", "look at me",
"do a spin"); see kindred/intents.py. The AI can also add a gesture to a reply ("emote").

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
import os
import random
import re
import time

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from . import config, intents, tools, voice
from .memory import GatewayMemory, Memory
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
    def __init__(self, cfg, token, mind=None, alerts=None, clock=time.monotonic, memory=None):
        self.cfg = cfg
        self.token = token
        self.memory = memory if memory is not None else Memory(
            GatewayMemory(cfg["gateway"]["url"], cfg["gateway"].get("key", "")))
        self.mind = mind or Mind(cfg, self.memory)
        self.abilities = []
        self.singleplayer = False
        self.pending = {}
        self.next_id = 0
        self.since = None
        self.alerts = alerts or Alerts()
        self.clock = clock
        self.ws = None
        self.snapshot = {}
        self.snapshot_at = -1e9
        self.in_world = False
        self.mood = "happy"
        self.mood_until = 0.0
        self.last_talk = clock()
        self.talk_lock = asyncio.Lock()
        self.greet_task = None
        self.line = 0
        self.last_pet_reply = -1e9

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
        except ConnectionClosed:
            pass  # the game quit without saying goodbye: normal when you close Minecraft
        finally:
            if self.ws is ws:
                self.ws = None
                if self.in_world:
                    asyncio.create_task(self.end_session())
                self.in_world = False
                log.info("game disconnected")

    # ------------------------------------------------------------------ messages

    async def on_message(self, msg):
        kind = msg.get("type")
        if kind == "hello":
            log.info("mod %s on Minecraft %s", msg.get("mod"), msg.get("minecraft"))
            self.set_abilities(msg)
            await self.send({"type": "welcome", "name": self.cfg["name"], "mood": self.mood})
        elif kind == "abilities":
            self.set_abilities(msg)
        elif kind == "done":
            fut = self.pending.pop(str(msg.get("id")), None)
            if fut and not fut.done():
                fut.set_result({k: v for k, v in msg.items() if k not in ("type", "id")})
        elif kind == "snapshot":
            await self.on_snapshot(msg)
        elif kind == "event":
            await self.on_event(msg.get("event"), msg)
        elif kind == "chat":
            asyncio.create_task(self.answer(msg.get("text", "")))
        elif kind == "voice":
            asyncio.create_task(self.on_voice(msg))

    def set_abilities(self, msg):
        self.abilities = list(msg.get("abilities") or [])
        self.singleplayer = bool(msg.get("singleplayer"))
        self.mind.powers = "Power: %s, style: %s. You can: %s.%s" % (
            msg.get("power", "?"), msg.get("style", "?"), ", ".join(self.abilities) or "only talk",
            "" if self.singleplayer else " This is not a singleplayer world, so actions that change the world won't work.")
        log.info("abilities: %s", ", ".join(self.abilities))

    async def request(self, action, args, timeout=25):
        """Ask the mod to do something and wait for what happened."""
        self.next_id += 1
        rid = str(self.next_id)
        fut = asyncio.get_running_loop().create_future()
        self.pending[rid] = fut
        await self.send({"type": "do", "id": rid, "action": action, "args": args})
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self.pending.pop(rid, None)
            return {"ok": False, "error": "the game didn't answer in time"}

    async def run_tool(self, name, args):
        """What happens when the AI uses a tool: memory here, everything else in the game."""
        try:
            if name == "remember":
                new = await self.memory.remember(args.get("fact", ""), args.get("about", "player"))
                return {"ok": True, "remembered": True, "alreadyKnew": not new}
            if name == "forget":
                return {"ok": True, "forgot": await self.memory.forget(args.get("about", ""))}
            if name == "name_place":
                p = await self.memory.name_place(args.get("name", ""), self.snapshot)
                return {"ok": bool(p), "named": args.get("name", "")} if p else {"ok": False, "error": "I don't know where we are"}
            if name == "set_reminder":
                m = await self.memory.add_reminder(args.get("text", ""), args.get("when", ""))
                return {"ok": True, "reminder": args.get("text", ""), "when": args.get("when", ""),
                        "inMinutes": round((m["due"] - time.time()) / 60) if m.get("due") else None}
            if name == "cancel_reminder":
                return {"ok": True, "cancelled": await self.memory.cancel_reminder(args.get("about", ""))}
        except MemoryError as e:
            return {"ok": False, "error": str(e)}
        if name not in self.abilities:
            return {"ok": False, "error": "My settings don't let me do that (%s)." % self.mind.powers}
        if name == "guide":
            args = await self.guide_target(args)
        result = await self.request(name, args)
        if name in ("find_ore", "locate") and result.get("ok") and "x" in result and result.get("found", True):
            what = result.get("ore") or result.get("what") or args.get("ore") or args.get("what") or "something"
            if name == "find_ore":
                what += " ore"
            dim = (self.snapshot.get("where") or {}).get("dimension", "minecraft:overworld")
            await self.safe(self.memory.found(what, result["x"], result.get("y", 64), result["z"], dim))
        if result.get("ok"):
            await self.safe(self.memory.episode("I used %s %s: %s" % (name, json.dumps(args), result.get("where")
                                                                       or json.dumps(result)[:160]), 4))
        return result

    async def safe(self, coro):
        """Memory is a bonus: if the store is unreachable, carry on without it."""
        try:
            return await coro
        except MemoryError as e:
            log.warning("%s", e)
            return None

    async def guide_target(self, args):
        """Where to lead: a place it remembers by name, what it just found ("last"), or coordinates
        only if the player actually said numbers (models like to invent them)."""
        to = str(args.get("to") or "").strip().lower()
        if to and to != "last":
            places = await self.safe(self.memory.places()) or []
            for p in places:
                name = p["meta"].get("name", "").lower()
                if name and (to in name or name in to):
                    return {k: p["meta"][k] for k in ("x", "y", "z")}
            found = await self.safe(self.memory.store.call("list", kinds=["found"], world=self.memory.world_id, limit=40))
            for f in (found or {}).get("results", []):
                if to in f["meta"].get("what", "").lower():
                    return {k: f["meta"][k] for k in ("x", "y", "z")}
        said_numbers = bool(re.search(r"-?\d{2,}", getattr(self, "last_player_text", "")))
        if "x" in args and "z" in args and said_numbers:
            return {k: args[k] for k in ("x", "y", "z") if k in args}
        return {}  # the mod then uses the last thing found or located

    async def reflect(self, session_end=False):
        """Learning: the AI looks back at what happened and keeps what's worth knowing for good."""
        talk = self.memory.exchanges
        history = list(self.mind.history[-16:])
        if talk < 2 and not session_end:
            return
        if not history:
            return
        transcript = "\n".join("%s: %s" % ("Player" if m["role"] == "user" else "You", m["content"]) for m in history)
        try:
            known = await self.memory.known_for(transcript[-1500:])
            lessons = await self.mind.reflect(transcript, known, diary=session_end and talk >= 2)
            added = await self.memory.learn(lessons)
            self.memory.since_reflection = 0
            log.info("learned %d new things%s", added, "; diary: %s" % lessons.get("diary") if lessons.get("diary") else "")
        except (AIError, MemoryError) as e:
            log.warning("could not reflect: %s", e)

    async def end_session(self):
        """When you leave: what it learned, a diary entry, and the time played."""
        if self.memory.world_id is None:
            return
        await self.reflect(session_end=True)
        await self.safe(self.memory.end_session())

    async def on_event(self, name, msg=None):
        msg = msg or {}
        if name == "join":
            self.in_world = True
            self.last_talk = self.clock()
            try:
                await self.memory.open_world(msg.get("world") or "unknown")
                self.mind.history = list(await self.memory.history())
                self.since = await self.memory.start_session()
            except MemoryError as e:
                log.warning("%s (playing without memory)", e)
                self.since = None
            if self.cfg["behaviour"].get("greet_on_join") and (self.greet_task is None or self.greet_task.done()):
                self.greet_task = asyncio.create_task(self.greet())
        elif name == "leave":
            if self.in_world:
                asyncio.create_task(self.end_session())
            self.in_world = False
            self.snapshot = {}
        elif name == "arrived":
            asyncio.create_task(self.say(random.choice(intents.ARRIVED_LINES), "excited", instant=True))
            await self.safe(self.memory.episode("We arrived where I was leading the player.", 4))
        elif name == "petted":
            log.info("petted")
            await self.set_mood("happy", hold=20)
            # answer a pet now and then, not every time: it should feel like a reaction, not a script
            if self.clock() - self.last_pet_reply > 60 and not self.talk_lock.locked():
                self.last_pet_reply = self.clock()
                asyncio.create_task(self.say(random.choice(intents.PET_LINES), "happy", instant=True))

    async def reminder_loop(self, every=2.0):
        """Reminders by the clock, and by game time (when night falls, at sunrise)."""
        last_tod = None
        while True:
            await asyncio.sleep(every)
            if not self.in_world or self.ws is None or self.memory.world_id is None:
                continue
            events = [None]
            tod = (self.snapshot.get("time") or {}).get("timeOfDay")
            if tod is not None and last_tod is not None:
                if last_tod < 13000 <= tod:
                    events.append("night")
                if tod < last_tod or (last_tod < 23500 <= tod):
                    events.append("morning")
            last_tod = tod
            for ev in events:
                for r in await self.safe(self.memory.due(ev)) or []:
                    log.info("reminder: %s", r["text"])
                    await self.say("Psst, a reminder: %s" % r["text"].rstrip("."), "curious", instant=True)

    async def on_snapshot(self, s):
        self.snapshot = s
        self.snapshot_at = self.clock()
        self.save_snapshot(s)
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

    def save_snapshot(self, s, every=5.0):
        """Keeps the latest snapshot in logs/last-snapshot.json: handy for bug reports and new alerts."""
        now = self.clock()
        if now - getattr(self, "_saved_at", -1e9) < every:
            return
        self._saved_at = now
        try:
            path = os.path.join(config.HOME, "logs", "last-snapshot.json")
            with open(path + ".tmp", "w", encoding="utf-8") as fh:
                json.dump(s, fh, indent=1)
            os.replace(path + ".tmp", path)
        except OSError:
            pass

    async def set_mood(self, mood, hold=0.0):
        if hold:
            self.mood_until = self.clock() + hold
        if mood != self.mood:
            self.mood = mood
            await self.send({"type": "mood", "mood": mood})

    # ------------------------------------------------------------------ talking

    async def say(self, text, mood, instant=False, emote=None):
        """Speak a line: subtitle plus voice streamed sentence by sentence.

        instant=True shows the subtitle right away and lets the voice follow (danger warnings)."""
        self.line += 1
        line = self.line
        self.mood = mood or self.mood
        # a warning's fright passes quickly; a feeling from conversation lasts a bit longer
        self.mood_until = self.clock() + (8 if instant else 20)
        chunks = sentences(text) if self.cfg["voice"].get("enabled", True) else []
        first = ""
        if chunks and not instant:
            first = await self._voice(chunks.pop(0))
            if first is None:
                chunks = []
                first = ""
        if line != self.line:
            return  # a newer line (a warning) took over while we were synthesizing
        msg = {"type": "say", "line": line, "text": text, "mood": self.mood, "audio": first, "more": bool(chunks)}
        if emote:
            msg["emote"] = emote
        await self.send(msg)
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
        acts, done = intents.match(text)
        for act in acts:  # the body reacts at once; the words follow
            await self.send(dict(act, type="act"))
        if acts:
            log.info("acting on: %s", "; ".join(done))
        await self.send({"type": "state", "state": "thinking"})
        async with self.talk_lock:
            try:
                self.last_player_text = text
                force = intents.action_hint(text, self.abilities + ["set_reminder", "name_place", "remember"])
                reply, mood, gesture = await self.mind.reply(self.snapshot, text, done,
                                                             tools.for_abilities(self.abilities), self.run_tool, force)
            except AIError as e:
                log.error("AI error: %s", e)
                await self.send({"type": "notice", "text": "AI gateway problem: %s" % str(e)[:120]})
                await self.say("Hmm, my thoughts are fuzzy right now. Can you check my AI connection?", "sad")
                return
            log.info("you: %s | %s: [%s]%s %s", text, self.cfg["name"], mood, " {%s}" % gesture if gesture else "", reply)
            self.memory.exchanges += 1
            self.memory.since_reflection += 1
            await self.safe(self.memory.keep_history(self.mind.history))
            await self.safe(self.memory.episode("The player said: %s | I said: %s" % (text, reply), 3))
            if self.memory.since_reflection >= 8:  # learn as we go, not only at the end
                asyncio.create_task(self.reflect())
            await self.say(reply, mood or "happy", emote=gesture)
            self.last_talk = self.clock()

    async def on_voice(self, msg):
        await self.send({"type": "state", "state": "thinking"})
        try:
            wav = base64.b64decode(msg.get("wav", ""))
            text = await voice.transcribe(self.cfg, wav, prompt="%s. Minecraft." % self.cfg["name"])
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
        # Wait for a snapshot taken a moment after joining: the very first one can come before the
        # server has sent the time of day, and a greeting about "the night" at noon sets a bad tone.
        joined = self.clock()
        for _ in range(40):
            await asyncio.sleep(0.25)
            if self.snapshot_at - joined >= 2.0:
                break
        if not self.in_world or self.ws is None:
            return
        async with self.talk_lock:
            try:
                welcome = await self.safe(self.memory.welcome(self.since)) or "Greet the player warmly in one short sentence."
                due = await self.safe(self.memory.due("session")) or []
                if due:
                    welcome += " Also remind them: " + "; ".join(r["text"] for r in due) + "."
                text, mood, gesture = await self.mind.initiative(self.snapshot, welcome)
            except AIError as e:
                log.error("AI error while greeting: %s", e)
                await self.send({"type": "notice", "text": "AI gateway problem: %s" % str(e)[:120]})
                return
        self.last_talk = self.clock()
        await self.say(text, mood or "happy", emote=gesture)

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
                    text, mood, gesture = await self.mind.initiative(
                        self.snapshot, "You have been quiet for a while. Say one short, friendly thing about what "
                                       "the player is doing or where they are: a tip, a question, or something you "
                                       "would like to see together. Don't repeat yourself.")
                except AIError as e:
                    log.error("AI error during small talk: %s", e)
                    continue
            await self.say(text, mood or "happy", emote=gesture)


async def run(cfg, token):
    brain = Brain(cfg, token)
    host, port = cfg["server"].get("host", "127.0.0.1"), int(cfg["server"]["port"])
    async with serve(brain.handler, host, port, process_request=brain.check_auth, max_size=MAX_MESSAGE,
                     ping_interval=20, ping_timeout=20):
        log.info("%s's brain is listening on ws://%s:%d (gateway: %s, model %s)", cfg["name"], host, port,
                 cfg["gateway"]["url"], cfg["ai"]["model"] or "the gateway's")
        await asyncio.gather(brain.small_talk_loop(), brain.reminder_loop())
