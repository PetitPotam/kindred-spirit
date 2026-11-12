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
from . import heart as intents_heart
from .describe import describe
from . import knowledge as kb
from .heart import Heart
from .memory import GatewayMemory, Memory
from .alerts import Alerts
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


def did_something(name, result):
    """Whether a power really showed itself: stopping isn't a power, pushing nothing away or finding
    nothing doesn't reveal anything."""
    if name == "stop_guide":
        return False
    if name == "protect":
        return bool(result.get("pushedAway"))
    if name == "harvest":
        return bool(result.get("broken"))
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


IMPORTED_KINDS = ("player", "self", "habit", "origin", "taste", "core")  # what an import brings: who you are, who she is, your habits

# moments worth waiting for a pause in the conversation, rather than skipping
WORTH_WAITING = ("baby", "tamed", "first_meet", "killed_villager", "kill_spree", "death", "advancement", "lore_place")


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
        self.memory.per_world = not cfg["heart"].get("same_companion_in_every_world", False)
        if hasattr(self.memory.store, "strict"):
            self.memory.store.strict = self.memory.per_world
        self.heart = Heart(cfg, self.memory)
        self.heart_loaded = False   # which heart is loaded (its key), or False
        self.last_notice = -1e9
        self.noticed = {}
        self.prev_biome = None
        self.prev_health = None
        self.last_protect = -1e9
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
        self.kb = kb.Knowledge(cfg)  # what the world remembers (services/knowledge)
        self.listening = set()       # questions she's listening to the world about right now
        self.reading = None          # the guide she was last told about (listen_more goes on from there)
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
            self.hear_player(msg.get("text", ""))
        elif kind == "voice":
            asyncio.create_task(self.on_voice(msg))
        elif kind == "admin":  # /kindred memory, /kindred reset, /kindred persona ... (answered in chat)
            asyncio.create_task(self.admin(msg.get("command", ""), msg.get("text", "")))

    def set_abilities(self, msg):
        self.abilities = list(msg.get("abilities") or [])
        self.singleplayer = bool(msg.get("singleplayer"))
        # (said in her world's words: these are limits of what she is, never "settings" to talk about)
        known = ", ".join(a.replace("_", " ") for a in self.abilities) if not self.heart.amnesia() else \
            "you don't know yet: you find out by trying when the player asks"
        self.mind.powers = "%s%s What you can do: %s.%s" % (
            {"advisor": "You can only look, sense and lead the way; you can't touch or change anything.",
             "helper": "You can help with your hands when asked, but nothing too big.",
             "allpowerful": "Your power is great: even the sun and the sky listen to you."}.get(msg.get("power"), ""),
            " You can only use what really exists (the player's own torches): you can't make things appear out of "
            "nothing." if msg.get("style") == "grounded" else " Your magic can make things appear.",
            known, "" if self.singleplayer else " Here your magic can't change the world itself.")
        if msg.get("glow") and self.singleplayer:
            self.mind.powers += " You glow softly: in the dark your light shows the way around you."
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
                self.heart.add_request(what, args.get("detail", ""))
                await self.heart.save()
                return {"ok": True, "willDoItEveryTime": what}
        except MemoryError as e:
            return {"ok": False, "error": str(e)}
        if name not in self.abilities:
            await self.tip_for(name)
            return {"ok": False, "error": "That's beyond what you can do."}
        if self.offered is not None and name not in self.offered:
            # (amnesia) a power she hasn't discovered: the AI knows the name, she doesn't
            return {"ok": False, "error": "You don't know how to do that yet."}
        if name == "guide":
            args = await self.guide_target(args)
        result = await self.request(name, args)
        m = re.search(r"\(?(?:The player can switch with )?(/kindred [a-z ]+?)\.?\)", result.get("error") or "")
        if m:  # the way to unlock it is for the player, as a hint in chat: never in her mouth
            await self.send({"type": "notice", "text": "Tip: %s lets %s do this" % (m.group(1), self.cfg["name"])})
            result["error"] = result["error"].replace(m.group(0), "").strip()
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
        need = {"give_item": "/kindred style magic", "set_time": "/kindred power allpowerful",
                "set_weather": "/kindred power allpowerful", "protect": "/kindred power helper",
                "place_torch": "/kindred power helper"}.get(ability)
        if need:
            await self.send({"type": "notice", "text": "Tip: %s lets %s do this" % (need, self.cfg["name"])})

    async def bond_update(self, delta, why=""):
        if abs(delta) < 0.5:
            return
        log.info("bond %+.1f (%s) -> %.0f %s", delta, why, self.heart.bond, self.heart.level())
        level = self.heart.level()
        if level in ("close", "best friend") and level not in self.heart.state.setdefault("levels_reached", []):
            self.heart.state["levels_reached"].append(level)  # a milestone: it may reveal a piece of her story
            moment = self.heart.origin_moment("you and the player just became %s" % (
                "close" if level == "close" else "best friends"), self.clock())
            if moment:
                asyncio.create_task(self.speak_up("You feel how much closer you've grown to the player." + moment,
                                                  "happy"))
        await self.send({"type": "bond", "value": round(self.heart.bond), "level": self.heart.level(),
                         "change": round(delta, 1)})
        await self.send({"type": "act", "closeness": self.heart.closeness()})
        await self.heart.save()

    async def vanish(self, seconds, line):
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
        waits = 30 if event in WORTH_WAITING else 0
        gap = 12 if event in WORTH_WAITING else 30
        while (self.talk_lock.locked() or self.clock() - self.last_notice < gap) and waits > 0:
            waits -= 1
            await asyncio.sleep(2)
        now = self.clock()
        if not self.in_world or self.ws is None or self.talk_lock.locked() or now - self.last_notice < gap:
            return
        if now - self.noticed.get(event, -1e9) < (600 if event in ("mining", "building") else 0):
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
        await self.say(text, mood or "curious", emote=gesture)

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
                    "(see What the world remembers). Come back and tell them, delighted, as what the stones or the wind "
                    "told you, in your own words and simply; only what it says, the key steps." % question, "excited",
                    emote="hop")
            else:
                await self.speak_up("You listened to your world about \"%s\", but it stayed quiet. Say so in one "
                                    "short sentence, in your world's words (the stones are quiet about that one), "
                                    "maybe you'll figure it out together." % question, "curious")
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
        theirs = (await m.store.call("doc", key="world:%s:heart" % src)).get("value") or {}
        extra = ""
        if theirs:  # the brain holds this world's heart, so it can take hers in right now
            st = self.heart.state
            st["bond"] = max(st["bond"], theirs.get("bond", 0))
            st["discovered"] = sorted(set(st.get("discovered", [])) | set(theirs.get("discovered", [])))
            for k, v in (theirs.get("asked") or {}).items():
                st.setdefault("asked", {})[k] = max(st["asked"].get(k, 0), v)
            await self.heart.save()
            await self.bond_update(0.6, "imported")  # (shows the heart meter)
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
                      "species_met": h.state.get("seen_species", []), "amnesia": h.amnesia()},
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
        while True:
            try:
                with open(path + ".tmp", "w", encoding="utf-8") as fh:
                    json.dump(self.state(), fh, ensure_ascii=False, default=str)
                os.replace(path + ".tmp", path)
            except Exception as e:  # the dashboard is a bonus: never a reason to stop
                log.debug("state not written: %s", e)
            await asyncio.sleep(every)

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
        return {}  # the mod then uses the last thing found or located

    def animal_named(self, text):
        """The nearest animal in view whose kind the text names ("sheeps" counts as sheep)."""
        words = set(re.findall(r"[a-z]+", text.lower()))
        words |= {w[:-1] for w in words if w.endswith("s")} | {w[:-2] for w in words if w.endswith("es")}
        seen = [a for a in self.snapshot.get("animals") or []
                if a.get("type", "").replace("minecraft:", "").replace("_", " ").split()[-1] in words]
        return min(seen, key=lambda a: a.get("distance", 99)) if seen else None

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
            lessons = await self.mind.reflect(transcript, known, diary=session_end and talk >= 2,
                                              bond=self.heart.level())
            added = await self.memory.learn(lessons)
            found = len(lessons.get("origin") or [])
            if found:  # a piece of where she comes from: it settles her doubts a little
                self.heart.shaken(-0.3 * found)
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
            await self.send({"type": "bond", "value": round(self.heart.bond), "level": self.heart.level(), "change": 0})
            await self.send({"type": "act", "closeness": self.heart.closeness()})
            if self.cfg["behaviour"].get("greet_on_join") and (self.greet_task is None or self.greet_task.done()):
                self.greet_task = asyncio.create_task(self.greet())
        elif name == "leave":
            if self.in_world:
                asyncio.create_task(self.end_session())
            self.in_world = False
            self.snapshot = {}
        elif name == "wrong_way":  # you walked off while she leads: she calls you back
            asyncio.create_task(self.say(random.choice(intents.WRONG_WAY_LINES), "excited", instant=True, emote="hop",
                                         why="the player walked away from where you're leading them"))
        elif name == "arrived":
            asyncio.create_task(self.say(random.choice(intents.ARRIVED_LINES), "excited", instant=True,
                                         why="you arrived where you were leading the player"))
            await self.safe(self.memory.episode("We arrived where I was leading the player.", 4))
        elif name == "hit":
            delta, line, vanish, back = self.heart.on_hit()
            await self.bond_update(delta, "hit")
            if vanish:
                asyncio.create_task(self.vanish(vanish, line))
            elif back == "bonk" and self.singleplayer:
                asyncio.create_task(self.request("bonk", {}))
                await self.say(line, "excited", instant=True, emote="hop",
                               why="the player hit you (probably by accident) and you playfully bonked them back")
            else:
                await self.say(line, "sad" if delta <= -4 else "worried", instant=True, why="the player hit you")
            await self.safe(self.memory.episode("The player hit me.", 5))
        elif name in ("advancement", "new_item"):
            asyncio.create_task(self.notice(name, msg.get("detail", "")))
        elif name == "killed":
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
        self.snapshot = s
        self.snapshot_at = self.clock()
        self.save_snapshot(s)
        await self.heart_watch(s)
        now = self.clock()
        s["recent"] = ["%s (%d seconds ago)" % (x, now - t) for t, x in self.recent if now - t < 90]
        if "health" in s:
            self.in_world = True
        now = self.clock()
        if self.cfg["behaviour"].get("alerts", True):
            alert = self.alerts.check(s, now)
            if alert:
                log.info("alert %s: %s", alert.kind, alert.text)
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
            self.heart.change(-2, "killed villager")
            await self.safe(self.memory.episode("The player killed a %s." % kind, 6))
            asyncio.create_task(self.notice("killed_villager", kind))
            return
        self.kills = [(t, k) for t, k in self.kills if now - t < 90] + [(now, kind)]
        same = [k for t, k in self.kills if k == kind]
        if len(self.kills) >= 4:
            self.kills = []
            asyncio.create_task(self.notice("kill_spree", max(set(same), key=same.count) if same else kind))

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
            elif kind not in self.heart.state["seen_species"] and a.get("distance", 99) < 10:
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
            place = self.heart.lore_place(biome, w.get("dimension"))  # a place from the old stories: the first time
            asyncio.create_task(self.notice("lore_place", place) if place else self.notice("biome", biome))
        self.prev_biome = biome or self.prev_biome
        health = s.get("health", 20)
        prev = self.prev_health
        jumped = self.prev_where is not None and w.get("x") is not None and \
            abs(w["x"] - self.prev_where[0]) + abs(w["z"] - self.prev_where[1]) > 24
        if prev is not None and prev > 0 and health <= 0:
            self.happened("The player died", now)
            asyncio.create_task(self.notice("death"))
        elif prev is not None and (prev <= 0 or (prev < 8 and health >= s.get("maxHealth", 20) and jumped)):
            if prev > 0:  # (the death itself happened between two snapshots)
                self.happened("The player died", now)
                asyncio.create_task(self.notice("death"))
            self.happened("The player came back to life at their spawn point (after dying)", now)
        elif prev is not None and prev - health >= 6:
            self.happened("The player just got badly hurt (lost %s hearts at once)" % round((prev - health) / 2), now)
        self.prev_health = health
        self.prev_where = (w.get("x"), w.get("z")) if w.get("x") is not None else self.prev_where
        self.watch_animals(s, now)
        if (s.get("brokenRecently") or 0) >= 20:
            asyncio.create_task(self.notice("mining"))
        if (s.get("placedRecently") or 0) >= 15:
            asyncio.create_task(self.notice("building"))
        # danger she can help with: by standing request, or by offering if she helped before
        reach = 10 if health <= 8 else 7  # when you're hurt, she keeps them further away
        archers = ("skeleton", "stray", "bogged", "pillager", "witch", "blaze", "breeze", "ghast")
        close = [m for m in s.get("hostiles") or [] if m.get("distance", 99) <= reach
                 or (m.get("distance", 99) <= 16 and m.get("type", "").replace("minecraft:", "") in archers)]
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
                await self.speak_up(self.heart.fizzle_note(ability), "sad")
                return
            await self.send({"type": "act", "look": "around", "seconds": 4})
            self.heart.feel("discovery", 0.5)
            await self.speak_up(self.heart.sensing_note(ability, request, plan["tangent"]), "curious", emote="think")
            done = None
            if plan["favour"]:
                await asyncio.sleep(3)
                if not await self.quiet_moment():
                    return
                st["favour"] = plan["favour"]
                await self.speak_up(self.heart.favour_note(plan["favour"]), "curious")
                st["asked_at"] = self.clock()
                done = await self.wait_favour(st)
                if done:
                    await self.bond_update(self.heart.change(2, "favour"), "did her favour")
            else:
                await asyncio.sleep(max(2.0, plan["reveal"] - plan["sense"]))
            if not await self.quiet_moment():
                return
            offered = self.heart.offered_tools(self.abilities, ability)
            moment = self.heart.origin_moment("a power of yours just woke up", self.clock(), chance=0.5)
            note = self.heart.reveal_note(ability, request, done) + (moment or (
                " You may also wonder, briefly, what this says about what you are." if random.random() < 0.5 else ""))
            await self.speak_up(note, "excited", emote="hop",
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
            if not self.talk_lock.locked() and self.clock() - self.last_talk >= self.quiet_gap:
                return True
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

    async def speak_up(self, instruction, mood, emote=None, tools_=None, force=None):
        """Say something on her own (from the AI), with her current feelings."""
        async with self.talk_lock:
            self.mind.heart = self.heart.guidance(self.mood)
            self.offered = [force] if force else []
            text, m, gesture = await self.mind.initiative(self.snapshot, instruction, tools_,
                                                          self.run_tool if tools_ else None, force)
        self.last_talk = self.clock()
        log.info("on her own: %s", text)
        await self.say(text, m or mood, emote=gesture or emote,
                       style="whisper" if self.mind.last_whisper else None)
        self.last_talk = self.clock()

    # ------------------------------------------------------------------ talking

    async def say(self, text, mood, instant=False, emote=None, style=None, why=""):
        """Speak a line: subtitle plus voice streamed sentence by sentence.

        instant=True shows the subtitle right away and lets the voice follow (danger warnings)."""
        if why:  # a line that didn't come from the AI: the AI hears it too, with why it was said
            self.mind.note_said(text, mood, why)
        self.line += 1
        line = self.line
        self.mood = mood or self.mood
        # a warning's fright passes quickly; a feeling from conversation lasts a bit longer
        self.mood_until = self.clock() + (8 if instant else 20)
        chunks = sentences(text) if self.cfg["voice"].get("enabled", True) else []
        style = style if style is not None else voice.style_for(mood, text)
        first = ""
        if chunks and not instant:
            first = await self._voice(chunks.pop(0), style)
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
            audio = await self._voice(chunk, style)
            if audio is None or line != self.line:
                return
            await self.send({"type": "audio", "line": line, "audio": audio})

    async def _voice(self, text, style=""):
        try:
            return base64.b64encode(await voice.speak(self.cfg, text, style)).decode("ascii")
        except voice.VoiceError as e:
            log.warning("%s (subtitle only)", e)
            return None

    def hear_player(self, text, spoken=False):
        """Messages wait in an inbox while she's thinking; when she's free she answers all of them at once
        (so ten messages in a row get one answer, not ten answers trickling in for a minute)."""
        text = (text or "").strip()
        if not text:
            return
        self.inbox.append((text, spoken))
        if self.inbox_task is None or self.inbox_task.done():
            self.inbox_task = asyncio.create_task(self.drain_inbox())

    async def drain_inbox(self):
        while self.inbox:
            batch, self.inbox = self.inbox, []
            await self.answer(merge_messages([t for t, _ in batch]), any(s for _, s in batch),
                              heard=[t for t, _ in batch])

    async def answer(self, text, spoken=False, heard=None):
        text = (text or "").strip()
        if not text:
            return
        self.last_talk = self.clock()
        acts, done = intents.match(text)
        for act in acts:  # the body reacts at once; the words follow
            await self.send(dict(act, type="act"))
        if acts:
            log.info("acting on: %s", "; ".join(done))
        if intents.PUT_BACK.search(text):  # "put my block back": undo a prank
            res = await self.request("return_block", {})
            log.info("put the block back: %s", res)
            done.append("put the block you borrowed back where it was" if res.get("ok") else
                        "tried to put a block back, but: %s" % res.get("error", "nothing to put back"))
        await self.send({"type": "state", "state": "thinking"})
        async with self.talk_lock:
            try:
                self.last_player_text = text
                force = None
                offer = self.heart.take_offer(self.clock()) if intents.YES.match(text) else None
                if offer and offer["what"] in self.abilities:
                    force = offer["what"]  # "yes" to "want me to push them away?"
                elif intents.YES.match(text) and self.her_offer and self.clock() - self.her_offer[1] < 60:
                    force = self.her_offer[0]  # "yes please" to "should I light it up for you?"
                self.her_offer = None
                force = force or intents.action_hint(text, self.abilities + ["set_reminder", "name_place", "remember",
                                                                              "standing_request"]) \
                    or intents.hint_in_context(text, self.recent_player, self.abilities)
                wanted = intents.action_hint(text, list(tools.ABILITY_TOOLS))
                if wanted and wanted not in self.abilities and self.clock() - self.tipped.get(wanted, -1e9) > 600:
                    self.tipped[wanted] = self.clock()  # her power or style doesn't allow it: a hint for you
                    await self.tip_for(wanted)
                self.recent_player = (self.recent_player + [text])[-3:]
                if self.heart.angry():
                    force = None  # when she's cross, whether to help is her choice
                self.heart.known_self = getattr(self.memory, "self_known", 0)
                for said in heard or [text]:  # (repeating the same words: less effect, then annoyance)
                    self.heart.hear(said)
                note = self.favour_heard(text)
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
                note += await self.world_answer(text)  # how the world works: what it remembers, or listen
                offered = self.heart.offered_tools(self.abilities, force)
                self.offered = offered
                fib = "" if force or (self.snapshot.get("hostiles") or []) else self.heart.fib(self.clock())
                self.mind.allow_fib = bool(fib)
                note += fib
                self.mind.heart = "\n".join(x for x in (self.heart.guidance(self.mood),
                                                       self.heart.discovery_note(self.abilities), note) if x)
                reply, mood, gesture = await self.mind.reply(self.snapshot, text, done,
                                                             tools.for_abilities(offered), self.run_tool, force, spoken)
            except AIError as e:
                log.error("AI error: %s", e)
                await self.send({"type": "notice", "text": "AI gateway problem: %s" % str(e)[:120]})
                await self.say("Hmm, my thoughts are fuzzy right now. Can you check my AI connection?", "sad",
                               why="you couldn't think: the AI connection failed")
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
            await self.say(reply, mood or "happy", emote=gesture,
                           style="whisper" if self.mind.last_whisper else None)
            self.last_talk = self.clock()
        # how they treated her changes the bond (and, when it's really bad, she leaves for a while)
        regard = self.mind.last_regard
        await self.bond_update(self.heart.on_regard(regard), regard)
        if regard == "mean" and self.heart.bond < 25:
            await self.mood_weather(sad=True)
        elif regard == "sorry" and not self.heart.angry():
            await self.mood_weather(sad=False)
        if regard == "mean" and self.heart.bond < 12 and self.heart.p.get("can_vanish", True):
            await self.vanish(120, random.choice(intents_heart.VANISH_LINES))

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
        self.hear_player(text, spoken=True)

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
                instruction = self.heart.musing()
                if not instruction:
                    continue  # she's upset: she keeps to herself
                self.mind.heart = self.heart.guidance(self.mood)
                try:
                    text, mood, gesture = await self.mind.initiative(self.snapshot, instruction + " Don't repeat yourself.")
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
        await asyncio.gather(brain.small_talk_loop(), brain.reminder_loop(), brain.heart_loop(), brain.state_loop())
