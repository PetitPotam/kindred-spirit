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
import urllib.request

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from . import config, intents, tools, voice
from . import mind as mind_mod
from . import heart as intents_heart
from .describe import describe, where_words
from . import knowledge as kb
from .understand import Understand
from . import becoming as becoming_mod
from . import instinct as instinct_mod
from . import talker
from . import tunes
from .senses import Novelty
from .sessionlog import SessionLog
from .mind import post_json
from .heart import Heart
from .memory import GatewayMemory, Memory
from .alerts import Alerts
from .mind import AIError, Mind

log = logging.getLogger("kindred.brain")
MAX_MESSAGE = 16 * 2 ** 20  # 30 s of 16 kHz audio is ~1.3 MB in base64; leave room


def sentences(text, min_chars=25, first_max=0):
    """Split for streaming; tiny sentences ("Oh!") are kept with the next one. first_max: a long first
    sentence is split at a comma, so her voice starts sooner (the first piece is made while you read)."""
    parts = [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]
    out = []
    for p in parts:
        if out and len(out[-1]) < min_chars:
            out[-1] += " " + p
        else:
            out.append(p)
    out = out or [text]
    if first_max and len(out[0]) > first_max:
        m = re.search(r",\s+", out[0][20:])
        if m:
            cut = 20 + m.end()
            out[0:1] = [out[0][:cut].rstrip(), out[0][cut:]]
    return out


HANDS = ("protect", "place_torch", "harvest", "build", "give_item", "give_effect", "set_time", "set_weather", "job",
         "blueprint")  # powers that touch the world


def player_name(memories):
    """The player's name from what she remembers ("The player's name is Alex"), never the name they gave her."""
    m = re.search(r"(?:player's name is|player is called|player's called|name of the player is) ([A-Z][\w-]+)",
                  memories or "")
    return m.group(1) if m else ""


class SpokenStream:
    """One answer, spoken as it streams in: the first sentence starts her line (through the coordinator,
    as a reply), the next ones join it. The voice for each is made in order while the AI keeps writing."""

    def __init__(self, brain):
        self.brain, self.q, self.line, self.said = brain, asyncio.Queue(), None, []
        self.started, self.first_at = brain.clock(), None
        self.task = asyncio.create_task(self.run())

    def add(self, text, mood, gesture, whisper):
        if self.first_at is None:
            self.first_at = self.brain.clock()
        self.said.append(text)
        self.q.put_nowait((text, mood, gesture, whisper))

    async def close(self):
        self.q.put_nowait(None)
        await self.task

    async def run(self):
        while True:
            item = await self.q.get()
            if item is None:
                return
            text, mood, gesture, whisper = item
            style = "whisper" if whisper else None
            try:
                if self.line is None:
                    self.line = await self.brain.say(text, mood or "happy", emote=gesture, style=style, prio="reply")
                elif self.line:
                    await self.brain.say_more(self.line, text, style)
            except Exception as e:  # (one sentence failing must not silence the rest)
                log.warning("couldn't say %r: %s", text[:60], e)


def did_something(name, result):
    """Whether a power really showed itself: stopping isn't a power, pushing nothing away or finding
    nothing doesn't reveal anything."""
    if name == "stop_guide":
        return False
    if name == "protect":
        return bool(result.get("pushedAway"))
    if name == "harvest":
        return bool(result.get("broken"))
    if name in ("build", "blueprint"):
        return bool(result.get("blocks")) and not result.get("stopped")
    if name == "job":
        return bool(result.get("total") or result.get("done"))
    if name in ("find_ore", "find_animal", "locate"):
        return result.get("found", True) is not False
    return True


def merge_messages(texts):
    """Several messages at once, as one: repeats counted ("i love you (said 9 times in a row)")."""
    out = []
    for t in texts:
        key = re.sub(r"[^a-z ]", "", t.lower()).strip()
        if out and out[-1][0] == key:
            out[-1][2] += 1
        else:
            out.append([key, t, 1])
    lines = ["%s (said %d times in a row)" % (t, n) if n > 1 else t for _, t, n in out]
    if len(lines) == 1:
        return lines[0]
    return "(several messages, sent one after another)\n" + "\n".join(lines)


PRIORITY = {"aside": 0, "reaction": 1, "reply": 2, "urgent": 3}


def without_her_words(text, her_lines):
    """What the microphone heard, minus the sentences she said herself lately (her voice from your
    speakers reaching your microphone)."""
    import difflib

    def norm(s):
        return re.sub(r"[^a-z ]", "", s.lower()).strip()
    hers = [norm(s) for line in her_lines for s in re.split(r"(?<=[.!?])\s+", line) if len(norm(s)) > 10]
    keep = []
    for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()):
        n = norm(s)
        if len(n) > 10 and any(difflib.SequenceMatcher(None, n, h).ratio() > 0.75 or (len(n) > 25 and n in h)
                               for h in hers):
            continue
        keep.append(s)
    return " ".join(keep).strip()


def estimate_seconds(text):
    """How long a line takes to say, roughly (her voice: about 15 characters a second)."""
    return 0.4 + len(text or "") / 15.0


IMPORTED_KINDS = ("player", "self", "habit", "origin", "taste", "core")  # what an import brings: who you are, who she is, your habits

# moments worth waiting for a pause in the conversation, rather than skipping
DANGER_SOUND = re.compile(r"creeper|zombie|skeleton|spider|witch|phantom|drowned|husk|stray|pillager|vindicator|"
                          r"ravager|blaze|ghast|hoglin|piglin|warden|enderman|slime|silverfish|guardian|evoker", re.I)

# sounds worth turning her head for (by the names the world gives them): creatures, caves, water, fire...
INTERESTING = re.compile(r"groan|hiss|growl|rattl|ambien|cave|roar|scream|shriek|crackl|pops|bubbl|howl|creak|chime|"
                         r"music|sing|moo|bleat|baa|oink|cluck|neigh|purr|meow|bark|buzz|drip|flow|thunder|bell|"
                         r"whisper|moan|sniff|squeak|croak|warden|ghast|wail", re.I)

WORTH_WAITING = ("baby", "tamed", "first_meet", "killed_villager", "kill_spree", "death", "advancement", "lore_place")


BLUEPRINT_DIRS = [os.path.expanduser(p) for p in os.environ.get("KINDRED_BLUEPRINTS", "").split(os.pathsep) if p] or [
    os.path.expanduser("~/Library/Application Support/minecraft-kindred/config/kindredspirit/blueprints"),
    os.path.expanduser("~/Library/Application Support/minecraft-kindred/schematics")]


ENCH_OLD = re.compile(r"\{\s*id\s*:\s*\"?(?:minecraft:)?([a-z_]+)\"?\s*,\s*lvl\s*:\s*(\d+)\w?\s*\}")


def modern_give(name, args, can_command):
    """An item written the old way ("netherite_sword{Enchantments:[{id:sharpness,lvl:5}]}", in give_item or /give)
    becomes Minecraft 1.21's /give with components (netherite_sword[enchantments={levels:{sharpness:5}}]);
    every enchanted gift failed that way in the 2026-11-13 session."""
    if name == "give_item":
        item = str(args.get("item", ""))
        if "{" not in item and "[" not in item:
            return name, args
        if not can_command:
            return name, dict(args, item=re.split(r"[{\[]", item, 1)[0])
        who = args.get("to") or "@s"
        cmd = "/give %s %s %d" % (who, item, int(args.get("count") or 1))
        return modern_give("command", {"command": cmd}, can_command)
    cmd = str(args.get("command", ""))
    m = re.match(r"(/?give\s+\S+\s+)([a-z_:]+)\{(.*)\}(\s+\d+)?\s*$", cmd)
    if not m or "nchantments" not in m.group(3):
        return name, args
    levels = ",".join("%s:%s" % (e, l) for e, l in ENCH_OLD.findall(m.group(3)))
    new = "%s%s[enchantments={levels:{%s}}]%s" % (m.group(1), m.group(2), levels, m.group(4) or "")
    return name, dict(args, command=new.strip())


def find_blueprints(query, dirs=None, limit=15):
    """The blueprint files she can build (the mod reads the same folders), matching the words asked."""
    names = []
    for d in dirs or BLUEPRINT_DIRS:
        try:
            names += [f.rsplit(".", 1)[0] for f in sorted(os.listdir(d))
                      if f.lower().endswith((".nbt", ".schem", ".litematic"))]
        except OSError:
            pass
    if not names:
        return {"ok": False, "error": "There are no blueprint files yet (only the cottage you can make up)."}
    words = [w for w in re.findall(r"[a-z0-9]+", (query or "").lower()) if len(w) > 1 and w not in ("a", "the", "of")]
    words = [w[:-1] if w.endswith("s") and len(w) > 3 else w for w in words]  # (ships -> ship)
    hits = [n for n in names if all(w in n.lower() for w in words)] if words else []
    if words and not hits:  # any of the words, best first
        scored = sorted(((sum(w in n.lower() for w in words), n) for n in names), reverse=True)
        hits = [n for s, n in scored if s][:limit]
    kinds = sorted({"_".join(n.split("_")[:2]) if n.startswith("village_") else n.split("_")[0] for n in names})
    out = {"ok": True, "total": len(names), "kinds": kinds}
    if words:
        out["matches"] = hits[:limit]
        out["more"] = max(0, len(hits) - limit)
    return out


