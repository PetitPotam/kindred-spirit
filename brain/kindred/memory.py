"""The companion's memory: it keeps what happens, learns from it, and recalls what matters.

Storage lives behind the gateway (/v1/memory/...): a local SQLite file by default, or a gateway
deployed elsewhere. This module decides what to keep and how to use it:

  episodes     everything said and done ("You asked me to find diamonds; I found some 9 blocks
               ahead"), per world
  learned      lasting knowledge distilled by reflection, in four kinds:
                 player  who you are: name, likes, play style, personality, goals
                 self    the companion's own tastes and little story, so it stays itself
                 habit   what you often ask or do ("asks where diamonds are")
                 world   facts about this world (your builds, plans)
  places       spots you named ("my base") and things found together (ores, villages)
  diary        one entry per play session
  reminders    "in 10 minutes", "at night", "next time we play", "every morning"

Recall for each message (retrieval-augmented prompting): always your profile, its identity,
your habits, active reminders and nearby places; plus the memories that best match what is
being said, ranked by meaning, keywords, recency and importance (the gateway does the ranking).

    python -m kindred.memory            show what it remembers
    python -m kindred.memory forget     forget every memory (asks first); keeps the bond and her powers
    python -m kindred.memory reset      a brand-new companion: memories, bond, powers, conversations
    python -m kindred.memory worlds     your worlds and what she knows in each
    python -m kindred.memory import FROM [TO]   bring what she knew about you from one world into another
"""
import asyncio
import json
import os
import math
import re
import sys
import time
import urllib.error
import urllib.request

from . import config

GLOBAL_KINDS = ("player", "self", "habit", "reminder", "origin", "taste", "core")


def ago(seconds):
    s = max(0, int(seconds))
    for unit, n in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if s >= n:
            k = s // n
            return "%d %s%s" % (k, unit, "" if k == 1 else "s")
    return "a moment"


def compass(dx, dz):
    names = ["south", "south-west", "west", "north-west", "north", "north-east", "east", "south-east"]
    return names[round(math.degrees(math.atan2(-dx, dz)) / 45) % 8]


def parse_when(when, now):
    """'in 10 minutes', 'at night', 'tomorrow morning', 'next time', 'every night' -> reminder timing."""
    w = (when or "").lower()
    meta = {}
    if "every" in w or "each" in w or "always" in w:
        meta["repeat"] = True
    m = re.search(r"(\d+|a|an|one|two|three|five|ten|half an?)\s*(second|sec|minute|min|hour|hr)s?", w)
    words = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "five": 5, "ten": 10}
    if m:
        n = m.group(1)
        amount = 0.5 if n.startswith("half") else words.get(n) or int(n)
        unit = m.group(2)
        secs = amount * (3600 if unit.startswith("h") else 1 if unit.startswith("s") else 60)
        meta.update(due=now + secs, every=secs if meta.get("repeat") else None)
    elif "night" in w or "evening" in w or "dark" in w or "sunset" in w:
        meta["game"] = "night"
    elif "morning" in w or "sunrise" in w or "day" in w:
        meta["game"] = "morning"
    elif "next time" in w or "next session" in w or "when we play" in w or "join" in w or "tomorrow" in w:
        meta["session"] = True
    else:
        meta.update(due=now + 600)  # unclear: in ten minutes
    return meta


class GatewayMemory:
    """Talks to the gateway's /v1/memory API."""

    def __init__(self, base, key=""):
        self.base = base.rstrip("/") + "/memory/"
        self.key = key
        self.strict = False  # each world has its own companion: only this world's memories

    def _call(self, op, body):
        if self.strict and body.get("world") and op in ("list", "search", "delete"):
            body = dict(body, strict=True)
        req = urllib.request.Request(self.base + op, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        if self.key:
            req.add_header("Authorization", "Bearer " + self.key)
        for attempt in (1, 2):  # a dropped connection is worth one more try
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                raise MemoryError("memory store refused %s: %s" % (op, e.read()[:200].decode("utf-8", "replace")))
            except (urllib.error.URLError, OSError, ValueError) as e:
                if attempt == 2:
                    raise MemoryError("memory store not reachable: %s" % getattr(e, "reason", e))

    async def call(self, op, **body):
        return await asyncio.to_thread(self._call, op, body)


class Memory:
    def __init__(self, store, clock=time.time):
        self.store = store
        self.clock = clock
        self.world_id = None
        self.per_world = False   # True: each world has its own companion (see brain.toml [heart])
        self.stats = None
        self.session_start = None
        self.exchanges = 0
        self.self_known = 0
        self.since_reflection = 0

    # ------------------------------------------------------------------ sessions

    async def open_world(self, world_id):
        self.world_id = world_id or "unknown"
        self.stats = (await self.store.call("doc", key="world:%s:stats" % self.world_id)).get("value") or {
            "first_met": None, "last_seen": None, "sessions": 0, "minutes": 0}

    async def history(self):
        return (await self.store.call("doc", key="world:%s:history" % self.world_id)).get("value") or []

    async def keep_history(self, history, summary=None):
        await self.store.call("doc", key="world:%s:history" % self.world_id, value=history[-24:])
        if summary is not None:
            await self.store.call("doc", key="world:%s:summary" % self.world_id, value=summary)

    async def summary(self):
        return (await self.store.call("doc", key="world:%s:summary" % self.world_id)).get("value") or ""

    async def _save_stats(self):
        await self.store.call("doc", key="world:%s:stats" % self.world_id, value=self.stats)

    async def start_session(self):
        """Returns how long ago you last played together here (None the first time)."""
        s = self.stats
        since = None if not s["last_seen"] else self.clock() - s["last_seen"]
        s["first_met"] = s["first_met"] or self.clock()
        s["sessions"] += 1
        s["last_seen"] = self.clock()
        self.session_start = self.clock()
        self.exchanges = 0
        await self._save_stats()
        return since

    async def end_session(self):
        if self.session_start is None or self.stats is None:
            return
        self.stats["minutes"] += int((self.clock() - self.session_start) / 60)
        self.stats["last_seen"] = self.clock()
        self.session_start = None
        await self._save_stats()

    # ------------------------------------------------------------------ keeping things

    async def add(self, kind, text, importance=5, meta=None, dedupe=None):
        world = None if kind in GLOBAL_KINDS and not self.per_world else self.world_id
        return await self.store.call("add", kind=kind, text=text, world=world, importance=importance,
                                     meta=meta or {}, dedupe=dedupe)

    async def episode(self, text, importance=3):
        await self.add("episode", text, importance)

    async def remember(self, fact, about="player", importance=7):
        kind = about if about in ("player", "self", "habit", "world") else "player"
        r = await self.add(kind, fact, importance, dedupe=0.88)
        return not r.get("merged")

    async def forget(self, about):
        r = await self.store.call("delete", kinds=["player", "self", "habit", "world", "place", "found", "reminder"],
                                  contains=about, **({"world": self.world_id} if self.per_world else {}))
        return r.get("deleted", 0)

    async def name_place(self, name, snapshot):
        w = (snapshot or {}).get("where") or {}
        if "x" not in w:
            return None
        name = " ".join((name or "").split())[:40] or "this place"
        meta = {"name": name, "x": w["x"], "y": w["y"], "z": w["z"], "dimension": w.get("dimension", "minecraft:overworld")}
        for p in await self.places():
            if p["meta"].get("name", "").lower() == name.lower():  # moved: same name, new spot
                await self.store.call("update", id=p["id"], text="Place the player named '%s'" % name, meta=meta)
                return meta
        await self.add("place", "Place the player named '%s'" % name, 7, meta)
        return meta

    async def found(self, what, x, y, z, dimension):
        for f in (await self.store.call("list", kinds=["found"], world=self.world_id, limit=60))["results"]:
            m = f["meta"]
            if f["text"].endswith(what) and abs(m.get("x", 1e9) - x) < 16 and abs(m.get("z", 1e9) - z) < 16:
                return
        await self.add("found", "We found %s" % what, 5, {"x": x, "y": y, "z": z, "dimension": dimension, "what": what})

    async def places(self):
        return (await self.store.call("list", kinds=["place"], world=self.world_id, limit=30))["results"]

    async def write_diary(self, text):
        if text:
            await self.add("diary", "%s: %s" % (time.strftime("%Y-%m-%d", time.localtime(self.clock())), text), 6)

    # ------------------------------------------------------------------ reminders

    async def add_reminder(self, text, when):
        meta = parse_when(when, self.clock())
        meta["when"] = when
        await self.add("reminder", text, 8, meta)
        return meta

    async def reminders(self):
        return (await self.store.call("list", kinds=["reminder"], world=self.world_id, limit=30))["results"]

    async def cancel_reminder(self, about):
        r = await self.store.call("delete", kinds=["reminder"], contains=about)
        return r.get("deleted", 0)

    async def due(self, event=None):
        """Reminders due now: by the clock, or on an event ('night', 'morning', 'session')."""
        out = []
        now = self.clock()
        for r in await self.reminders():
            m = r["meta"]
            hit = (m.get("due") and now >= m["due"]) or (event == "night" and m.get("game") == "night") \
                or (event == "morning" and m.get("game") == "morning") or (event == "session" and m.get("session"))
            if not hit:
                continue
            out.append(r)
            if m.get("repeat"):
                if m.get("every"):
                    m["due"] = now + m["every"]
                await self.store.call("update", id=r["id"], meta=m)
            else:
                await self.store.call("delete", id=r["id"], kinds=["reminder"])
        return out

    # ------------------------------------------------------------------ recall (what goes in the prompt)

    async def context(self, snapshot, query):
        where = (snapshot or {}).get("where") or {}

        def rel(m):
            if "x" not in m:
                return ""
            if "x" not in where:
                return " (at %d %d %d)" % (m["x"], m["y"], m["z"])
            if m.get("dimension") and where.get("dimension") and m["dimension"] != where["dimension"]:
                return " (in %s)" % m["dimension"].replace("minecraft:", "").replace("_", " ")
            dx, dz = m["x"] - where["x"], m["z"] - where["z"]
            d = math.hypot(dx, dz)
            return " (right here)" if d < 6 else " (%d blocks %s)" % (round(d), compass(dx, dz))

        lst = self.store.call
        topic = " ".join([query or "", where.get("biome", ""), (snapshot or {}).get("holding", "")])
        core = await asyncio.gather(
            lst("list", kinds=["player"], world=self.world_id, limit=8, order="important"),
            lst("list", kinds=["self"], world=self.world_id, limit=5, order="important"),
            lst("list", kinds=["origin"], world=self.world_id, limit=8, order="oldest"),
            lst("list", kinds=["taste"], world=self.world_id, limit=10, order="recent"),
            lst("list", kinds=["core"], world=self.world_id, limit=5, order="important"),
            lst("list", kinds=["habit"], world=self.world_id, limit=4, order="important"),
            lst("list", kinds=["reminder"], world=self.world_id, limit=6),
            lst("list", kinds=["place"], world=self.world_id, limit=8),
            lst("search", query=topic, kinds=["player", "self", "habit", "world", "found", "episode", "diary"],
                world=self.world_id, k=8))
        now = self.clock()
        player, me, origin, tastes, cores, habits, reminders, places, recalled = (
            [m for m in c["results"] if m.get("text") and (m.get("meta") or {}).get("expires", now + 1) > now]
            for c in core)
        seen = {m["id"] for group in (player, me, origin, tastes, cores, habits, reminders, places) for m in group}
        self.self_known = len(origin) + len(me)  # (how much she knows about herself: her doubts depend on it)
        lines = []
        if player:
            lines.append("About the player: " + " ".join(m["text"].rstrip(".") + "." for m in player))
        if me:
            lines.append("About yourself: " + " ".join(m["text"].rstrip(".") + "." for m in me))
        lines.append("Where you come from: " + (" ".join(m["text"].rstrip(".") + "." for m in origin) +
                                                " Beyond that, it's still a mystery." if origin else
                                                "you don't know yet; it's a mystery you'll uncover together."))
        if tastes:
            lines.append("Your tastes (they can change): " + "; ".join(m["text"] for m in tastes) + ".")
        if cores:
            lines.append("Moments that shaped you: " + " ".join(
                m["text"].rstrip(".") + (" (it still hurts)." if (m.get("meta") or {}).get("pain") and not
                                         (m.get("meta") or {}).get("healed") else
                                         " (you've made peace with it)." if (m.get("meta") or {}).get("healed") else ".")
                for m in cores))
        if habits:
            lines.append("The player's habits: " + " ".join(m["text"].rstrip(".") + "." for m in habits))
        if places:
            lines.append("Named places: " + "; ".join(m["meta"].get("name", m["text"]) + rel(m["meta"]) for m in places) + ".")
        if reminders:
            lines.append("Reminders you hold: " + "; ".join("%s (%s)" % (m["text"], m["meta"].get("when", "")) for m in reminders) + ".")
        extra = [m for m in recalled if m["id"] not in seen and m["score"] > 0.2][:6]
        if extra:
            lines.append("Memories that come to mind: " + " | ".join(m["text"] + rel(m["meta"]) for m in extra))
        s = self.stats or {}
        if s.get("first_met"):
            lines.append("You have played together %d time%s in this world since %s (about %d minutes in all)." % (
                s["sessions"], "" if s["sessions"] == 1 else "s",
                time.strftime("%Y-%m-%d", time.localtime(s["first_met"])), s["minutes"]))
        return "\n".join(lines)

    async def welcome(self, since):
        if since is None:
            return ("The player just joined this world, and it's your first time here together. Greet them warmly "
                    "in one short sentence, maybe noticing one thing about where they are.")
        diary = (await self.store.call("list", kinds=["diary"], world=self.world_id, limit=1))["results"]
        last = diary[0]["text"] if diary else ""
        return "The player is back after %s. Welcome them back warmly in one short sentence%s." % (
            ago(since), ", maybe recalling something from your diary (%s)" % last if last else "")

    # ------------------------------------------------------------------ learning (reflection)

    async def learn_self(self, lessons):
        """Her tastes (one per thing, and she can change her mind), her core memories, and the hurts she
        made peace with."""
        added = 0
        for t in lessons.get("tastes") or []:
            if not isinstance(t, dict) or not t.get("about") or t.get("feeling") not in ("love", "like", "dislike", "hate"):
                continue
            about = str(t["about"]).strip().lower()[:60]
            text = "I %s %s%s" % (t["feeling"], about, (" (%s)" % t["why"].rstrip(".")) if t.get("why") else "")
            old = [m for m in (await self.store.call("list", kinds=["taste"], world=self.world_id, limit=200))["results"]
                   if (m.get("meta") or {}).get("about") == about]
            meta = {"about": about, "feeling": t["feeling"]}
            if old:  # she changed her mind (or felt it again): one opinion per thing, with what it was before
                was = old[0]["meta"].get("feeling")
                if was != t["feeling"]:
                    meta["was"] = was
                await self.store.call("update", id=old[0]["id"], text=text, meta=meta, importance=7)
            else:
                await self.add("taste", text, 6, meta=meta)
                added += 1
        for c in (lessons.get("core") or [])[:1]:
            if isinstance(c, dict) and c.get("text") and len(c["text"]) < 300:
                await self.add("core", c["text"], 10, meta={"feeling": c.get("feeling", ""), "pain": bool(c.get("pain"))},
                               dedupe=0.9)
                added += 1
        for mid in lessons.get("healed") or []:
            try:
                rows = (await self.store.call("list", kinds=["core"], world=self.world_id, limit=50))["results"]
                row = next((r for r in rows if r["id"] == int(mid)), None)
                if row:
                    await self.store.call("update", id=row["id"], meta=dict(row.get("meta") or {}, healed=True))
            except (TypeError, ValueError):
                pass
        return added

    async def known_for(self, text):
        hits = (await self.store.call("search", query=text, kinds=["player", "self", "habit", "world", "taste"],
                                      world=self.world_id, k=15))["results"]
        cores = (await self.store.call("list", kinds=["core"], world=self.world_id, limit=10))["results"]
        return ["#%d %s" % (h["id"], h["text"]) for h in hits] + [
            "#%d (a core memory%s) %s" % (c["id"], ", still painful" if (c.get("meta") or {}).get("pain") and not
                                          (c.get("meta") or {}).get("healed") else "", c["text"]) for c in cores]

    async def learn(self, lessons):
        """Applies what reflection found: new knowledge, merged with what it already knew."""
        added = 0
        for kind in ("player", "self", "habit", "world", "origin"):
            for item in lessons.get(kind) or []:
                text = item.get("text") if isinstance(item, dict) else str(item)
                imp = item.get("importance", 6) if isinstance(item, dict) else 6
                passing = isinstance(item, dict) and bool(item.get("temporary"))
                if text and len(text) < 300:
                    # a passing feeling or situation fades after a day and a half, and never outranks
                    # what lasts
                    r = await self.add(kind, text, min(5, imp) if passing else max(1, min(10, int(imp))),
                                       meta={"expires": self.clock() + PASSING} if passing else None,
                                       dedupe=0.86)
                    added += 0 if r.get("merged") else 1
        added += await self.learn_self(lessons)
        diary = lessons.get("diary")
        if isinstance(diary, list):  # some models wrap it like the other lists
            diary = " ".join(d.get("text", "") if isinstance(d, dict) else str(d) for d in diary)
        elif isinstance(diary, dict):
            diary = diary.get("text", "")
        if diary:
            await self.write_diary(str(diary))
        for old, new in lessons.get("merge") or []:  # "these two say the same thing": keep one
            try:
                await self.store.call("update", id=int(new), importance=10)
                await self.store.call("delete", id=int(old), kinds=["player", "self", "habit", "world"])
            except (TypeError, ValueError):
                pass
        return added


PASSING = 36 * 3600  # how long a passing feeling or situation stays in mind
IMPORTED = ("player", "self", "habit", "origin", "taste", "core")  # who you are, who she is, your habits: not places or events


def worlds_cli(store, argv):
    """worlds: each world and what she knows there.  import FROM [TO]: bring what she knew about you
    (and, with the game closed, her bond and powers) from one world into another."""
    rows = store._call("list", {"limit": 5000, "all_worlds": True, "order": "recent"})["results"]
    worlds = []
    for r in rows:  # most recently used first
        if r["world"] and r["world"] not in worlds:
            worlds.append(r["world"])

    def find(name):
        hits = [w for w in worlds if name.lower() == w.lower() or name.lower() in w.lower()]
        return hits[0] if len(hits) == 1 else None

    if argv[0] == "worlds":
        if not worlds:
            print("No worlds yet.")
        for w in worlds:
            mine = [r for r in rows if r["world"] == w]
            about = [r["text"] for r in mine if r["kind"] == "player"][:2]
            print("%-28s %3d memories%s" % (w.split(":", 1)[-1], len(mine),
                                           ("   e.g. " + " / ".join(about)) if about else ""))
        return 0
    if len(argv) < 2:
        print('Usage: scripts/memory.sh import "FROM WORLD" ["TO WORLD"]   (TO: the world you played last)')
        return 1
    src = find(argv[1])
    dst = find(argv[2]) if len(argv) > 2 else next((w for w in worlds if w != src), None)
    if not src or not dst or src == dst:
        print("Which worlds? I know: %s" % ", ".join(w.split(":", 1)[-1] for w in worlds))
        return 1
    copied = 0
    for r in store._call("list", {"kinds": list(IMPORTED), "world": src, "strict": True, "limit": 200})["results"]:
        out = store._call("add", {"kind": r["kind"], "text": r["text"], "world": dst, "importance": r["importance"],
                                  "meta": dict(r.get("meta") or {}, imported_from=src), "dedupe": 0.88})
        copied += 0 if out.get("merged") else 1
    print("Copied %d memories about you and her from %s into %s." % (copied, src.split(":", 1)[-1],
                                                                    dst.split(":", 1)[-1]))
    heart = store._call("doc", {"key": "world:%s:heart" % src}).get("value")
    if heart and os.environ.get("KINDRED_GAME_CONNECTED") == "1":
        print("Her bond and discovered powers were not copied: the game is connected. Quit it and import again "
              "to bring those too.")
    elif heart:
        mine = store._call("doc", {"key": "world:%s:heart" % dst}).get("value") or {}
        mine.update({k: heart[k] for k in ("bond", "discovered", "asked", "requests") if k in heart})
        store._call("doc", {"key": "world:%s:heart" % dst, "value": mine})
        print("Her bond (%d) and the powers she discovered there came along too." % round(heart.get("bond", 30)))
    return 0


def main(argv):
    cfg = config.load()
    store = GatewayMemory(cfg["gateway"]["url"], cfg["gateway"].get("key", ""))
    if argv[:1] == ["forget"]:
        if input("Forget everything Kindred remembers? Type yes: ").strip().lower() == "yes":
            n = store._call("delete", {"kinds": ["player", "self", "habit", "world", "place", "found", "episode",
                                                 "diary", "reminder"], "contains": ""})
            print("Forgotten (%s)." % n)
        return 0
    if argv[:1] == ["reset"]:  # (scripts/memory.sh reset stops the brain first, then starts it again)
        if input("Reset your companion completely: every memory, the bond, discovered powers and "
                 "conversations? Type yes: ").strip().lower() == "yes":
            n = store._call("delete", {"kinds": ["player", "self", "origin", "taste", "core", "habit", "world", "place", "found",
                                                 "episode", "diary", "reminder"], "contains": ""})
            d = store._call("clear_docs", {})
            print("Reset: %s, %s. Next time you play, you'll meet a brand-new companion." % (n, d))
        return 0
    if argv[:1] in (["worlds"], ["import"]):
        return worlds_cli(store, argv)
    for kind in ("player", "self", "origin", "core", "taste", "habit", "reminder", "world", "place", "found", "diary",
                 "episode"):
        rows = store._call("list", {"kinds": [kind], "limit": 15, "order": "important", "all_worlds": True})["results"]
        if rows:
            print("\n%s:" % kind)
            for r in rows:
                print("  [%s] %s%s" % (int(r["importance"]), r["text"], "  (%s)" % r["world"] if r["world"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