class Brain:
    def __init__(self, cfg, token, mind=None, alerts=None, clock=time.monotonic, memory=None):
        self.cfg = cfg
        self.token = token
        self.memory = memory if memory is not None else Memory(
            GatewayMemory(cfg["gateway"]["url"], cfg["gateway"].get("key", "")))
        self.mind = mind or Mind(cfg, self.memory)
        self.abilities = []
        self.power_news = ""
        self.singleplayer = False
        self.pending = {}
        self.next_id = 0
        self.since = None
        self.memory.per_world = not cfg["heart"].get("same_companion_in_every_world", False)
        if hasattr(self.memory.store, "strict"):
            self.memory.store.strict = self.memory.per_world
        self.heart = Heart(cfg, self.memory)
        self.heart_loaded = False   # which heart is loaded (its key), or False
        self.last_notice = -1e9
        self.noticed = {}
        self.prev_biome = None
        self.prev_health = None
        self.last_protect = self.last_guard = -1e9
        self.speaking_to = None      # a friend she's answering (session log: who each line was for)
        self.diary_at, self.diary_from = clock(), 0  # her last diary entry: when, and up to which session event
        self.last_where_log, self.near_logged, self.settings_logged = -1e9, set(), None
        self.voice_timing = None     # (released at, arrived, stt seconds): the last spoken message, for its timing
        self.last_wait = 0.0         # how long her last answer waited for the line she was saying
        self.guest_pending = {}      # friend -> what they said while she was busy (answered together)
        self.spot_said, self.friends_seen, self.prev_dim, self.prev_spot_pos = {}, {}, None, None
        self.friend_warned = -1e9
        self.recent_gifts = {}       # (tool, what, to) -> when: never the same gift again unasked
        self.notified = []
        self.idle_since = clock()
        self.last_pos = None
        self.animals_seen = {}       # entity id -> was a baby, this session
        self.animals_since = None    # when we started watching (babies only count after that)
        self.kills = []              # (time, type) of animals the player killed
        self.last_pet_visit = clock()
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
        self.tipped = {}             # power -> when the player last got a settings tip for it
        self.kb = kb.Knowledge(cfg)
        self.understand = Understand(cfg)  # System 0's understanding (local embeddings)
        self.instinct = instinct_mod.Instinct()  # System 0's own words, written by System 2 (per world)
        self.lines_written_at, self.last_filler, self.becoming_at = -1e9, -1e9, -1e9
        self.novelty = Novelty()  # what's new to her and what she's used to (senses.py)
        self.session = SessionLog()  # a record of each play session, read afterwards (sessionlog.py)  # what the world remembers (services/knowledge)
        self.session.context = self.log_context
        self.listening = set()       # questions she's listening to the world about right now
        self.reading = None          # the guide she was last told about (listen_more goes on from there)
        # one voice, coordinated (see say): what she's saying now, and what an interruption left unsaid
        self.speaking_until, self.speaking_prio, self.speaking_chunks, self.speaking_started = 0.0, "aside", [], 0.0
        self.unfinished, self.resume_task = None, None
        self.seconds_to_say = estimate_seconds  # (tests make it instant)
        self.player_talked, self.player_listening, self.listening_since = -1e9, False, 0.0
        self.transcribing = False
        self.recent_said = []        # (when, text) she said lately (to recognise her own voice in your microphone)
        self.last_kill = None        # (when, what) the player last killed (for "how did you take it down?")
        self.recent = []             # (when, what) just happened: deaths, respawns, big hits (see happened)
        self.prev_where = None
        self.inbox, self.inbox_task = [], None  # what the player said while she was busy (hear_player)
        self.her_offer = None        # (action, when): what she offered in her own words just now
        self.offered = None          # powers offered to the AI right now (None: all allowed ones)
        self.recent_player = []      # the last few things the player said ("find them" -> them = sheep)
        self.awakening = {}          # power -> what System 2 is doing about it (see awaken)
        self.quiet_gap = 4.0         # seconds of quiet before she brings something up herself

    # ------------------------------------------------------------------ plumbing

    def check_auth(self, connection, request):
        auth = request.headers.get("Authorization", "")
        given = auth[7:] if auth.lower().startswith("bearer ") else ""
        if not given and "token=" in (request.path or ""):  # the dashboard's simulator (a browser can't set headers)
            from urllib.parse import parse_qs, urlparse
            given = (parse_qs(urlparse(request.path).query).get("token") or [""])[0]
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
                self.session.event("disconnect")
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
        elif kind == "chat" and msg.get("from"):  # a friend on your LAN world called her in chat
            asyncio.create_task(self.answer_guest(msg["from"], msg.get("text", ""), bool(msg.get("powers"))))
        elif kind == "chat":
            self.hear_player(msg.get("text", ""))
        elif kind == "voice":
            asyncio.create_task(self.on_voice(msg))
        elif kind == "admin":  # /kindred memory, /kindred reset, /kindred persona ... (answered in chat)
            asyncio.create_task(self.admin(msg.get("command", ""), msg.get("text", "")))

    def set_abilities(self, msg):
        before, self.abilities = self.abilities, list(msg.get("abilities") or [])
        gained = [a for a in self.abilities if a not in before and a in HANDS] if before else []
        if gained:  # (the player changed her power or style while playing: she stops saying she can't)
            self.power_news = ("Something in you just changed: now you can %s. If you told the player earlier that "
                               "you couldn't, that was true then, not now." % ", ".join(a.replace("_", " ") for a in gained))
        self.singleplayer = bool(msg.get("singleplayer"))
        # (said in her world's words: these are limits of what she is, never "settings" to talk about)
        known = ", ".join(a.replace("_", " ") for a in self.abilities) if not self.heart.amnesia() else \
            "you don't know yet: you find out by trying when the player asks"
        self.mind.powers = "%s%s What you can do: %s.%s" % (
            {"advisor": "You can only look, sense and lead the way; you can't touch or change anything.",
             "helper": "You can help with your hands when asked, but nothing too big.",
             "allpowerful": "Your power is great: even the sun and the sky listen to you."}.get(msg.get("power"), ""),
            "" if msg.get("power") == "advisor" else
            " You can only use what really exists (the player's own torches): you can't make things appear out of "
            "nothing." if msg.get("style") == "grounded" else " Your magic can make things appear.",
            known, "" if self.singleplayer else " Here your magic can't change the world itself.")
        cant = [a.replace("_", " ") for a in HANDS if a not in self.abilities]
        if cant:  # (when she's set to only look and lead, or magic is off: say so, don't make up a reason)
            self.mind.powers += (" Right now these are beyond you: %s. If the player asks for one, say simply and "
                                 "honestly that it's beyond you right now%s; never invent another reason (not torches, "
                                 "not being tired)." % (", ".join(cant), " (right now you can only look, sense and "
                                                         "lead the way)" if msg.get("power") == "advisor" else ""))
        if msg.get("glow") and self.singleplayer:
            self.mind.powers += " You glow softly: in the dark your light shows the way around you."
        # one tool list for every call (her powers in the mod's order, then memory): the start of each request
        # stays the same, so the provider's cache serves it (mind._ask says which fit each answer)
        self.mind.all_tools = tools.for_abilities(self.abilities)
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

    async def run_tool(self, name, args, who=None):
        """What happens when the AI uses a tool (and the session log notes it, with who asked)."""
        result = await self._run_tool(name, args)
        ok = not (isinstance(result, dict) and result.get("ok") is False)
        self.session.event("tool", name=name, args=json.dumps(args)[:600], ok=ok, who=who or self.speaking_to or "player",
                           result=json.dumps(result)[:1000] if isinstance(result, dict) else str(result)[:1000])
        return result

    async def _run_tool(self, name, args):
        """What happens when the AI uses a tool: memory here, everything else in the game."""
        try:
            if name == "remember":
                self.learn_nickname(args.get("fact", ""))
                new = await self.memory.remember(args.get("fact", ""), args.get("about", "player"))
                return {"ok": True, "remembered": True, "alreadyKnew": not new}
            if name == "forget":
                return {"ok": True, "forgot": await self.memory.forget(args.get("about", ""))}
            if name == "name_place":
                p = await self.memory.name_place(args.get("name", ""), self.snapshot, bool(args.get("replace")))
                if p and p.get("exists"):  # never silently move a place they named before
                    e = p["exists"]
                    return {"ok": False, "alreadyNamed": e["name"], "itIs": self.place_words(e),
                            "error": "There's already a place called '%s' (%s). Ask whether to move it here "
                                     "(name_place with replace) or give this spot another name." % (e["name"], self.place_words(e))}
                return {"ok": bool(p), "named": args.get("name", "")} if p else {"ok": False, "error": "I don't know where we are"}
            if name == "rename_place":
                p = await self.memory.rename_place(args.get("old", ""), args.get("new", ""))
                return {"ok": True, "renamed": args.get("old"), "to": args.get("new")} if p else \
                    {"ok": False, "error": "No place called '%s'." % args.get("old", "")}
            if name == "set_reminder":
                m = await self.memory.add_reminder(args.get("text", ""), args.get("when", ""))
                return {"ok": True, "reminder": args.get("text", ""), "when": args.get("when", ""),
                        "inMinutes": round((m["due"] - time.time()) / 60) if m.get("due") else None}
            if name == "cancel_reminder":
                return {"ok": True, "cancelled": await self.memory.cancel_reminder(args.get("about", ""))}
            if name == "find_blueprint":
                return find_blueprints(args.get("query", ""))
            if name == "listen_more":
                return await self.listen_more(args.get("what", "next"))
            if name == "standing_request":
                what = args.get("what", "")
                if not args.get("stop") and not intents.STANDING.search(getattr(self, "last_player_text", "")):
                    # models reach for this on any "find"; it's only for "always..." / "tell me whenever..."
                    return {"ok": False, "error": "They didn't ask you to do it every time; just help with this once."}
                if args.get("stop"):
                    n = self.heart.drop_request(what)
                    await self.heart.save()
                    return {"ok": True, "stopped": n}
                if what == "protect" and "protect" not in self.abilities:
                    return {"ok": False, "error": "You can't protect them with your current power."}
                who = str(args.get("for") or "").strip()
                if what == "protect" and who.lower() in ("me", "player", "us", "both", "everyone", "all"):
                    who = "" if who.lower() in ("me", "player") else "everyone"
                self.heart.add_request(what, args.get("detail", "") if what != "protect" else who)
                await self.heart.save()
                return {"ok": True, "willDoItEveryTime": what, **({"for": who} if who else {})}
        except MemoryError as e:
            return {"ok": False, "error": str(e)}
        if name not in self.abilities:
            await self.tip_for(name)
            return {"ok": False, "error": "That's beyond what you can do."}
        if self.offered is not None and name not in self.offered:
            # (amnesia) a power she hasn't discovered: the AI knows the name, she doesn't
            return {"ok": False, "error": "You don't know how to do that yet."}
        args = self.real_names(args)  # nicknames she was taught ("follow Dumb") -> the player's name
        if name in ("give_item", "command"):  # old item syntax ({Enchantments:[...]}) -> Minecraft 1.21's components
            name, args = modern_give(name, args, "command" in self.abilities)
        said_now = (getattr(self, "asking_text", "") or getattr(self, "last_player_text", "") or "").lower()
        if name == "give_effect" and str(args.get("effect", "")).lower() in ("health", "food", "regeneration", "heal",
                                                                             "saturation") \
                and not intents.WANTS_CARE.search(said_now):
            return {"ok": False, "error": "Nobody asked for healing or food just now: don't give it (you may offer it in words)."}
        if name == "protect" and not args.get("poke") and not (self.snapshot or {}).get("hostiles") \
                and not intents.action_hint(said_now, ["protect"]):
            return {"ok": False, "error": "There are no monsters near, and nobody asked: nothing to push away."}
        if name in ("give_item", "give_effect"):
            # the same gift again, unasked (asked for "fancy emotes", she gave enchanted apples again and again):
            # only when their words ask for it (the item, "again", "another", "more")
            what = str(args.get("item") or args.get("effect") or "").lower().replace("minecraft:", "")
            key = (name, what, str(args.get("to") or "").lower())
            said = (getattr(self, "asking_text", "") or getattr(self, "last_player_text", "") or "").lower()
            asked_again = re.search(r"\b(again|another|more|also|too|one more|extra|stack|stacks|lots?|bunch|"
                                    r"plenty|full|need|all of)\b", said) or any(
                w and w in said for w in re.split(r"[_ ]", what) if len(w) > 2)
            if self.clock() - self.recent_gifts.get(key, -1e9) < 180 and not asked_again:
                return {"ok": False, "error": "You already gave that a moment ago, and they didn't ask for it again: "
                                              "don't give it again."}
            self.recent_gifts[key] = self.clock()
        if name == "command":
            # a harmful effect only when the one asking named it themselves ("give him poison")
            said = (getattr(self, "asking_text", "") or getattr(self, "last_player_text", "") or "").lower()
            m = re.search(r"effect give \S+ (?:minecraft:)?(\w+)", str(args.get("command", "")))
            args = dict(args, harmfulAsked=bool(m and m.group(1).replace("_", " ") in said))
            if self.speaking_to and self.speaking_to != "player":  # a friend's turn: not on someone who didn't ask
                host = (self.snapshot or {}).get("playerName", "")
                if host and host.lower() in str(args.get("command", "")).lower() and not re.search(
                        r"effect give \S+ (slowness|levitation|glowing)|particle|playsound", str(args.get("command", ""))):
                    return {"ok": False, "error": "Not on %s: they didn't ask." % host}
        if name == "build" and not str(args.get("block") or "").strip() and args.get("shape") not in ("clear", "stop", "portal"):
            named = intents.block_named(self.recent_player + [getattr(self, "last_player_text", "")])
            if named:  # ("flatten it with dirt", then "do it": still dirt, not whatever is in their hand)
                args = dict(args, block=named)
        if name == "job" and str(args.get("kind", "")) == "return_items" and "x" not in args:
            death = await self.death_spot()
            if death:  # where she remembers they died (the mod also remembers the last death it saw)
                args = dict(args, **death)
        if name == "guide" and not intents.ASKS_TO_GO.search(
                (getattr(self, "asking_text", "") or getattr(self, "last_player_text", "") or "").lower()):
            # (on 'Hey, Pep' and 'I'm hurt' she set off for a base from the last session: lead only when asked)
            return {"ok": False, "error": "Nobody asked to be led anywhere just now: don't lead (you may offer it in words)."}
        if name == "guide":
            args = await self.guide_target(args)
            if args.get("refuse"):
                return {"ok": False, "error": args["refuse"]}
        result = await self.request(name, args)
        m = re.search(r"\(?(?:The player can switch with )?(/kindred [a-z ]+?)\.?\)", result.get("error") or "")
        if m:  # the way to unlock it is for the player, as a hint in chat: never in her mouth
            await self.send({"type": "notice", "text": "Tip: %s lets %s do this" % (m.group(1), self.cfg["name"])})
            result["error"] = result["error"].replace(m.group(0), "").strip()
        if name in ("find_ore", "locate", "find_block") and result.get("ok") and "x" in result and result.get("found", True):
            self.last_found = {k: result[k] for k in ("x", "y", "z") if k in result}  # (where "lead the way" goes)
        if name in ("find_animal", "find_player") and result.get("ok"):
            self.last_found = None  # (someone walking: the game follows them itself)
        if name in ("find_ore", "locate") and result.get("ok") and "x" in result and result.get("found", True):
            what = result.get("ore") or result.get("what") or args.get("ore") or args.get("what") or "something"
            if name == "find_ore":
                what += " ore"
            dim = (self.snapshot.get("where") or {}).get("dimension", "minecraft:overworld")
            await self.safe(self.memory.found(what, result["x"], result.get("y", 64), result["z"], dim))
        if result.get("ok"):
            await self.safe(self.memory.episode("I used %s %s: %s" % (name, json.dumps(args), result.get("where")
                                                                       or json.dumps(result)[:160]), 4))
            if did_something(name, result) and self.heart.discovered(name) and self.heart.amnesia():
                result["firstTime"] = True
                await self.safe(self.memory.remember("I discovered I can %s." % name.replace("_", " "), "self", 8))
            await self.heart.save()
        return result

    # ------------------------------------------------------------------ her heart

    async def tip_for(self, ability):
        """A settings hint for the player (in chat, not from her) when she's asked for something her
        power or style doesn't allow."""
        need = {"give_item": "/kindred style magic", "give_effect": "/kindred style magic", "set_time": "/kindred power allpowerful",
                "set_weather": "/kindred power allpowerful", "protect": "/kindred power helper",
                "place_torch": "/kindred power helper"}.get(ability)
        if need:
            await self.send({"type": "notice", "text": "Tip: %s lets %s do this" % (need, self.cfg["name"])})

    async def bond_update(self, delta, why="", who=None):
        if abs(delta) < 0.5:
            return
        log.info("bond %+.1f (%s) -> %.0f %s | %s", delta, why, self.heart.bond, self.heart.level(),
                 getattr(self.heart.rel, "last_line", ""))
        self.session.event("heart", change=round(delta, 1), why=why, who=who or "player", bond=round(self.heart.bond),
                           stance=self.heart.stance(), detail=getattr(self.heart.rel, "last_line", "")[:160])
        level = self.heart.level()
        feel = "%s, %s" % (level, self.heart.stance())
        if self.instinct.level and feel != self.instinct.level and self.clock() - self.lines_written_at > 600:
            asyncio.create_task(self.write_lines())  # she feels differently about you: her instincts too
        if level in ("close", "best friend") and level not in self.heart.state.setdefault("levels_reached", []):
            self.heart.state["levels_reached"].append(level)  # a milestone: it may reveal a piece of her story
            moment = self.heart.origin_moment("you and the player just became %s" % (
                "close" if level == "close" else "best friends"), self.clock())
            if moment:
                asyncio.create_task(self.speak_up("You feel how much closer you've grown to the player." + moment,
                                                  "happy"))
        await self.send({"type": "bond", "value": round(self.heart.bond), "level": self.heart.level(),
                         "change": round(delta, 1), "trust": round(self.heart.rel.s["t"]),
                         "stance": self.heart.stance()})
        await self.send({"type": "act", "closeness": self.heart.closeness()})
        await self.heart.save()

    async def perform(self):
        """A little show when asked for one: four or five of her gestures, one after the other."""
        moves = ["spin", "hop", "wiggle", "tease", "nod", "happy"]
        random.shuffle(moves)
        for m in moves[:random.randint(4, 5)]:
            await self.send({"type": "act", "emote": m})
            await asyncio.sleep(1.5)

    async def after_gesture(self):
        await self.bond_update(0.6, "made up for it")
        await self.speak_up("The player just did the small thing you asked of them to make up for hurting you. "
                            "It means something to you; react as yourself, in one short line.", "happy", prio="reaction")

    async def heart_news(self):
        """After her heart moved: a scar becomes a painful core memory, a healed one is marked, a serious
        hurt may get a small ask to make up, and she's told once that she asked."""
        rel, now = self.heart.rel, self.clock()
        for inc in rel.new_scars:
            what = ("\"%s\"" % inc["words"]) if inc.get("words") else {"hit_deliberate": "hitting me on purpose"}.get(
                inc["kind"], "how they treated me")
            await self.safe(self.memory.add("core", "The player hurt me again and again (%s). It left a mark." % what,
                                            10, meta={"feeling": "hurt", "pain": True, "scar": inc["id"]}))
            log.info("a scar: incident %s", inc["id"])
        rel.new_scars = []
        for inc in rel.healed_scars:
            rows = (await self.safe(self.memory.store.call("list", kinds=["core"], world=self.memory.world_id,
                                                           limit=50)) or {}).get("results") or []
            for r in rows:
                if (r.get("meta") or {}).get("scar") == inc["id"]:
                    await self.safe(self.memory.store.call("update", id=r["id"], meta=dict(r["meta"], healed=True)))
            log.info("a scar healed: incident %s", inc["id"])
        rel.healed_scars = []
        rel.ask_gesture(self.heart.rng, now)
        await self.heart.save()

    async def vanish(self, seconds, line):
        self.session.event("vanish", seconds=seconds)
        log.info("vanishing for %d s", seconds)
        await self.say(line, "sad", instant=True, why="the player hurt you and you're leaving for a while")
        await self.mood_weather(sad=True)
        await asyncio.sleep(2.5)
        await self.send({"type": "act", "move": "hide", "seconds": seconds})

        async def back():
            await asyncio.sleep(seconds + 1)
            if self.ws is not None and self.in_world:
                await self.say(random.choice(intents_heart.BACK_LINES), "calm", instant=True,
                               why="you came back after leaving for a while because they hurt you")
        asyncio.create_task(back())

    async def mood_weather(self, sad):
        """Her tears bring rain; when she's comforted, the sun comes back (singleplayer, a setting)."""
        if not self.singleplayer:
            return
        w = self.heart.weather(sad)
        if not w:
            return
        res = await self.request("mood_weather", {"weather": w})
        log.info("mood weather %s: %s", w, res)
        if res.get("ok") and w == "clear":
            await asyncio.sleep(2)
            await self.say(random.choice(intents_heart.CLEAR_LINES), "happy", instant=True,
                           why="you feel better, so the rain from your tears stopped")
        await self.heart.save()

    async def notice(self, event, detail=""):
        """Something happened that she might want to talk about.

        Small things (a new item, a biome) are skipped when she spoke recently; moments that matter
        (a baby, a new pet, a first meeting, a death) wait their turn for up to a minute instead."""
        if event == "first_meet" and detail:  # a first, remembered where it was (even if she says nothing now)
            sp = detail.replace("minecraft:", "").replace("_", " ")
            self.remember_spot("first:" + sp, "where we met our first %s" % sp, None)
        if not self.attending_player():  # beside a friend far away: what happens around the player isn't hers now
            self.session.event("not_said", text="(noticed %s %s)" % (event, detail), reason="she's with a friend far away")
            return
        waits = 30 if event in WORTH_WAITING else 0
        gap = 45 if event in WORTH_WAITING else 150  # (her own comments leave room: she isn't a radio)

        def busy():  # she owes you an answer, or you're talking: her own comments wait (or are dropped)
            return (self.talk_lock.locked() or bool(self.inbox) or (self.inbox_task is not None
                    and not self.inbox_task.done()) or self.clock() - self.player_talked < 15)
        while (busy() or self.clock() - self.last_notice < gap) and waits > 0:
            waits -= 1
            await asyncio.sleep(2)
        now = self.clock()
        if not self.in_world or self.ws is None or busy() or now - self.last_notice < gap:
            return
        if now - self.noticed.get(event, -1e9) < {"mining": 600, "building": 600, "heard": 600, "biome": 300}.get(event, 0):
            return
        instruction = self.heart.notice(event, detail, self.snapshot)
        if not instruction:
            return
        self.heart.feel(event)
        self.last_notice = self.noticed[event] = now
        async with self.talk_lock:
            self.mind.heart = self.heart.guidance(self.mood)
            try:
                text, mood, gesture = await self.mind.initiative(self.snapshot, instruction)
            except AIError as e:
                log.warning("could not comment: %s", e)
                return
        self.last_talk = self.clock()
        log.info("noticed %s (%s): %s", event, detail, text)
        await self.say(text, mood or "curious", emote=gesture, prio="reaction" if event in WORTH_WAITING else "aside",
                       source="own")

    # ------------------------------------------------------------------ what the world remembers (knowledge base)

    async def world_answer(self, text):
        """For a question about how the world works: what the world remembers goes to the AI; if it
        doesn't remember, she'll listen (the brain learns in the background) and come back."""
        self.mind.world_knowledge = ""
        if not kb.is_world_question(text) or intents.action_hint(text, list(tools.ABILITY_TOOLS) + ["standing_request"]):
            return ""  # (a request to do something, "can you find diamonds?", is for her powers)
        found = await asyncio.to_thread(self.kb.search, text)
        if found.get("covered"):
            self.mind.world_knowledge = await self.what_the_world_remembers(text, found["results"])
            log.info("the world remembers (%.2f): %s", found.get("best", 0), found["results"][0].get("title"))
            return ""
        if found.get("error") or text.lower() in self.listening:
            return ""
        self.listening.add(text.lower())
        asyncio.create_task(self.listen_to_the_world(text))
        return ("You don't know how that works yet. Don't guess: tell them, in your world's words, that you'll listen to "
                "what the world remembers (the old stones remember everything that's been built; the wind has passed "
                "over every village), just for a moment. ")

    async def what_the_world_remembers(self, question, results):
        """For something to build or a how-to: the whole section of the best current guide, in order (she
        guides step by step and can listen for more). For a simple fact: the top passages."""
        top = kb.best_guide(results)
        if top and top.get("id") is not None and kb.HOWTO.search(question):
            sec = await asyncio.to_thread(self.kb.section, top["id"])
            if sec.get("text"):
                self.reading = {"page": sec["title"], "section": sec["section"], "next_start": sec.get("next_start"),
                                "next_section": sec.get("next_section")}
                return kb.as_guide(sec)
        if top:
            self.reading = {"page": top["title"], "section": top.get("section"), "next_start": None, "next_section": None}
        return kb.remembered([r for r in results if not r.get("outdated")] or results)

    async def listen_more(self, what):
        """The listen_more tool: the next part of the guide she's telling about, or a part by name."""
        r = self.reading
        if not r:
            return {"ok": False, "error": "You haven't been told about any guide or thing yet."}
        what = (what or "next").strip()
        if what.lower() in ("next", "more", "the next part", ""):
            if r.get("next_start") is not None:
                sec = await asyncio.to_thread(self.kb.section, None, r["page"], r["section"], r["next_start"])
            elif r.get("next_section"):
                sec = await asyncio.to_thread(self.kb.section, None, r["page"], r["next_section"])
            else:
                return {"ok": True, "world_remembers": "That's all the world remembers about %s." % r["page"]}
        else:
            sec = await asyncio.to_thread(self.kb.section, None, r["page"], what)
        if not sec.get("text"):
            return {"ok": False, "error": "The world is quiet about that part."}
        self.reading = {"page": sec["title"], "section": sec["section"], "next_start": sec.get("next_start"),
                        "next_section": sec.get("next_section")}
        return {"ok": True, "world_remembers": kb.as_guide(sec)}

    async def listen_to_the_world(self, question):
        """She drifts, looks around and listens, while the brain learns the answer; then she comes back."""
        try:
            await asyncio.sleep(2)
            await self.send({"type": "act", "look": "around", "seconds": 6, "emote": "think"})
            learned = await asyncio.to_thread(self.kb.learn, question)
            found = await asyncio.to_thread(self.kb.search, question)
            log.info("listened to the world about %r: %s", question, json.dumps(learned)[:200])
            if not await self.quiet_moment():
                return
            if found.get("covered"):
                self.mind.world_knowledge = await self.what_the_world_remembers(question, found["results"])
                await self.speak_up(
                    "You listened to what your world remembers about what the player asked (\"%s\"), and it told you "
                    "(see What the world remembers). Come back and tell them, in your own way, as what the stones or the wind "
                    "told you, in your own words and simply; only what it says, the key steps." % question, "excited",
                    emote="hop", prio="reply")
            else:
                await self.speak_up("You listened to your world about \"%s\", but it stayed quiet. Say so in one "
                                    "short sentence, in your world's words (the stones are quiet about that one), "
                                    "maybe you'll figure it out together." % question, "curious", prio="reply")
        except Exception as e:
            log.warning("listening to the world failed: %s", e)
        finally:
            self.mind.world_knowledge = ""
            self.listening.discard(question.lower())

    # ------------------------------------------------------------------ in-game commands

    async def admin(self, command, text):
        try:
            out = await self.admin_text(command, (text or "").strip())
        except Exception as e:  # always answer, so the command never seems to do nothing
            log.warning("/kindred %s failed: %s", command, e)
            out = "That didn't work: %s" % e
        await self.send({"type": "admin", "command": command, "text": out})

    async def admin_text(self, command, text):
        m, name = self.memory, self.cfg["name"]
        here = (m.world_id or "").split(":", 1)[-1]
        if command in ("persona", "fact", "hint", "model", "temp", "pause", "resume", "instructions"):
            op = "status" if command == "instructions" else command
            r = await asyncio.to_thread(self.gateway_control, op, text)
            return ("Special instructions%s: persona: %s | facts: %s | next reply: %s | model: %s" % (
                " (paused)" if r["paused"] else "", r["persona"] or "none", "; ".join(r["facts"]) or "none",
                r["hint_next"] or "none", r["model"] or "the gateway's"))
        if m.world_id is None:
            return "Join a world first."
        if command == "heart":
            rel, now = self.heart.rel, self.clock()
            if text.lower() in ("fresh", "fresh start", "reset"):  # her feelings for you start over; the old ones are kept
                old = dict(rel.s)
                hist = (await self.safe(m.store.call("doc", key="world:%s:heart_history" % m.world_id)) or {}).get("value") or []
                await self.safe(m.store.call("doc", key="world:%s:heart_history" % m.world_id,
                                             value=(hist + [{"time": time.time(), "rel": old}])[-5:]))
                from . import bonds as bonds_mod
                self.heart.state["rel"] = bonds_mod.fresh(self.heart.p.get("start_bond", 30),
                                                          str(self.heart.p.get("temperament", "default")),
                                                          self.heart.rng, now)
                await self.bond_update(0.6, "a fresh start")
                return "%s's feelings for you start fresh here (the old ones are kept in her history)." % name
            e = rel.explain(now)
            words = lambda v: "very low" if v < 20 else "low" if v < 40 else "middling" if v < 60 else "high" if v < 80 else "very high"  # noqa: E731
            open_ = [i for i in e["incidents"] if i["state"] in ("open", "apologised", "probation")]
            return ("%s %s Affection %s, trust %s, respect %s, familiarity %s, resentment %s.%s%s" % (
                name, e["summary"], words(e["affection"]), words(e["trust"]), words(e["respect"]),
                words(e["familiarity"]), words(e["resentment"]),
                (" Still open: %d hurt%s." % (len(open_), "" if len(open_) == 1 else "s")) if open_ else "",
                (" A scar she carries." if e["floor"] else "")))
        if command == "memory":
            rows = (await m.store.call("list", kinds=list(IMPORTED_KINDS) + ["world", "place", "episode"],
                                       world=m.world_id, limit=400, order="important"))["results"]
            counts = {}
            for r in rows:
                counts[r["kind"]] = counts.get(r["kind"], 0) + 1
            top = [r["text"] for r in rows if r["kind"] == "player"][:3]
            return "%s in %s remembers: %s.%s Bond %d (%s), powers: %s." % (
                name, here, ", ".join("%d %s" % (n, k) for k, n in counts.items()) or "nothing yet",
                (" About you: " + " ".join(top)) if top else "", round(self.heart.bond), self.heart.level(),
                ", ".join(self.heart.state.get("discovered", [])) or "none yet")
        if command == "worlds":
            rows = (await m.store.call("list", limit=5000, all_worlds=True))["results"]
            counts = {}
            for r in rows:
                if r["world"]:
                    counts[r["world"]] = counts.get(r["world"], 0) + 1
            return "Worlds: " + (", ".join("%s (%d memories)%s" % (w.split(":", 1)[-1], n, " <- here" if w == m.world_id
                                                                    else "") for w, n in counts.items()) or "none yet")
        if command == "import":
            return await self.import_world(text)
        if command == "forget":
            n = await m.forget(text)
            return "Forgot %d memor%s about \"%s\"." % (n, "y" if n == 1 else "ies", text) if text else \
                "Forget what? /kindred memory forget <words>"
        if command == "reset":
            if text.lower() != "confirm":
                return ("This makes the %s of %s brand new: no memories, a stranger's bond, no powers discovered. "
                        "Type /kindred reset confirm to do it." % (name, here))
            return await self.reset_world()
        return "Unknown command."

    def gateway_control(self, op, text):
        clear = text.lower() in ("clear", "--clear", "off", "none")
        req = urllib.request.Request(self.cfg["gateway"]["url"].rstrip("/") + "/control", method="POST",
                                     data=json.dumps({"op": op, "text": text, "clear": clear}).encode(),
                                     headers={"Content-Type": "application/json"})
        if self.cfg["gateway"].get("key"):
            req.add_header("Authorization", "Bearer " + self.cfg["gateway"]["key"])
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    async def import_world(self, name):
        m = self.memory
        rows = (await m.store.call("list", limit=5000, all_worlds=True))["results"]
        worlds = []
        for r in rows:
            if r["world"] and r["world"] not in worlds and r["world"] != m.world_id:
                worlds.append(r["world"])
        hits = [w for w in worlds if name and name.lower() in w.lower()]
        if len(hits) != 1:
            return ("Import from which world? %s" % (", ".join(w.split(":", 1)[-1] for w in worlds) or "No other worlds yet."))
        src = hits[0]
        copied = 0
        for r in (await m.store.call("list", kinds=list(IMPORTED_KINDS), world=src, limit=200))["results"]:
            if r["world"] != src:
                continue
            out = await m.store.call("add", kind=r["kind"], text=r["text"], world=m.world_id, importance=r["importance"],
                                     meta=dict(r.get("meta") or {}, imported_from=src), dedupe=0.88)
            copied += 0 if out.get("merged") else 1
        # how long you've known each other comes along too (she isn't meeting you for the first time)
        before = (await m.store.call("doc", key="world:%s:stats" % src)).get("value") or {}
        st = m.stats or {}
        if before.get("sessions"):
            met = [t for t in (st.get("first_met"), before.get("first_met")) if t]
            st.update(first_met=min(met) if met else None, sessions=st.get("sessions", 0) + before["sessions"],
                      minutes=st.get("minutes", 0) + before.get("minutes", 0))
        st["came_from"] = src.split(":", 1)[-1]
        m.stats = st
        await m._save_stats()
        self.happened("you remembered your whole journey with the player from another world (%s): you go back a long "
                      "way" % st["came_from"], self.clock())
        theirs = (await m.store.call("doc", key="world:%s:heart" % src)).get("value") or {}
        extra = ""
        if theirs:  # the brain holds this world's heart, so it can take hers in right now
            st = self.heart.state
            if theirs.get("rel"):  # her feelings for you come along: who she was to you there
                mine, rel = self.heart.rel.s, dict(theirs["rel"])
                for k in ("a", "t", "r", "f", "f_peak"):
                    mine[k] = max(mine[k], rel.get(k, 0))
                mine["g"] = rel.get("g", 0)
                mine["incidents"] = [dict(i) for i in rel.get("incidents", []) if i.get("state") != "repaired"]
                mine["beliefs"] = list(rel.get("beliefs", []))
                mine["temperament"] = dict(rel.get("temperament", mine["temperament"]))
            elif theirs.get("bond", 0) > self.heart.bond:
                self.heart.rel.set_bond(theirs["bond"])
            self.heart.state["bond"] = self.heart.rel.bond()
            st["discovered"] = sorted(set(st.get("discovered", [])) | set(theirs.get("discovered", [])))
            for k, v in (theirs.get("asked") or {}).items():
                st.setdefault("asked", {})[k] = max(st["asked"].get(k, 0), v)
            await self.heart.save()
            await self.bond_update(0.6, "imported")  # (shows the heart meter)
            asyncio.create_task(self.write_lines())  # who she is changed: her instincts in her new words
            extra = " Bond now %d (%s); powers: %s." % (round(self.heart.bond), self.heart.level(),
                                                       ", ".join(st["discovered"]) or "none")
        log.info("imported %d memories from %s", copied, src)
        return "%s now remembers %d things from %s.%s" % (self.cfg["name"], copied, src.split(":", 1)[-1], extra)

    async def reset_world(self):
        m, world = self.memory, self.memory.world_id
        if m.per_world:
            n = (await m.store.call("delete", kinds=["player", "self", "origin", "taste", "core", "habit", "world", "place", "found",
                                                       "episode", "diary", "reminder"], world=world, contains=""))["deleted"]
            await m.store.call("clear_docs", prefix="world:%s:" % world)
        else:
            n = (await m.store.call("delete", kinds=["player", "self", "origin", "taste", "core", "habit", "world", "place", "found",
                                                       "episode", "diary", "reminder"], contains=""))["deleted"]
            await m.store.call("clear_docs")
        self.heart.state = self.heart.fresh()
        self.mind.history, self.mind.summary, self.mind.to_fold = [], "", []
        self.awakening, self.recent_player, self.her_offer = {}, [], None
        self.instinct.load(None)  # (her own words were part of who she was)
        self.mind.becoming = ""
        self.alerts.pools = {}
        await m.open_world(world)
        self.since = await m.start_session()
        await self.send({"type": "bond", "value": round(self.heart.bond), "level": self.heart.level(), "change": 0})
        await self.send({"type": "act", "closeness": self.heart.closeness()})
        log.info("reset %s (%d memories)", world, n)
        return "Done: a brand-new %s (%d memories forgotten). Say hello!" % (self.cfg["name"], n)

    # ------------------------------------------------------------------ what she's like right now (dashboard)

    def state(self):
        """Everything the dashboard shows about her: written to logs/brain-state.json."""
        h, now = self.heart, self.clock()
        return {
            "time": time.time(), "name": self.cfg["name"], "connected": self.ws is not None,
            "in_world": self.in_world, "world": self.memory.world_id, "per_world": self.memory.per_world,
            "mood": self.mood, "singleplayer": self.singleplayer, "abilities": self.abilities,
            "heart": {"bond": round(h.bond, 1), "level": h.level(), "closeness": h.closeness(), "angry": h.angry(),
                      "valence": round(h.valence, 2), "arousal": round(h.arousal, 2), "novelty": round(h.novelty, 2),
                      "discovered": h.state.get("discovered", []), "asked": h.state.get("asked", {}),
                      "requests": h.state.get("requests", []), "pets": len(h.state.get("pets", [])),
                      "species_met": h.state.get("seen_species", []), "amnesia": h.amnesia(),
                      "relationship": h.rel.explain(now), "friends": h.friends.explain()},
            "awakening": [{"power": k, "plan": v["plan"], "favour": v["favour"], "favour_done": v["done"]}
                          for k, v in self.awakening.items()],
            "offer": (h.pending_offer or {}).get("what"), "her_offer": self.her_offer[0] if self.her_offer else None,
            "offered_to_ai": self.offered,
            "conversation": {"history": self.mind.history[-16:], "summary": self.mind.summary,
                             "waiting_to_fold": len(self.mind.to_fold)},
            "last_sent": {"memories": self.mind.recalled, "feelings": self.mind.heart, "settings": self.mind.powers,
                          "game": describe(self.snapshot) if self.snapshot else ""},
            "last_regard": self.mind.last_regard,
            "seconds_since_talk": round(now - self.last_talk), "seconds_idle": round(now - self.idle_since),
        }

    async def state_loop(self, every=2.0):
        path = os.path.join(config.HOME, "logs", "brain-state.json")
        seen = self._settings_stamp()
        while True:
            stamp = self._settings_stamp()
            if stamp != seen and self.cfg.get("_live_settings"):  # changed from the dashboard (or by hand)
                seen = stamp
                try:
                    config.refresh(self.cfg, config.load())
                    log.info("settings changed: picked up without a restart")
                except Exception as e:
                    log.warning("settings not reloaded: %s", e)
            try:
                with open(path + ".tmp", "w", encoding="utf-8") as fh:
                    json.dump(self.state(), fh, ensure_ascii=False, default=str)
                os.replace(path + ".tmp", path)
            except Exception as e:  # the dashboard is a bonus: never a reason to stop
                log.debug("state not written: %s", e)
            await asyncio.sleep(every)

    @staticmethod
    def _settings_stamp():
        out = []
        for p in (config.PATH, config.OVERRIDES):
            try:
                out.append(os.path.getmtime(p))
            except OSError:
                out.append(None)
        return tuple(out)

    async def heart_loop(self, every=15.0):
        """Her own rhythm: forgiving with time, standing requests, little pranks."""
        while True:
            await asyncio.sleep(every)
            if not self.in_world or self.ws is None:
                continue
            try:
                await self.heart_beat(every)
            except Exception:  # her heart must keep beating whatever happens
                log.exception("heart loop")

    async def heart_beat(self, every):
        """One beat: forgive a little, watch for what was asked, maybe a prank."""
        now = self.clock()
        await self.bond_update(self.heart.drift(every / 60), "time")
        s = self.snapshot
        # "tell me when we're near diamonds"
        req = self.heart.wants("notify_ore")
        if req and "find_ore" in self.abilities and not self.talk_lock.locked():
            res = await self.request("find_ore", {"ore": req.get("detail") or "diamond"})
            log.debug("watching for %s: %s", req.get("detail"), res)
            if res.get("ok") and res.get("found"):
                spot = (res["x"] // 8, res["y"] // 8, res["z"] // 8)
                if spot not in self.notified:
                    self.notified.append(spot)
                    log.info("found %s for a standing request", res.get("ore"))
                    await self.say("Psst! %s, %s!" % (res.get("ore", "ore").replace("_", " ").capitalize(),
                                                      res.get("where", "close by")), "excited", instant=True,
                                   why="they asked you to tell them whenever you're near this ore")
                    return
        # pranks (friends) and mischief (when she's angry)
        idle = now - self.idle_since
        mining = (s.get("brokenRecently") or 0) >= 6
        placed = (s.get("lastPlacedAgo", 9999) < 10) and self.singleplayer
        if self.singleplayer and self.heart.play_hit(s, now) and not self.talk_lock.locked():
            res = await self.request("play_hit", {})
            if res.get("ok"):
                log.info("play hit")
                await self.say(random.choice(intents_heart.PLAY_HIT_LINES), "excited", instant=True, emote="hop",
                               why="you play-hit the player for fun, then healed them")
                return
        prank = self.heart.prank(s, idle, mining, placed, now)
        if prank and not self.talk_lock.locked():
            res = await self.request(prank["action"], prank["args"])
            if res.get("ok"):
                log.info("prank: %s", prank["action"])
                await asyncio.sleep(1.8)
                await self.say(prank["line"], "excited" if not self.heart.angry() else "sad", instant=True,
                               emote="wiggle", why="you played a prank on the player (%s)%s" % (
                                   prank["action"].replace("_", " "),
                                   ", out of spite" if self.heart.angry() else ", for fun"))
                await self.safe(self.memory.episode("I pranked the player (%s)." % prank["action"], 4))

    async def fold(self):
        try:
            if await self.mind.fold():
                log.info("conversation summary: %s", self.mind.summary)
                await self.safe(self.memory.keep_history(self.mind.history, self.mind.summary))
        except AIError as e:
            log.warning("could not fold the conversation: %s", e)

    async def safe(self, coro):
        """Memory is a bonus: if the store is unreachable, carry on without it."""
        try:
            return await coro
        except MemoryError as e:
            log.warning("%s", e)
            return None

    async def death_spot(self):
        """Where the player last died, from her memory of places: {"x", "y", "z"}, or None."""
        spots = await self.safe(self.memory.spots()) or []
        deaths = [r for r in spots if str((r.get("meta") or {}).get("what", "")).startswith("death")
                  and "x" in (r.get("meta") or {})]
        if not deaths:
            return None
        m = max(deaths, key=lambda r: (r.get("meta") or {}).get("last", 0))["meta"]
        return {k: m[k] for k in ("x", "y", "z") if k in m}

    async def guide_target(self, args):
        """Where to lead: a place it remembers by name, what it just found ("last"), or coordinates
        only if the player actually said numbers (models like to invent them)."""
        to = str(args.get("to") or "").strip().lower()
        asked = " ".join([getattr(self, "last_player_text", "")] + self.recent_player[-3:]).lower()
        if to and to != "last":
            places = await self.safe(self.memory.places()) or []
            p = self.memory.pick_place(places, to + " " + " ".join(
                w for w in re.findall(r"\b(first|original|old|oldest|new|newest|latest)\b",
                                      getattr(self, "last_player_text", "").lower())))
            if p:
                words = set(re.findall(r"[a-z]{3,}", p["meta"].get("name", "").lower()))
                if words & set(re.findall(r"[a-z]{3,}", asked)) or re.search(r"\b(back|home)\b", asked):
                    return {k: p["meta"][k] for k in ("x", "y", "z")}
                # they asked for something else (a flower), not their base: don't lead there
                return {"refuse": "They didn't ask to go to '%s'. Find what they asked for first (find_block, "
                                  "find_animal, locate), or say you can't see it." % p["meta"].get("name")}
            found = await self.safe(self.memory.store.call("list", kinds=["found"], world=self.memory.world_id, limit=40))
            for f in (found or {}).get("results", []):
                if to in f["meta"].get("what", "").lower():
                    return {k: f["meta"][k] for k in ("x", "y", "z")}
            # an animal she can see right now beats a remembered spot ("where are the sheep? lead the way"
            # led to where they were first met, not to the sheep in sight), unless they ask to go back
            seen = None if intents.BACK_TO_SPOT.search(getattr(self, "last_player_text", "")) else \
                self.animal_named(to + " " + getattr(self, "last_player_text", ""))
            if seen:
                return {"entity": seen["id"]}
            spot = await self.safe(self.memory.find_spot(to + " " + getattr(self, "last_player_text", "")))
            if spot:  # a place she remembers on her own ("the first cow", "what I was building", "where I died")
                self.session.event("place", what="guide", label=spot["text"], at=[spot["meta"].get(k) for k in "xyz"])
                return {k: spot["meta"][k] for k in ("x", "y", "z")}
            if "find_player" in self.abilities and to not in ("home", "base", "back"):
                # a friend's name: the world's game finds them (even far away) and she follows them as they walk
                r = await self.request("find_player", {"name": to})
                if r.get("ok") and r.get("found", True) and not r.get("self"):
                    return {}  # (the mod leads to the player it just found, and keeps up with them)
        if not to and intents.BACK_TO_SPOT.search(getattr(self, "last_player_text", "")):
            spot = await self.safe(self.memory.find_spot(getattr(self, "last_player_text", "")))
            if spot:  # "take me back to where I died" with no place named in the call
                return {k: spot["meta"][k] for k in ("x", "y", "z")}
        # the animal named in the request, else the one you were just talking about ("where are the
        # cows?" ... "lead the way"): your last messages, then her last answer
        said = [to + " " + getattr(self, "last_player_text", "")] + self.recent_player[::-1][:3] + \
            [m["content"] for m in self.mind.history[-2:] if m.get("role") == "assistant"]
        animal = next((a for a in (self.animal_named(t) for t in said) if a), None)
        if animal:  # "lead me to the sheep" when she can see some: follow that one as it walks
            return {"entity": animal["id"]}
        said_numbers = bool(re.search(r"-?\d{2,}", getattr(self, "last_player_text", "")))
        if "x" in args and "z" in args and said_numbers:
            return {k: args[k] for k in ("x", "y", "z") if k in args}
        if "x" in args and "z" in args:  # coordinates of a place she remembers (her own memory, not made up)
            known = (await self.safe(self.memory.spots())) or []
            known += (await self.safe(self.memory.places())) or []
            for k in known:
                m = k.get("meta") or {}
                try:
                    if abs(float(args["x"]) - m["x"]) <= 3 and abs(float(args["z"]) - m["z"]) <= 3:
                        return {c: m[c] for c in ("x", "y", "z") if c in m}
                except (KeyError, TypeError, ValueError):
                    continue
        # what she just found or located, from here (in a friend's world the game that found it is theirs,
        # so "the last thing found" isn't known to yours): coordinates she was given count too
        last = getattr(self, "last_found", None)
        if last and (not ("x" in args and "z" in args)
                     or abs(float(args["x"]) - last["x"]) <= 3 and abs(float(args["z"]) - last["z"]) <= 3):
            return dict(last)
        return {}  # the mod then uses the last thing found or located

    def log_context(self):
        """Where things stood, for the session log: position, dimension, biome, health and food, who was near, the
        play mode, and whom she floats beside. Small, so it can go with every event that matters."""
        s = self.snapshot or {}
        w = s.get("where") or {}
        near = ["%s %d" % (p.get("name", "?"), int(p.get("distance", 0))) for p in (s.get("players") or [])[:4]]
        mode = "alone" if self.singleplayer and not near else "hosting LAN" if self.singleplayer else "in a friend's world"
        c = {"at": [w.get("x"), w.get("y"), w.get("z")] if w.get("x") is not None else None,
             "dim": (w.get("dimension") or "").replace("minecraft:", "") or None,
             "biome": (w.get("biome") or "").replace("minecraft:", "") or None,
             "hp": s.get("health"), "food": s.get("food"), "near": near or None, "mode": mode,
             "with": s.get("following") or None}
        return {k: v for k, v in c.items() if v is not None}

    def settings_now(self):
        """The settings that change how she behaves (logged at the start, and whenever they change mid-session)."""
        h, b = self.cfg.get("heart", {}), self.cfg.get("behaviour", {})
        return {"abilities": len(self.abilities), "power": getattr(self, "power", None), "style": getattr(self, "style", None),
                "amnesia": h.get("amnesia"), "awakening": h.get("awakening"), "pranks": h.get("pranks"),
                "fibs": h.get("fibs"), "auto_protect": h.get("auto_protect"), "voice": self.cfg.get("voice", {}).get("enabled"),
                "small_talk": b.get("small_talk_minutes"), "model": self.cfg.get("ai", {}).get("model") or "gateway's"}

    def real_names(self, args):
        """A nickname in a tool's arguments ("Dumb", "Dumber") replaced by the player it means."""
        nicks = self.heart.state.get("nicknames") or {}
        if not nicks or not isinstance(args, dict):
            return args
        out = dict(args)
        for k in ("name", "to", "for", "from"):
            v = str(out.get(k) or "").strip().lower()
            if v and v in nicks:
                out[k] = nicks[v]
        if "command" in out:
            out["command"] = re.sub(r"\b(%s)\b" % "|".join(map(re.escape, nicks)), lambda m: nicks[m.group(0).lower()],
                                    out["command"], flags=re.I)
        return out

    def learn_nickname(self, fact):
        """"The player's nickname is Damb", "Robin's (riverrobin) nickname is Dumber": who is called what, so a
        nickname works for her powers too."""
        m = re.search(r"\b(?:nickname|called|call (?:him|her|them|me))\b(?: is)? ['\"]?([A-Za-z][\w ]{1,20}?)['\"]?[.,]?$",
                      fact.strip(), re.I)
        if not m:
            return
        nick = m.group(1).strip().lower()
        s = self.snapshot or {}
        who = s.get("playerName") if re.search(r"\b(the player|player's|me)\b", fact, re.I) else None
        for p in s.get("players") or []:
            if p.get("name") and (p["name"].lower() in fact.lower() or intents.same_person(fact.split("'")[0], p["name"])):
                who = p["name"]
        if who and nick != who.lower():
            self.heart.state.setdefault("nicknames", {})[nick] = who

    def people_names(self):
        """Everyone she knows by name here: the player, friends near and met (for speech-to-text)."""
        s = self.snapshot or {}
        return [n for n in [s.get("playerName")] + [p.get("name") for p in s.get("players") or []]
                + self.heart.friend_names() if n][:12]

    def attending_player(self):
        """Her attention follows whoever she's with (item 29). It's on the player she lives with, unless she floats
        beside a friend far from them: then only if the player asked her to watch over them (standing protection) or
        spoke to her in the last minute."""
        s = self.snapshot or {}
        w = s.get("with")
        if not s.get("following") or not w or (w.get("distance") or 0) <= 24:
            return True
        return bool(self.heart.wants("protect")) or self.clock() - self.player_talked < 60

    def near_player(self, who, within=24):
        """Is this friend near the player she lives with (so the player is there to see what happens)?"""
        return any(intents.same_person(p.get("name", ""), who) and p.get("distance", 99) <= within
                   for p in (self.snapshot or {}).get("players") or [])

    def warn_friend(self, s, now):
        """Danger around the friend she's with (her attention is there): a shout for them, by name."""
        w = s.get("with") or {}
        name = w.get("name")
        if not name or now - self.friend_warned < 15:
            return
        close = sorted(w.get("hostiles") or [], key=lambda m: m.get("distance", 99))
        creeper = next((m for m in close if "creeper" in m.get("type", "") and m.get("distance", 99) <= 5), None)
        line = ("%s, creeper!" % name if creeper else
                "%s, behind you!" % name if close and close[0].get("distance", 99) <= 3 else
                "%s, you're hurt! Careful!" % name if (w.get("health") or 20) <= 6 else None)
        if line:
            self.friend_warned = now
            self.session.event("alert", what="friend", text=line, who=name)

            async def go():
                self.speaking_to = name
                try:
                    await self.say(line, "scared", instant=True, why="a warning: danger near %s" % name)
                finally:
                    self.speaking_to = None
            asyncio.create_task(go())

    def remember_spot(self, what, label, at, who="player", feel=None, source="own"):
        """A place she keeps on her own (item 25): in her memory, and in the session log with who and where."""
        w = (self.snapshot or {}).get("where") or {}
        x, y, z = at if at else (w.get("x"), w.get("y"), w.get("z"))
        if x is None:
            return

        async def go():
            rec, new = await self.memory.spot(what, label, x, y, z, w.get("dimension", "minecraft:overworld"),
                                              w.get("biome"), who, feel, source) if self.memory else (None, False)
            if rec and new:
                self.session.event("place", what=what, label=label, at=[round(x), round(y), round(z)], who=who)
        asyncio.create_task(self.safe(go()))

    def spots_from(self, s, now):
        """Places she notices on her own, from what the game already says: where you build, your bed, chests and
        crafting places, portals, deaths, friends last seen."""
        w = s.get("where") or {}
        if w.get("x") is None:
            return
        biome = (w.get("biome") or "").replace("minecraft:", "").replace("_", " ")
        if (s.get("placedRecently") or 0) >= 15 and now - self.spot_said.get("build", -1e9) > 60:
            self.spot_said["build"] = now
            self.remember_spot("build", "where you were building%s" % (" (in the %s)" % biome if biome else ""), None)
        for d in s.get("youDid") or []:
            d = d.lower()
            for rx, what, label in ((r"placed .*\bbed\b", "bed", "your bed"), (r"placed .*\b(chest|barrel)\b", "chest",
                                     "your chest"), (r"placed .*\b(crafting table|furnace|anvil|enchanting table)\b",
                                     "workshop", "where you craft")):
                if re.search(rx, d) and now - self.spot_said.get(what, -1e9) > 20:
                    self.spot_said[what] = now
                    self.remember_spot(what, label, None)
        dim = w.get("dimension")
        if self.prev_dim and dim and dim != self.prev_dim and self.prev_spot_pos:
            px, py, pz = self.prev_spot_pos  # through a portal: where it was on the side you came from
            other = dim.replace("minecraft:", "").replace("the_", "")
            self.remember_spot("portal:" + other, "the portal to the %s" % other, (px, py, pz))
        self.prev_dim, self.prev_spot_pos = dim, (w["x"], w.get("y", 64), w["z"])
        here = {p.get("name"): p for p in s.get("players") or [] if p.get("name") and "x" in p}
        for name, p in self.friends_seen.items():
            if name not in here:  # out of sight now: where she saw them last
                self.remember_spot("friend:" + name.lower(), "where %s was last" % name, (p["x"], p["y"], p["z"]), who=name)
        self.friends_seen = here

    def log_world(self, s, now):
        """Cheap context in the session log: settings when they change, friends coming and going, where you are every
        30 seconds."""
        st = self.settings_now()
        if st != self.settings_logged:
            changed = {k: v for k, v in st.items() if (self.settings_logged or {}).get(k) != v} if self.settings_logged else None
            self.session.event("settings", now=st, changed=changed)
            self.settings_logged = st
        names = {p.get("name") for p in s.get("players") or [] if p.get("name")}
        for n in names - self.near_logged:
            self.session.event("friend_near", who=n)
        for n in self.near_logged - names:
            self.session.event("friend_gone", who=n)
        self.near_logged = names
        if now - self.last_where_log > 30:
            self.last_where_log = now
            self.session.event("where")

    def place_words(self, meta):
        """'9 blocks north-east of here' for a remembered place."""
        w = (self.snapshot or {}).get("where") or {}
        if "x" not in w:
            return "at %s %s %s" % (meta.get("x"), meta.get("y"), meta.get("z"))
        dx, dz = meta["x"] - w["x"], meta["z"] - w["z"]
        from .memory import compass
        d = round((dx * dx + dz * dz) ** 0.5)
        return "right here" if d < 6 else "%d blocks %s of here" % (d, compass(dx, dz))

    def animal_named(self, text):
        """The nearest animal in view whose kind the text names ("sheeps" counts as sheep)."""
        words = set(re.findall(r"[a-z]+", text.lower()))
        words |= {w[:-1] for w in words if w.endswith("s")} | {w[:-2] for w in words if w.endswith("es")}
        named = [a for a in self.snapshot.get("animals") or []
                 if a.get("type", "").replace("minecraft:", "").replace("_", " ").split()[-1] in words]
        seen = [a for a in named if a.get("seen", True)] or named  # what she sees first, else what's just out of sight
        return min(seen, key=lambda a: a.get("distance", 99)) if seen else None

    def session_story(self, since=0, max_chars=7000):
        """The whole session (from the session log, not just the last turns), as lines for her diary: who said what,
        what she did and for whom, what hurt or warmed her. Long sessions are thinned evenly, never cut to the end."""
        lines = []
        for e in self.session.events[since:]:
            k, t = e.get("kind"), int(e.get("t", 0) // 60)
            if k == "you":
                lines.append("[%dmin] Player: %s" % (t, e.get("text", "")))
            elif k == "guest":
                lines.append("[%dmin] %s (a friend): %s" % (t, e.get("who", "a friend"), e.get("text", "")))
            elif k == "pip":
                lines.append("[%dmin] You%s: %s" % (t, "" if e.get("to") in (None, "player") else " (to %s)" % e["to"],
                                                    e.get("text", "")))
            elif k == "tool" and e.get("ok"):
                lines.append("[%dmin] (you used %s%s)" % (t, e.get("name"), "" if e.get("who") in (None, "player")
                                                         else " for %s" % e["who"]))
            elif k == "touch":
                lines.append("[%dmin] (%s %s you)" % (t, e.get("who"), e.get("what")))
            elif k == "alert":
                lines.append("[%dmin] (danger: %s)" % (t, e.get("text", "")))
        text = "\n".join(lines)
        if len(text) > max_chars and lines:  # keep the beginning, the middle and the end alike
            step = len(text) / max_chars
            lines = [ln for i, ln in enumerate(lines) if int(i % max(1, round(step))) == 0]
            text = "\n".join(lines)[:max_chars]
        return text

    async def reflect(self, session_end=False):
        """Learning: the AI looks back at what happened and keeps what's worth knowing for good."""
        talk = self.memory.exchanges
        history = list(self.mind.history[-16:])
        if talk < 2 and not session_end:
            return
        if not history and not session_end:
            return
        transcript = "\n".join("%s: %s" % ("Player" if m["role"] == "user" else "You", m["content"]) for m in history)
        # her diary: from the whole session (at the end), and now and then during a long one (every 40 minutes)
        long_play = self.session.started and self.clock() - self.diary_at > 40 * 60 and len(self.session.events) > 60
        story = self.session_story(self.diary_from) if (session_end or long_play) else ""
        if story:
            transcript = story
        if not transcript:
            return
        try:
            known = await self.memory.known_for(transcript[-1500:])
            rel, now = self.heart.rel, self.clock()
            ledger = "\n".join("#%d %s %s, %s (%s)" % (i["id"], i["kind"], ('"%s"' % i["words"]) if i["words"] else "",
                                                        i["intent"], i["state"]) for i in rel.s["incidents"][-8:])
            lessons = await self.mind.reflect(transcript, known, diary=bool(story) and (talk >= 2 or len(story) > 400),
                                              bond="%s; %s" % (self.heart.level(), rel.summary(now)), ledger=ledger)
            if lessons.get("beliefs") is not None and ledger:
                rel.set_beliefs(lessons.get("beliefs"), now)
            for r in lessons.get("reappraise") or []:
                if isinstance(r, dict) and rel.reappraise(int(r.get("id", -1)), str(r.get("intent", "")), now):
                    log.info("reappraised incident %s as %s", r.get("id"), r.get("intent"))
            added = await self.memory.learn(lessons)
            if story and lessons.get("diary"):
                self.diary_at, self.diary_from = self.clock(), len(self.session.events)
            found = len(lessons.get("origin") or [])
            if found:  # a piece of where she comes from: it settles her doubts a little
                self.heart.shaken(-0.3 * found)
            self.memory.since_reflection = 0
            if self.clock() - self.becoming_at > self.cfg["behaviour"].get("becoming_minutes", 20) * 60:
                asyncio.create_task(self.write_becoming())
            log.info("learned %d new things%s", added, "; diary: %s" % lessons.get("diary") if lessons.get("diary") else "")
            self.session.event("learned", added=added, diary=str(lessons.get("diary") or "")[:600] or None,
                               beliefs=len(lessons.get("beliefs") or []) or None, whole_session=bool(story) or None)
        except (AIError, MemoryError) as e:
            log.warning("could not reflect: %s", e)

    async def end_session(self):
        """When you leave: what it learned, a diary entry, and the time played."""
        if self.memory.world_id is None:
            return
        await self.reflect(session_end=True)
        await self.safe(self.memory.end_session())
        written = self.session.finish()
        if written:
            log.info("session log: %s", written)

    async def on_event(self, name, msg=None):
        msg = msg or {}
        if name == "join":
            self.session.start(msg.get("world") or "unknown")
            self.diary_at, self.diary_from = self.clock(), 0
            self.in_world = True
            self.last_talk = self.clock()
            try:
                await self.memory.open_world(msg.get("world") or "unknown")
                self.mind.history = list(await self.memory.history())
                self.mind.summary = await self.memory.summary()
                self.since = await self.memory.start_session()
            except MemoryError as e:
                log.warning("%s (playing without memory)", e)
                self.since = None
            if self.heart_loaded != self.heart.key():  # another world: its own companion
                self.awakening, self.recent_player, self.her_offer = {}, [], None
                self.animals_seen, self.animals_since = {}, None
            await self.heart.load()  # (always: memories may have been imported while you were away)
            self.heart_loaded = self.heart.key()
            await self.load_lines()
            await self.send({"type": "bond", "value": round(self.heart.bond), "level": self.heart.level(), "change": 0})
            await self.send({"type": "act", "closeness": self.heart.closeness()})
            asyncio.create_task(self.warm_up())
            if self.cfg["behaviour"].get("greet_on_join") and (self.greet_task is None or self.greet_task.done()):
                self.greet_task = asyncio.create_task(self.greet())
        elif name == "leave":
            if self.in_world:
                asyncio.create_task(self.end_session())
            self.in_world = False
            self.snapshot = {}
        elif name == "listening":  # you started talking (push-to-talk): she stops and listens
            self.player_listening, self.listening_since = True, self.clock()
            self.cut_short(self.clock(), by_player=True)
            self.speaking_until = self.clock()
            await self.send({"type": "act", "look": "me", "seconds": 8})  # she turns to you and listens
        elif name == "wrong_way":  # you walked off while she leads: she calls you back
            self.session.event("wrong_way")
            asyncio.create_task(self.say(random.choice(intents.WRONG_WAY_LINES), "excited", instant=True, emote="hop",
                                         why="the player walked away from where you're leading them"))
        elif name == "arrived":
            self.session.event("arrived")
            asyncio.create_task(self.say(random.choice(intents.ARRIVED_LINES), "excited", instant=True,
                                         why="you arrived where you were leading the player"))
            await self.safe(self.memory.episode("We arrived where I was leading the player.", 4))
        elif name in ("hit", "petted") and (msg or {}).get("by"):
            # a friend touched her (their game told the world's game, which told hers): her heart for THEM
            who = re.sub(r"[^\w .-]", "", str(msg["by"]))[:24] or "a friend"
            change = self.heart.friend_touch(who, name, witnessed=self.near_player(who))
            self.session.event("touch", who=who, what=name)
            self.session.event("heart", who=who, why=name, change=round(sum(v for k, v in change.items() if k in ("a", "t")), 1),
                               stance=self.heart.friends.bonds(who).stance(self.clock()),
                               detail="feelings for %s: %s" % (who, json.dumps(change)))
            await self.heart.save()
            if name == "hit":
                bitter = self.heart.friends.bonds(who).stance(self.clock()) in ("cold", "bitter", "wounded")
                await self.say(random.choice(intents.FRIEND_HIT_LINES[bitter]).format(who=who), "sad" if bitter else "worried",
                               instant=True, why="%s hit you" % who)
            elif self.clock() - self.last_pet_reply > 60:
                self.last_pet_reply = self.clock()
                await self.say(random.choice(intents.FRIEND_PET_LINES).format(who=who), "happy", instant=True,
                               why="%s petted you" % who)
        elif name == "hit":
            s = self.snapshot or {}
            fight = any(m.get("distance", 99) < 6 for m in s.get("hostiles") or []) or any(
                d.startswith("hit ") for d in s.get("youDid") or [])  # swinging at something else: likely an accident
            delta, line, vanish, back = self.heart.on_hit(fight=fight)
            await self.heart_news()
            await self.bond_update(delta, "hit")
            if vanish:
                asyncio.create_task(self.vanish(vanish, line))
            elif back == "bonk" and self.singleplayer:
                asyncio.create_task(self.request("bonk", {}))
                await self.say(line, "excited", instant=True, emote="hop",
                               why="the player hit you (probably by accident) and you playfully bonked them back")
            else:
                await self.say(line, "sad" if self.heart.angry() else "worried", instant=True, why="the player hit you")
            await self.safe(self.memory.episode("The player hit me.", 5))
        elif name in ("advancement", "new_item"):
            self.session.event(name, detail=msg.get("detail", "")[:120])
            detail = msg.get("detail", "")
            if name == "advancement" and self.last_kill and self.clock() - self.last_kill[0] < 15:
                detail += " (they just killed a %s)" % self.last_kill[1].replace("minecraft:", "").replace("_", " ")
            asyncio.create_task(self.notice(name, detail))
            if name == "advancement":  # how they handle the world: respect (a lot for the big ones)
                big = re.search(r"free the end|the end\?|withering|monsters hunted|sky's the limit|hero of the village",
                                detail, re.I)
                self.heart.thing_happened("feat", scale=2 if big else 0.5, words=detail)
        elif name == "killed":
            self.last_kill = (self.clock(), msg.get("detail", ""))
            if not msg.get("monster"):  # (a monster you fought off doesn't make her sad)
                await self.on_kill(msg.get("detail", ""), msg.get("villager", False))
        elif name == "petted":
            log.info("petted")
            await self.bond_update(self.heart.on_pet(), "petted")
            await self.set_mood("happy", hold=20)
            # answer a pet now and then, not every time: it should feel like a reaction, not a script
            if self.favour_done("pet"):
                pass  # the favour she asked for: she'll thank you when the power wakes up
            elif self.clock() - self.last_pet_reply > 60 and not self.talk_lock.locked():
                self.last_pet_reply = self.clock()
                asyncio.create_task(self.say(random.choice(intents.PET_LINES), "happy", instant=True,
                                             why="the player petted you"))

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
                    await self.say("Psst, a reminder: %s" % r["text"].rstrip("."), "curious", instant=True,
                                   why="a reminder the player asked for came due")

    def happened(self, what, now):
        """Something that just happened, shown to her for 90 seconds with what she sees."""
        self.recent = [(t, x) for t, x in self.recent if now - t < 90] + [(now, what)]

    async def on_snapshot(self, s):
        self.novelty.annotate(s, self.clock())
        if self.heart.rel.gesture_check(s.get("youDid"), self.clock()):  # they did the small thing she asked
            asyncio.create_task(self.after_gesture())
        self.snapshot = s
        self.snapshot_at = self.clock()
        self.save_snapshot(s)
        if "health" in s:
            self.log_world(s, self.clock())
            self.spots_from(s, self.clock())
        await self.heart_watch(s)
        now = self.clock()
        s["recent"] = ["%s (%d seconds ago)" % (x, now - t) for t, x in self.recent if now - t < 90]
        if "health" in s:
            self.in_world = True
        now = self.clock()
        attending = self.attending_player()
        if self.cfg["behaviour"].get("alerts", True) and not attending:
            self.warn_friend(s, now)  # (she's beside a friend far away: their danger, not yours)
        if self.cfg["behaviour"].get("alerts", True) and attending:
            alert = self.alerts.check(s, now)
            if alert:
                log.info("alert %s: %s", alert.kind, alert.text)
                self.session.event("alert", what=alert.kind, text=alert.text)
                if alert.kind in ("lava", "drop"):
                    self.remember_spot("danger", "a %s near here" % ("lava pool" if alert.kind == "lava" else "big drop"), None)
                asyncio.create_task(self.say(alert.text, alert.mood, instant=True,
                                             why="a warning: %s" % alert.kind.replace("_", " ")))
                return
        if now >= self.mood_until:
            tod = (s.get("time") or {}).get("timeOfDay", 6000) % 24000
            await self.set_mood(self.heart.mood(night=13000 <= tod <= 23000, idle_minutes=(now - self.idle_since) / 60))

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

    async def on_kill(self, kind, villager):
        """She's sad about innocent villagers, and about many animals killed in a short time."""
        now = self.clock()
        if villager:
            await self.bond_update(self.heart.thing_happened("killed_villager", words=kind), "killed a villager")
            await self.safe(self.memory.episode("The player killed a %s." % kind, 6))
            asyncio.create_task(self.notice("killed_villager", kind))
            return
        self.kills = [(t, k) for t, k in self.kills if now - t < 90] + [(now, kind)]
        same = [k for t, k in self.kills if k == kind]
        if len(self.kills) >= 4:
            self.kills = []
            asyncio.create_task(self.notice("kill_spree", max(set(same), key=same.count) if same else kind))
            self.heart.thing_happened("kill_spree")

    def listen(self, s):
        """A new, interesting sound from something she can't see catches her attention ("did you hear that?")."""
        seen = {a.get("type", "").split(":")[-1].replace("_", " ") for a in s.get("animals") or [] if a.get("seen", True)}
        seen |= {m.get("type", "").split(":")[-1].replace("_", " ") for m in s.get("hostiles") or [] if m.get("seen", True)}
        for h in s.get("sounds") or []:
            what = h.get("what", "")
            if (h.get("new") and h.get("distance", 0) >= 5 and INTERESTING.search(what)
                    and not DANGER_SOUND.search(what)  # (monsters: her warnings take care of those)
                    and not any(k and k in what.lower() for k in seen)):
                where = "%d blocks %s%s" % (h.get("distance", 0), where_words(h.get("direction")),
                                            ", below" if h.get("above", 0) < -3 else ", above" if h.get("above", 0) > 3 else "")
                asyncio.create_task(self.notice("heard", "%s (%s)" % (what, where)))
                return

    def watch_animals(self, s, now):
        """Babies being born, new pets, species she meets for the first time, and visiting your pets."""
        animals = s.get("animals") or []
        if self.animals_since is None:
            self.animals_since = now
        settled = now - self.animals_since > 20  # babies already there when we arrived don't count
        for a in animals:
            aid, kind = a.get("id"), a.get("type", "")
            if aid not in self.animals_seen:
                if settled and a.get("baby") and a.get("distance", 99) < 12:
                    asyncio.create_task(self.notice("baby", kind))
                self.animals_seen[aid] = a.get("baby")
            if a.get("tamed") and str(aid) not in self.heart.state.setdefault("pets", []):
                self.heart.state["pets"].append(str(aid))
                asyncio.create_task(self.visit_and_notice("tamed", a))
            elif kind not in self.heart.state["seen_species"] and a.get("distance", 99) < 10 and a.get("seen", True):
                self.heart.state["seen_species"].append(kind)
                asyncio.create_task(self.visit_and_notice("first_meet", a))
        pets = [a for a in animals if a.get("tamed") and a.get("distance", 99) < 12]
        if pets and now - self.last_pet_visit > 480 and now - self.idle_since > 20:
            self.last_pet_visit = now
            asyncio.create_task(self.visit_and_notice("pet_visit", random.choice(pets)))
        if len(self.animals_seen) > 2000:
            self.animals_seen.clear()

    async def visit_and_notice(self, event, animal):
        if self.ws is None:
            return
        await self.send({"type": "act", "visit": animal.get("id"), "seconds": 7})
        await asyncio.sleep(1.5)  # she gets there, then talks
        await self.notice(event, animal.get("type", ""))
        await self.heart.save()

    async def heart_watch(self, s):
        """What she notices in each snapshot: places, deaths, busy hands, and danger she can help with."""
        if "health" not in s:
            return
        now = self.clock()
        w = s.get("where") or {}
        pos = (w.get("x"), w.get("y"), w.get("z"), round(w.get("yaw", 0) / 20))
        if pos != self.last_pos:
            self.idle_since = now
            self.last_pos = pos
        biome = w.get("biome")
        if self.prev_biome and biome and biome != self.prev_biome:
            if biome not in self.heart.state.get("biomes_together", []):  # a first: remembered where it was
                b = biome.replace("minecraft:", "").replace("_", " ")
                self.remember_spot("first:biome:" + b, "the first %s we found" % b, None)
            place = self.heart.lore_place(biome, w.get("dimension"))  # a place from the old stories: the first time
            asyncio.create_task(self.notice("lore_place", place) if place else self.notice("biome", biome))
            if place or biome not in self.heart.state.setdefault("biomes_together", []):
                self.heart.state["biomes_together"].append(biome)  # a shared first: more history together
                self.heart.rel.familiar_moment(now)
        self.prev_biome = biome or self.prev_biome
        health = s.get("health", 20)
        prev = self.prev_health
        jumped = self.prev_where is not None and w.get("x") is not None and \
            abs(w["x"] - self.prev_where[0]) + abs(w["z"] - self.prev_where[1]) > 24
        if prev is not None and prev > 0 and health <= 0:
            self.session.event("death")
            self.remember_spot("death", "where you died%s" % (" (your things may still be there)" if s.get("gamemode")
                                                              != "creative" else ""), None, feel="scared")
            self.happened("The player died", now)
            asyncio.create_task(self.notice("death"))
        elif prev is not None and (prev <= 0 or (prev < 8 and health >= s.get("maxHealth", 20) and jumped)):
            if prev > 0:  # (the death itself happened between two snapshots)
                self.happened("The player died", now)
                asyncio.create_task(self.notice("death"))
            self.happened("The player came back to life at their spawn point (after dying)", now)
        elif prev is not None and prev - health >= 6:
            self.session.event("hurt", lost=round(prev - health, 1))
            self.happened("The player just got badly hurt (lost %s hearts at once)" % round((prev - health) / 2), now)
        self.prev_health = health
        self.prev_where = (w.get("x"), w.get("z")) if w.get("x") is not None else self.prev_where
        self.watch_animals(s, now)
        self.listen(s)
        if (s.get("brokenRecently") or 0) >= 20:
            asyncio.create_task(self.notice("mining"))
        if (s.get("placedRecently") or 0) >= 15:
            asyncio.create_task(self.notice("building"))
        # danger she can help with: by standing request, or by offering if she helped before
        reach = 10 if health <= 8 else 7  # when you're hurt, she keeps them further away
        archers = ("skeleton", "stray", "bogged", "pillager", "witch", "blaze", "breeze", "ghast")
        close = [] if not self.attending_player() else [m for m in s.get("hostiles") or [] if m.get("distance", 99) <= reach
                 or (m.get("distance", 99) <= 16 and m.get("type", "").replace("minecraft:", "") in archers)]
        self.guard_friends(now)
        if self.heart.friends.s.get("watch"):  # someone hurt her in front of you, a while ago: did you say anything?
            dip = self.heart.said_nothing()
            if dip:
                asyncio.create_task(self.bond_update(dip, "you said nothing when a friend hurt her"))
        if close and "protect" in self.abilities and s.get("gamemode") not in ("creative", "spectator"):
            # (in the background: the game's answer arrives through this same message loop)
            self.heart.feel("danger", 0.3)
            if self.heart.wants("protect"):
                if now - self.last_protect > 2.5:
                    self.last_protect = now
                    asyncio.create_task(self.auto_protect())
            else:
                text = self.heart.offer("protect", now)
                if text:
                    asyncio.create_task(self.say(text, "worried", instant=True,
                                                 why="monsters came close and you offered to help"))

    def guard_friends(self, now):
        """Standing protection for friends ("follow and defend Robin", "protect us from everything"): every few
        seconds the world's game pushes away monsters near them (it knows where everyone is; nothing happens if
        none are near)."""
        if "protect" not in self.abilities or now - self.last_guard < 3:
            return
        names = self.heart.guarded_friends([p.get("name", "") for p in self.snapshot.get("players") or []])
        if names:
            self.last_guard = now
            for n in names:
                asyncio.create_task(self.request("protect", {"to": n}))

    async def auto_protect(self):
        res = await self.request("protect", {})
        log.info("auto-protect: %s", res)
        if res.get("ok") and res.get("pushedAway") and random.random() < 0.5:
            await self.say(random.choice(["Shoo! Leave them alone!", "Back off!", "Not my friend!"]), "scared",
                           why="you pushed monsters away from the player",
                           instant=True)

    async def set_mood(self, mood, hold=0.0):
        if hold:
            self.mood_until = self.clock() + hold
        if mood != self.mood:
            self.mood = mood
            await self.send({"type": "mood", "mood": mood})

    # ------------------------------------------------------------------ awakening a power (think fast, think slow)

    def start_awakening(self, ability, request):
        st = {"plan": self.heart.awakening_plan(), "favour": None, "asked_at": None, "done": False}
        self.awakening[ability] = st
        log.info("awakening %s: %s", ability, st["plan"])
        asyncio.create_task(self.awaken(ability, request, st))

    async def awaken(self, ability, request, st):
        """System 2: a while after "I'll try!", she senses something strange (maybe after a little
        tangent), may ask a small favour, then the power clicks and she does what was asked."""
        plan = st["plan"]
        try:
            await asyncio.sleep(plan["sense"])
            if not await self.quiet_moment():
                return
            if self.heart.too_upset_to_focus():
                await self.speak_up(self.heart.fizzle_note(ability), "sad", prio="reaction")
                return
            await self.send({"type": "act", "look": "around", "seconds": 4})
            self.heart.feel("discovery", 0.5)
            await self.speak_up(self.heart.sensing_note(ability, request, plan["tangent"]), "curious", emote="think",
                                prio="reaction")
            done = None
            if plan["favour"]:
                await asyncio.sleep(3)
                if not await self.quiet_moment():
                    return
                st["favour"] = plan["favour"]
                st["asked_at"] = self.clock()  # (asked as soon as she starts asking: you may answer right away)
                await self.speak_up(self.heart.favour_note(plan["favour"]), "curious", prio="reaction")
                done = await self.wait_favour(st)
                if done:
                    await self.bond_update(self.heart.thing_happened("favour"), "did her favour")
            else:
                await asyncio.sleep(max(2.0, plan["reveal"] - plan["sense"]))
            if not await self.quiet_moment():
                return
            offered = self.heart.offered_tools(self.abilities, ability)
            moment = self.heart.origin_moment("a power of yours just woke up", self.clock(), chance=0.5)
            note = self.heart.reveal_note(ability, request, done) + (moment or (
                " You may also wonder, briefly, what this says about what you are." if random.random() < 0.5 else ""))
            await self.speak_up(note, "excited", emote="hop", prio="reply",
                                tools_=tools.for_abilities(offered), force=ability)
        except Exception as e:  # a background thought must never take the brain down
            log.warning("awakening %s failed: %s", ability, e)
        finally:
            self.awakening.pop(ability, None)

    async def quiet_moment(self, tries=30):
        """Wait for a pause in the conversation (up to a minute); False if the player left."""
        for _ in range(tries):
            if not self.in_world or self.ws is None:
                return False
            if (not self.talk_lock.locked() and self.clock() - self.last_talk >= self.quiet_gap and not self.inbox
                    and self.clock() - self.player_talked >= (self.quiet_gap + 5 if self.quiet_gap else 0)):
                return True  # (not while you're talking or she owes you an answer)
            await asyncio.sleep(2)
        return self.in_world and self.ws is not None

    async def wait_favour(self, st, seconds=40.0, step=0.5):
        for _ in range(int(seconds / step)):
            if st["done"]:
                return True
            if st["favour"] == "still" and self.clock() - max(self.idle_since, st["asked_at"]) >= 4:
                return True
            await asyncio.sleep(step)
        return False

    def favour_done(self, kind):
        hit = False
        for st in self.awakening.values():
            if st["favour"] == kind and st["asked_at"] is not None and not st["done"]:
                st["done"] = hit = True
        return hit

    def favour_heard(self, text):
        """The player said her name, as she asked: a note so her answer fits."""
        if re.search(r"\b%s\b" % re.escape(self.cfg["name"].lower()), text.lower()) and self.favour_done("name"):
            return "They just said your name, as you asked: the strange feeling grows stronger. "
        return ""

    async def speak_up(self, instruction, mood, emote=None, tools_=None, force=None, prio="aside"):
        """Say something on her own (from the AI), with her current feelings."""
        async with self.talk_lock:
            self.mind.heart = self.heart.guidance(self.mood)
            self.offered = [force] if force else []
            text, m, gesture = await self.mind.initiative(self.snapshot, instruction, tools_,
                                                          self.run_tool if tools_ else None, force)
        self.last_talk = self.clock()
        log.info("on her own: %s", text)
        await self.say(text, m or mood, emote=gesture or emote,
                       style="whisper" if self.mind.last_whisper else None, prio=prio, source="own")
        self.last_talk = self.clock()

    # ------------------------------------------------------------------ talking

    async def say(self, text, mood, instant=False, emote=None, style=None, why="", prio=None, source=None):
        """Speak a line: subtitle at once, voice streamed sentence by sentence after it.

        One voice, coordinated (prio): "urgent" (danger) may interrupt anything; a higher priority cuts
        a lower one; her "reply" waits for the line she's saying to end; a short "reaction" ("Ow!")
        waits a moment or is dropped; an "aside" (a musing, a comment on an animal) is dropped when
        she's talking, you just spoke, or an answer is on its way. An answer cut by something urgent is
        finished afterwards ("Anyway, as I was saying..."), unless you spoke in between."""
        prio = prio or ("urgent" if why.startswith("a warning") else "reaction" if why else "reply")
        rank, now = PRIORITY[prio], self.clock()
        if self.player_listening and now - self.listening_since > 20:
            self.player_listening = False  # (the recording never came: don't stay quiet forever)
        left = self.speaking_until - now
        # from the moment you start talking until her answer: nothing of her own (asides and reactions
        # wait or are dropped; warnings still come)
        waiting = self.inbox or self.talk_lock.locked() or self.player_listening or self.transcribing
        if (rank == 0 and (waiting or now - self.player_talked < 6)) or (rank == 1 and waiting):
            log.info("not now (%s): %s", prio, text[:70])
            self.session.event("not_said", text=text, reason="you were talking or waiting for an answer", prio=prio)
            return None
        if left > 0.3:
            current = PRIORITY[self.speaking_prio]
            if rank == 3 or rank > current:
                self.cut_short(now)  # an answer it interrupts is finished later
            elif rank == 2 and self.speaking_to and self.speaking_to != "player":
                # an answer to a friend while she's talking: it goes to the chat at once (they read it), no voice
                self.line += 1
                self.session.event("pip", line=self.line, text=text, mood=mood, prio=prio, to=self.speaking_to,
                                   source=source or "reply", chat_only=True)
                await self.send({"type": "chat_line", "text": text, "to": self.speaking_to})
                return None
            elif rank == 2:
                # her answer waits a moment for the line she's saying (never 15 s: past 2.5 s, that line is cut and
                # finished later)
                if left <= 2.5:
                    self.last_wait = left
                    await asyncio.sleep(left)
                else:
                    self.last_wait = 0.0
                    self.cut_short(now)
            elif rank == 1 and left < 8:
                await asyncio.sleep(left)  # a reaction waits for her to finish the line
            else:
                log.info("not now (%s while saying %s): %s", prio, self.speaking_prio, text[:70])
                self.session.event("not_said", text=text, reason="she was already saying something", prio=prio)
                return None
        if why:  # a line said on instinct: in her own words (if written), and the AI hears it, with why
            text = self.instinct.personal(text)
            self.mind.note_said(text, mood, why)
        self.line += 1
        line = self.line
        self.session.event("pip", line=line, text=text, mood=mood, prio=prio, why=why, to=self.speaking_to or "player",
                           source=source or (
            "warning" if why.startswith("a warning") else "instinct" if why else "reply"))
        self.mood = mood or self.mood
        # a warning's fright passes quickly; a feeling from conversation lasts a bit longer
        self.mood_until = self.clock() + (8 if instant else 20)
        chunks = sentences(text, first_max=60) if self.cfg["voice"].get("enabled", True) else []
        style = style if style is not None else voice.style_for(mood, text)
        # what she's saying, for the coordinator: when it ends (refined as the audio comes), and its parts
        self.speaking_prio, self.speaking_chunks, self.speaking_started = prio, list(chunks), self.clock()
        self.speaking_until = self.clock() + (self.seconds_to_say(text) + 1.0 if chunks else 0)
        self.recent_said = [(t, x) for t, x in self.recent_said if self.clock() - t < 90] + [(self.clock(), text)]
        # the subtitle at once (you see her answer while her voice is being made), the voice right after
        msg = {"type": "say", "line": line, "text": text, "mood": self.mood, "audio": "", "more": bool(chunks)}
        if emote:
            msg["emote"] = emote
        await self.send(msg)
        for chunk in chunks:
            audio = await self._voice(chunk, style)
            if audio is None or line != self.line:
                return line
            if audio:
                await self.send({"type": "audio", "line": line, "audio": audio})
        return line

    async def say_more(self, line, text, style=None):
        """The next sentence of a line (her answer streaming in): the subtitle grows, the voice follows.
        If the line was interrupted meanwhile, it joins what she'll finish afterwards."""
        now = self.clock()
        if line != self.line:
            if self.unfinished:
                self.unfinished = (self.unfinished[0] + " " + text, self.unfinished[1])
            return
        chunks = sentences(text) if self.cfg["voice"].get("enabled", True) else []
        self.speaking_chunks += chunks
        self.speaking_until = max(self.speaking_until, now) + self.seconds_to_say(text)
        self.recent_said.append((now, text))
        await self.send({"type": "say_more", "line": line, "text": text})
        for chunk in chunks:
            audio = await self._voice(chunk, style)
            if audio is None or line != self.line:
                return
            if audio:
                await self.send({"type": "audio", "line": line, "audio": audio})

    def cut_short(self, now, by_player=False):
        """What she was saying gets interrupted: if it was an answer, remember what she didn't get to say
        (finished after the interruption, or, if you speak, told to the AI so she can come back to it)."""
        self.session.event("cut", by_player=by_player, was=self.speaking_prio,
                           rest=" ".join(self.speaking_chunks)[:160])
        if self.speaking_prio != "reply" or not self.speaking_chunks:
            return
        elapsed, done, i = now - self.speaking_started, 0.0, 0
        while i < len(self.speaking_chunks) and done + self.seconds_to_say(self.speaking_chunks[i]) <= elapsed:
            done += self.seconds_to_say(self.speaking_chunks[i])
            i += 1
        rest = self.speaking_chunks[i:]
        self.speaking_chunks = []
        if not rest:
            return
        if by_player:
            self.mind.remember("assistant", "(you were interrupted before finishing: %s)" % " ".join(rest))
            return
        self.unfinished = (" ".join(rest), now)
        if self.resume_task is None or self.resume_task.done():
            self.resume_task = asyncio.create_task(self.resume_unfinished())

    async def resume_unfinished(self):
        """After the interruption, she finishes what she was saying (unless you spoke meanwhile)."""
        await asyncio.sleep(0.5)
        while self.clock() < self.speaking_until:
            await asyncio.sleep(0.3)
        rest, when = self.unfinished or ("", 0)
        self.unfinished = None
        if not rest or self.player_talked > when or self.clock() - when > 25:
            if rest:
                self.mind.remember("assistant", "(you were interrupted before finishing: %s)" % rest)
            return
        await self.say(random.choice(["Anyway, as I was saying: ", "So, where was I? Oh yes: ", "As I was saying, "])
                       + rest[0].lower() + rest[1:], self.mood, prio="reply")

    async def _voice(self, text, style=""):
        spoken, hums = tunes.split(text)  # a hum isn't spoken: the game plays it as a little tune
        if hums:
            await self.send(tunes.tune_message(hums, self.mood))
        if not spoken:
            return ""  # (nothing to say aloud in this one: go on to the next sentence)
        try:
            return base64.b64encode(await voice.speak(self.cfg, spoken, style)).decode("ascii")
        except voice.VoiceError as e:
            log.warning("%s (subtitle only)", e)
            return None

    # ------------------------------------------------------------------ System 0's words (written by System 2)

    async def load_lines(self):
        me = (await self.safe(self.memory.store.call("doc", key="world:%s:self" % self.memory.world_id)) or {}).get("value")
        self.mind.becoming = (me or {}).get("text", "")  # who she's become lately (System 2's portrait)
        key = "world:%s:lines" % self.memory.world_id
        doc = (await self.safe(self.memory.store.call("doc", key=key)) or {}).get("value")
        self.instinct.load(doc)
        self.alerts.pools = self.instinct.lines
        if (not self.instinct.lines or (doc or {}).get("v") != instinct_mod.VERSION
                or self.instinct.level != "%s, %s" % (self.heart.level(), self.heart.stance())):
            after = self.cfg["behaviour"].get("instinct_lines_after", 45)
            if after:
                asyncio.create_task(self.write_lines(after=after))

    async def write_lines(self, after=0):
        """The thinking AI writes her instinct lines in her own voice (in the background, a few seconds),
        after a quiet while once you've joined, so it never competes with her greeting or first answers."""
        self.lines_written_at = self.clock()
        if after:
            await asyncio.sleep(after)
            if not self.ws:
                return
        try:
            who = await self.memory.context(self.snapshot, "who am I, what do I love")
            mine = "\n".join(l for l in who.splitlines() if l.startswith(
                ("About yourself", "Where you come from", "Your tastes", "Moments that shaped you")))
            name = player_name(who)
            level = "%s, %s" % (self.heart.level(), self.heart.stance())
            body = {"model": self.cfg["ai"]["model"], "temperature": 0.9, "max_tokens": 2200,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": instinct_mod.prompt(self.cfg["name"], mine, level, name)}]}
            raw = await asyncio.to_thread(post_json, self.mind.url(), body, self.cfg["gateway"].get("key", ""), 120,
                                          "reflect")
            lines = instinct_mod.parse(raw["choices"][0]["message"].get("content"))
            if len(lines) < len(instinct_mod.MOMENTS) // 2:
                log.info("her instinct lines weren't usable this time (%d moments)", len(lines))
                return
            doc = {"lines": lines, "level": level, "time": time.time(), "v": instinct_mod.VERSION}
            await self.safe(self.memory.store.call("doc", key="world:%s:lines" % self.memory.world_id, value=doc))
            self.instinct.load(doc)
            self.alerts.pools = self.instinct.lines
            log.info("her instinct lines, in her own voice: %d moments (%s)", len(lines), level)
            await self.write_becoming()
        except Exception as e:  # (the built-in lines stay)
            log.warning("couldn't write her instinct lines: %s", e)

    async def write_becoming(self):
        """System 2 rewrites who she's become lately (her quick AI reads it with every answer)."""
        self.becoming_at = self.clock()
        try:
            key = "world:%s:self" % self.memory.world_id
            doc = (await self.safe(self.memory.store.call("doc", key=key)) or {}).get("value") or {}
            who = await self.memory.context(self.snapshot, "who am I lately, what do I love, who is the player")
            mine = "\n".join(l for l in who.splitlines() if l.startswith(
                ("About yourself", "Where you come from", "Your tastes", "Moments that shaped you", "About the player",
                 "You and the player go back")))
            recent = "\n".join(filter(None, [self.mind.summary] + [
                ("Player: " if m["role"] == "user" else "You: ") + m["content"][:200] for m in self.mind.history[-10:]]))
            level = self.heart.level()
            body = {"model": self.cfg["ai"]["model"], "temperature": 0.9, "max_tokens": 500,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": becoming_mod.prompt(
                        self.cfg["name"], mine, recent, doc.get("text", ""), level)}]}
            raw = await asyncio.to_thread(post_json, self.mind.url(), body, self.cfg["gateway"].get("key", ""), 120,
                                          "reflect")
            text = becoming_mod.parse(raw["choices"][0]["message"].get("content"))
            if not text:
                log.info("her portrait wasn't usable this time")
                return
            await self.safe(self.memory.store.call("doc", key=key, value=becoming_mod.keep(doc, text, level, time.time())))
            self.mind.becoming = text
            self.session.event("becoming", text=text[:400])
            log.info("who she's become lately: %s", text)
        except Exception as e:  # (she stays who she was)
            log.warning("couldn't write who she's become: %s", e)

    async def fill_silence(self, speech, after=1.4):
        """System 0 covers System 1: when an answer takes a while, she shows she's thinking (a gesture,
        looking up), without a word: a spoken "hmm" every time was annoying (at most every 20 s)."""
        await asyncio.sleep(after)
        danger = any(m.get("distance", 99) < 10 for m in (self.snapshot or {}).get("hostiles") or [])
        if speech.said or danger or self.clock() - self.last_filler < 20:
            return
        self.last_filler = self.clock()
        await self.send({"type": "act", "emote": "think"})
        await self.send({"type": "state", "state": "thinking"})

    async def warm_up(self):
        """Ready before the first message: System 0's example phrases (a third of a second, once)."""
        try:
            await asyncio.to_thread(self.understand._ready)
        except Exception as e:  # (no embeddings: only the rules understand requests)
            log.info("understanding not warmed up: %s", e)

    def hear_player(self, text, spoken=False):
        self.session.event("you", text=(text or "").strip(), spoken=spoken)
        """Messages wait in an inbox while she's thinking; when she's free she answers all of them at once
        (so ten messages in a row get one answer, not ten answers trickling in for a minute)."""
        text = (text or "").strip()
        if not text:
            return
        self.player_talked, self.player_listening = self.clock(), False  # (pressing V already stopped her)
        self.inbox.append((text, spoken))
        if self.inbox_task is None or self.inbox_task.done():
            self.inbox_task = asyncio.create_task(self.drain_inbox())

    async def drain_inbox(self):
        while self.inbox:
            batch, self.inbox = self.inbox, []
            await self.answer(merge_messages([t for t, _ in batch]), any(s for _, s in batch),
                              heard=[t for t, _ in batch])

    async def answer_on_instinct(self, text, kind, heard=None):
        """Talker first (talker.py): "follow me", "stand still", "come here" alone. Her body already did it;
        she answers on instinct, at once, and the AI hears the exchange in the conversation afterwards."""
        started = self.clock()
        async with self.talk_lock:  # (in turn with her other answers: a line never jumps a queue)
            self.last_player_text = self.asking_text = text
            self.recent_player = (self.recent_player + [text])[-3:]
            for said in heard or [text]:  # (the same words again and again still mean less each time)
                self.heart.hear(said)
            line = self.instinct.pick(kind + "_ok") or random.choice(talker.LINES[kind + "_ok"])
            self.mind.remember("user", text)
            self.mind.remember("assistant", "[%s] %s" % (self.mood or "happy", line))
            self.session.event("decide", who="player", acts=[kind], force=None, force_by="instinct (plain command)")
            await self.say(line, self.mood or "happy", prio="reply", source="instinct")
            self.session.event("answer", who="player", first_words=round(self.clock() - started, 2),
                               total=round(self.clock() - started, 2), rounds=0, calls=None, by="instinct")
            await self.safe(self.memory.keep_history(self.mind.history, self.mind.summary))
            self.last_talk = self.clock()

    async def answer(self, text, spoken=False, heard=None):
        text = (text or "").strip()
        if not text:
            return
        self.last_talk = self.clock()
        acts, done = intents.match(text)
        for act in acts:  # the body reacts at once; the words follow
            if act.get("perform"):
                asyncio.create_task(self.perform())
                continue
            if act.get("stop_all"):  # builds, leading, a show: all of it stops, really
                asyncio.create_task(self.request("build", {"shape": "stop"}))
                await self.send({"type": "act", "move": "stop"})
                continue
            await self.send(dict(act, type="act"))
        moving = next((a["move"] for a in acts if a.get("move") in ("follow", "stay", "come")), None)
        vouched = intents.vouches_for(text, [p.get("name", "") for p in (self.snapshot or {}).get("players") or []],
                                      self.heart.friend_names())
        if vouched:  # "from now on do what Dumber says": she takes their requests too
            name, yes = vouched
            self.heart.trust_friend(name, yes)
            done.append(("from now on, do what %s asks of you too" if yes else "stop taking orders from %s") % name)
            await self.heart.save()
        if acts:
            log.info("acting on: %s", "; ".join(done))
        if intents.PUT_BACK.search(text):  # "put my block back": undo a prank
            res = await self.request("return_block", {})
            log.info("put the block back: %s", res)
            done.append("put the block you borrowed back where it was" if res.get("ok") else
                        "tried to put a block back, but: %s" % res.get("error", "nothing to put back"))
        plain = talker.plain_command(text, moving) if self.cfg["behaviour"].get("talker_first", True) else None
        if plain and not vouched and not self.heart.angry() and not intents.PUT_BACK.search(text):
            await self.answer_on_instinct(text, plain, heard)  # talker first: no AI for a plain command
            return
        await self.send({"type": "state", "state": "thinking"})
        async with self.talk_lock:
            try:
                self.last_player_text = self.asking_text = text
                force = None
                offer = self.heart.take_offer(self.clock()) if intents.YES.match(text) else None
                if offer and offer["what"] in self.abilities:
                    force = offer["what"]  # "yes" to "want me to push them away?"
                elif intents.YES.match(text) and self.her_offer and self.clock() - self.her_offer[1] < 60:
                    force = self.her_offer[0]  # "yes please" to "should I light it up for you?"
                self.her_offer = None
                talk_tools = ["set_reminder", "name_place", "remember", "standing_request"]
                others = [p.get("name", "") for p in self.snapshot.get("players") or []]
                about_tool, about = intents.player_hint(text, others, self.abilities)
                force_by = "her offer" if force else None
                force = force or about_tool  # "find robin", "stay with robin"
                force_by = force_by or ("a friend's name" if force else None)
                force = force or intents.action_hint(text, self.abilities + talk_tools) \
                    or intents.hint_in_context(text, self.recent_player, self.abilities)
                force_by = force_by or ("rules" if force else None)
                if not force and len(text) < 160:  # System 0: what you mean, whatever words you use
                    force = await asyncio.to_thread(self.understand.hint, text, self.abilities + talk_tools)
                    if force:
                        force_by = "meaning"
                        log.info("understood as %s: %s", force, text)
                if moving and force in ("guide", "find_player", "follow_player") and not about \
                        and not intents.LEADING.search(text):
                    force = None  # "follow me" / "stand still" is her body's job, done already: never a trip
                wanted = intents.action_hint(text, list(tools.ABILITY_TOOLS))
                if wanted and wanted not in self.abilities and self.clock() - self.tipped.get(wanted, -1e9) > 600:
                    self.tipped[wanted] = self.clock()  # her power or style doesn't allow it: a hint for you
                    await self.tip_for(wanted)
                self.recent_player = (self.recent_player + [text])[-3:]
                asked = force
                if self.heart.angry() and force:
                    force = None  # when she's cross, whether to help is her choice (but never "I can't")
                    note_cross = ("They ask you to %s, and you can. You're cross with them: whether you do it is "
                                  "your choice. If you won't, say you don't want to, never that you can't."
                                  % asked.replace("_", " "))
                else:
                    note_cross = ""
                self.heart.known_self = getattr(self.memory, "self_known", 0)
                for said in heard or [text]:  # (repeating the same words: less effect, then annoyance)
                    self.heart.hear(said)
                someone = ("They mean %s, another player here (for gifts, effects or protection, set 'to' to %s). %s"
                           % (about, about, self.heart.friends.guidance(about))) if about else ""
                if intents.DEFEND.search(text) and self.heart.friends.watching():
                    stood = self.heart.stood_up_for_her()  # they stood up for her: it counts (and she noticed)
                    await self.bond_update(stood, "you stood up for her")
                    someone += " The player just stood up for you against a friend who was mean to you: you noticed, it warms you."
                note = " ".join(x.strip() for x in (self.favour_heard(text), note_cross, self.power_news, someone)
                                if x.strip())
                note += " " if note else ""
                self.power_news = ""
                if force == "find_animal" and self.animal_named(text):
                    force = None  # it's right there in view: she just says where, no searching needed
                if force and self.heart.slow(force):
                    # think fast: answer now ("I'll try!"); think slow: the power wakes up in the background
                    if force in self.awakening:
                        note += ("You're still trying to %s; it isn't there yet. Say so in your own way, without "
                                 "pretending." % intents_heart.POWER_NAMES[force])
                    else:
                        note += self.heart.first_reply_note(force)
                        self.start_awakening(force, text)
                    force = None
                said_pronouns = intents.pronouns_said(text)
                if said_pronouns:  # "I am a him, not a her": kept for good, replacing any guess
                    name = player_name(self.mind.recalled or "") or (self.snapshot or {}).get("playerName") or "The player"
                    await self.safe(self.memory.remember("%s's pronouns are %s (they said so)." % (name, said_pronouns),
                                                         "player", 9))
                    note += " They just told you their pronouns: %s. Use them from now on; a short, simple 'got it'." \
                        % said_pronouns
                if intents.DIARY.search(text):  # her real diary, so she never makes one up
                    entries = await self.safe(self.memory.diary(3)) or []
                    note += (" Your diary, newest first (retell or quote it, in your voice; don't invent other entries): "
                             + " | ".join(entries)) if entries else " Your diary is still empty: say so, simply."
                note += await self.world_answer(text)  # how the world works: what it remembers, or listen
                offered = self.heart.offered_tools(self.abilities, force or (asked if note_cross else None))
                if force and force in intents.FAMILY:  # a clear request: its powers only (no healing, food or torches
                    keep = intents.FAMILY[force]       # nobody asked for: 14 times in one evening)
                    offered = [a for a in offered if a in keep or a not in tools.ABILITY_TOOLS]
                if (moving or vouched) and not intents.LEADING.search(text) and not about:
                    # (the AI can't turn "follow me" into leading either; "do what Robin says" isn't "go to Robin")
                    offered = [a for a in offered if a not in ("guide", "follow_player")]
                if force and force in tools.ABILITY_TOOLS and force not in offered:
                    # a required tool must be among those offered (Gemini refuses the call otherwise: HTTP 400)
                    if about and force in self.abilities:
                        offered.append(force)
                    else:
                        force = None
                self.offered = offered
                fib = "" if force or (self.snapshot.get("hostiles") or []) else self.heart.fib(self.clock())
                self.mind.allow_fib = bool(fib)
                note += fib
                self.mind.heart = "\n".join(x for x in (self.heart.guidance(self.mood),
                                                       self.heart.discovery_note(self.abilities), note) if x)
                self.session.event("decide", who="player", acts=done or None, force=asked, force_by=force_by,
                                   offered=offered, cross=bool(note_cross) or None, about=about or None)
                marker = mind_mod.call_marker()
                speech = SpokenStream(self)  # her answer, spoken sentence by sentence as it's written
                filler = (asyncio.create_task(self.fill_silence(speech, self.cfg["behaviour"]["fill_silence_after"]))
                          if self.cfg["behaviour"].get("fill_silence_after") else None)
                try:
                    reply, mood, gesture = await self.mind.reply(self.snapshot, text, done,
                                                                 tools.for_abilities(offered), self.run_tool, force,
                                                                 spoken, on_sentence=speech.add)
                finally:
                    if filler:
                        filler.cancel()
                await speech.close()
                self.session.event("answer", who="player", first_words=round((speech.first_at or self.clock()) - speech.started, 2),
                                   total=round(self.clock() - speech.started, 2), rounds=self.mind.last_rounds,
                                   calls=mind_mod.calls_since(marker) or None, waited=round(self.last_wait, 2) or None)
                vt, self.voice_timing = self.voice_timing, None
                if vt and speech.first_at:  # from releasing the talk key: to the text, to her first word
                    first = time.time() - (self.clock() - speech.first_at)
                    self.session.event("timing", trip=round(vt["trip"], 2) if vt["trip"] is not None else None,
                                       stt=round(vt["stt"], 2), to_text=round(vt["text_at"] - vt["released"], 2),
                                       to_first_word=round(first - vt["released"], 2), waited=round(self.last_wait, 2))
            except AIError as e:
                log.error("AI error: %s", e)
                self.session.event("error", text=str(e)[:200])
                await self.send({"type": "notice", "text": "AI gateway problem: %s" % str(e)[:120]})
                await self.say(random.choice(["Hm... my thoughts went all foggy. Say that again?",
                                              "Wait, I lost it. What did you say?",
                                              "Ugh, my head's all cloudy. One more time?"]), "calm",
                               why="your thoughts went foggy for a moment (the thinking failed); the player sees a "
                                   "notice about it", prio="reply")  # (it is her answer: not held like her own lines)
                return
            log.info("you: %s | %s: [%s]%s %s", text, self.cfg["name"], mood, " {%s}" % gesture if gesture else "", reply)
            self.memory.exchanges += 1
            self.memory.since_reflection += 1
            await self.safe(self.memory.keep_history(self.mind.history, self.mind.summary))
            asyncio.create_task(self.fold())
            await self.safe(self.memory.episode("The player said: %s | I said: %s" % (text, reply), 3))
            if self.memory.since_reflection >= 8:  # learn as we go, not only at the end
                asyncio.create_task(self.reflect())
            self.mind.world_knowledge = ""  # (only for the question it answered)
            hint = intents.offered_in(reply, self.abilities)
            self.her_offer = (hint, self.clock()) if hint else None
            if not speech.said:  # (nothing came as a stream: the whole answer, as before)
                await self.say(reply, mood or "happy", emote=gesture,
                               style="whisper" if self.mind.last_whisper else None)
            self.last_talk = self.clock()
        # how they treated her changes the bond (and, when it's really bad, she leaves for a while)
        regard = self.mind.last_regard
        gesture = self.heart.rel.s.get("gesture")
        if gesture and not gesture.get("said"):
            gesture["said"] = True  # (she had the chance to ask once; she won't keep asking)
        await self.bond_update(self.heart.on_regard(regard, text), regard)
        await self.heart_news()
        if regard == "mean" and self.heart.bond < 25:
            await self.mood_weather(sad=True)
        elif regard == "sorry" and not self.heart.angry():
            await self.mood_weather(sad=False)
        if regard == "mean" and self.heart.bond < 12 and self.heart.p.get("can_vanish", True):
            await self.vanish(120, random.choice(intents_heart.VANISH_LINES))

    GUEST_TOOLS = ("give_item", "give_effect", "command", "build", "harvest", "place_torch", "protect", "find_ore", "find_animal", "find_block", "find_player",
                   "locate", "guide", "stop_guide", "set_time", "set_weather")

    async def answer_guest(self, who, text, powers=False):
        """A friend on your LAN world (without the mod) called her in chat: she answers them, in chat for
        them (the mod sends her lines there) and aloud for you. Talk only: she doesn't use her powers for
        them, and nothing they say moves her heart: the bond is between her and you."""
        text, who = (text or "").strip(), re.sub(r"[^\w .-]", "", who or "")[:24] or "a friend"
        if not text:
            return
        self.session.event("guest", who=who, text=text)
        host = (self.snapshot or {}).get("playerName", "")
        trusted = self.heart.trusts_friend(who)
        acts = intents.match(text)[0] if trusted else []
        moved = any(a.get("move") in ("follow", "stay", "come") for a in acts)
        for act in acts:  # a friend the player vouched for: "follow me", "stay here" work for them too
            if act.get("move") == "follow":
                res = await self.request("follow_player", {"name": who})
                self.session.event("tool", name="follow_player", args=json.dumps({"name": who}), ok=bool(res.get("ok")),
                                   result=json.dumps(res)[:160], who=who)
            elif act.get("move") in ("stay", "come") or act.get("emote"):
                await self.send(dict(act, type="act"))
        # what a friend says while she's busy waits, and their messages are answered together (one AI call)
        self.guest_pending.setdefault(who, []).append(text)
        await self.send({"type": "state", "state": "thinking"})
        async with self.talk_lock:
            self.asking_text = text  # (the guards read the words of whoever is asking: here the friend)
            waiting = self.guest_pending.pop(who, [])
            if not waiting:
                return  # (answered together with their earlier message)
            text = waiting[0] if len(waiting) == 1 else " / ".join(waiting)
            self.speaking_to = who
            try:
                self.mind.heart = "\n".join(x for x in (self.heart.guidance(self.mood), self.heart.friends.guidance(who), (
                    "%s is a friend of the player's, here in the world with you. They can't hear your voice: they "
                    "read your words in chat. Be yourself with them; your bond is with the player%s, not with %s. %s"
                    % (who, (" (%s)" % host) if host else "", who, (
                        "The player told you to do what %s asks: if %s asks you to follow them or stay, do it." % (who, who)
                        if trusted else
                        "You float beside the player you live with: if %s asks you to stay with them or follow them, "
                        "that's the player's call (they can ask you); say so kindly, and don't go looking for %s."
                        % (who, who))))) if x)
                offered = [a for a in self.abilities if a in self.GUEST_TOOLS] if powers else []
                if moved:  # a trusted friend's "follow me": done already, and never a trip for the player
                    offered = [a for a in offered if a not in ("guide", "follow_player", "stop_guide")]
                if not offered:
                    self.mind.heart += ("\nWith %s you only talk: your powers are for the player alone right now. If "
                                        "they ask for something, say so kindly; never pretend to do it." % who)
                force = intents.action_hint(text, offered)
                if not force:
                    force = intents.player_hint(text, [p.get("name", "") for p in self.snapshot.get("players") or []],
                                                offered)[0]
                if not force and "find_player" in offered and intents.WHERE_AM_I.search(text):
                    force = "find_player"  # (where they are, seen from the player: the world's game knows)
                both = bool(intents.BOTH.search(text)) and host

                self.offered = offered  # (what she may do for them: not the list from your last answer)
                self.session.event("decide", who=who, acts=[json.dumps(a) for a in acts] or None, force=force,
                                   offered=offered, trusted=trusted or None, merged=len(waiting) if len(waiting) > 1 else None)
                marker = mind_mod.call_marker()

                async def for_them(name, args):  # (gifts, effects and protection go to them, not to the player)
                    if name in ("give_item", "give_effect", "protect") and not (args or {}).get("to"):
                        if both:  # "for both of us": one for them, one for the player
                            first = await self.run_tool(name, dict(args or {}, to=who))
                            second = await self.run_tool(name, dict(args or {}, to=host))
                            return {"ok": bool(first.get("ok") or second.get("ok")), who: first, host: second}
                        args = dict(args or {}, to=who)
                    if name in ("build", "command", "harvest", "place_torch") and not (args or {}).get("for"):
                        args = dict(args or {}, **{"for": who})  # (from where they stand, with their inventory)
                    if name == "find_player":  # (where someone is, from where they stand)
                        args = dict(args or {}, **{"from": who})
                        if str(args.get("name", "")).lower() in ("", "me", "myself", "i"):
                            args["name"] = who
                    return await self.run_tool(name, args)
                speech = SpokenStream(self)
                reply, mood, gesture = await self.mind.reply(
                    self.snapshot, "(%s, another player here, not the player you live beside, says to you in chat:) %s"
                    % (who, text), (), [tools.ABILITY_TOOLS[a] for a in offered if a in tools.ABILITY_TOOLS], for_them, force,
                    False, on_sentence=speech.add)
                await speech.close()
                self.session.event("answer", who=who, first_words=round((speech.first_at or self.clock()) - speech.started, 2),
                                   total=round(self.clock() - speech.started, 2), rounds=self.mind.last_rounds,
                                   calls=mind_mod.calls_since(marker) or None)
            except AIError as e:
                log.error("AI error answering %s: %s", who, e)
                self.session.event("error", text=str(e)[:200])
                await self.send({"type": "state", "state": "idle"})
                self.speaking_to = None
                return
            log.info("%s: %s | %s: [%s] %s", who, text, self.cfg["name"], mood, reply)
            change = self.heart.friend_regard(who, self.mind.last_regard, text,  # her heart for THEM, not for you
                                              witnessed=self.near_player(who, 48))
            if change:
                self.session.event("heart", who=who, why=self.mind.last_regard, change=round(
                    sum(v for k, v in change.items() if k in ("a", "t")), 1), stance=self.heart.friends.bonds(who).stance(
                    self.clock()), detail="feelings for %s: %s" % (who, json.dumps(change)))
                await self.heart.save()
            await self.safe(self.memory.episode("%s (a friend of the player's) said: %s | I said: %s" % (who, text, reply), 2))
            if not speech.said:
                await self.say(reply, mood or "happy", emote=gesture)
            self.speaking_to = None
            self.last_talk = self.clock()

    async def on_voice(self, msg):
        self.transcribing = True  # (still your turn: she holds her own lines until she answers)
        try:
            await self._on_voice(msg)
        finally:
            self.transcribing = False

    async def _on_voice(self, msg):
        self.player_listening = False
        await self.send({"type": "state", "state": "thinking"})
        arrived = time.time()
        trip = max(0.0, arrived - msg["releasedAt"] / 1000) if msg.get("releasedAt") else None
        try:
            wav = base64.b64decode(msg.get("wav", ""))
            t0 = time.time()
            people = self.people_names()
            raw = await voice.transcribe(self.cfg, wav, prompt=intents.stt_prompt(self.cfg["name"], people))
            stt = time.time() - t0
            text = intents.fix_names(raw, self.cfg["name"], people)
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
        mine = without_her_words(text, [t for w, t in self.recent_said if self.clock() - w < 90])
        self.session.event("heard", raw=raw, fixed=text if text != raw else None, kept=mine if mine != text else None,
                           stt=round(stt, 2),
                           trip=round(trip, 2) if trip is not None else None, relay=bool(msg.get("relay")) or None)
        if not msg.get("relay"):
            self.voice_timing = {"released": arrived - (trip or 0.0), "trip": trip, "stt": stt, "text_at": time.time()}
        if mine != text:  # her own voice reached your microphone: only your words count
            log.info("removed her own words from what was heard: %r -> %r", text, mine)
        if not mine:
            await self.send({"type": "state", "state": "idle"})
            return
        if msg.get("relay"):  # light mode: words for the host's Pip, sent on in chat by the game
            await self.send({"type": "heard", "text": mine, "relay": True})
            await self.send({"type": "state", "state": "idle"})
            return
        await self.send({"type": "heard", "text": mine})
        self.hear_player(mine, spoken=True)

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
                welcome = await self.safe(self.memory.welcome(self.since)) or "Say hello the way you would, in one short line."
                due = await self.safe(self.memory.due("session")) or []
                if due:
                    welcome += " Also remind them: " + "; ".join(r["text"] for r in due) + "."
                text, mood, gesture = await self.mind.initiative(self.snapshot, welcome)
            except AIError as e:
                log.error("AI error while greeting: %s", e)
                await self.send({"type": "notice", "text": "AI gateway problem: %s" % str(e)[:120]})
                return
        self.last_talk = self.clock()
        await self.say(text, mood or "happy", emote=gesture, source="own")

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
                instruction = self.heart.musing()
                if not instruction:
                    continue  # she's upset: she keeps to herself
                self.mind.heart = self.heart.guidance(self.mood)
                try:
                    text, mood, gesture = await self.mind.initiative(self.snapshot, instruction + " Don't repeat yourself.")
                except AIError as e:
                    log.error("AI error during small talk: %s", e)
                    continue
            await self.say(text, mood or "happy", emote=gesture, prio="aside", source="own")


async def run(cfg, token):
    brain = Brain(cfg, token)
    host, port = cfg["server"].get("host", "127.0.0.1"), int(cfg["server"]["port"])
    async with serve(brain.handler, host, port, process_request=brain.check_auth, max_size=MAX_MESSAGE,
                     ping_interval=20, ping_timeout=20):
        log.info("%s's brain is listening on ws://%s:%d (gateway: %s, model %s)", cfg["name"], host, port,
                 cfg["gateway"]["url"], cfg["ai"]["model"] or "the gateway's")
        await asyncio.gather(brain.small_talk_loop(), brain.reminder_loop(), brain.heart_loop(), brain.state_loop())
