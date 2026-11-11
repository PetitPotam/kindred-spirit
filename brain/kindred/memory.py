"""The companion's memory: what it knows about you, and what it remembers of each world.

Plain JSON files in ~/.kindred-spirit/memory/, readable and deletable:
  you.json               facts about you, shared by every world ("loves cherry trees")
  world-<name>.json      per world: named places ("my base"), discoveries (ores, villages it
                         found), a diary entry per play session, how long you have played
                         together, and the recent conversation (so a restart continues it)

    python -m kindred.memory            show everything it remembers
    python -m kindred.memory clear      forget everything (asks first)
"""
import json
import math
import os
import re
import sys
import time

from . import config

DIR = os.path.join(config.HOME, "memory")
MAX_FACTS, MAX_PLACES, MAX_FOUND, MAX_DIARY = 60, 30, 40, 60


def _now():
    return time.time()


def _day(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def ago(seconds):
    """1 day 3 hours ago -> "1 day"."""
    s = max(0, int(seconds))
    for unit, n in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if s >= n:
            k = s // n
            return "%d %s%s" % (k, unit, "" if k == 1 else "s")
    return "a moment"


def compass(dx, dz):
    names = ["south", "south-west", "west", "north-west", "north", "north-east", "east", "south-east"]
    a = math.degrees(math.atan2(-dx, dz))
    return names[round(a / 45) % 8]


def _safe(world):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", world or "unknown")[:80]


class Memory:
    def __init__(self, directory=DIR, clock=_now):
        self.dir = directory
        self.clock = clock
        os.makedirs(self.dir, exist_ok=True)
        self.you = self._load("you.json", {"facts": []})
        self.world_id = None
        self.world = None
        self.session_start = None
        self.exchanges = 0

    # ------------------------------------------------------------------ files

    def _path(self, name):
        return os.path.join(self.dir, name)

    def _load(self, name, default):
        try:
            with open(self._path(name), encoding="utf-8") as fh:
                data = json.load(fh)
            return {**default, **data}
        except (OSError, ValueError):
            return json.loads(json.dumps(default))

    def _write(self, name, data):
        tmp = self._path(name) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, ensure_ascii=False)
        os.replace(tmp, self._path(name))

    def save(self):
        self._write("you.json", self.you)
        if self.world is not None:
            self._write("world-%s.json" % _safe(self.world_id), self.world)

    # ------------------------------------------------------------------ sessions

    def open_world(self, world_id):
        if self.world is not None and world_id == self.world_id:
            return
        self.world_id = world_id or "unknown"
        self.world = self._load("world-%s.json" % _safe(self.world_id), {
            "world": self.world_id, "first_met": None, "last_seen": None, "sessions": 0, "minutes": 0,
            "places": {}, "found": [], "diary": [], "history": []})

    def start_session(self):
        """Returns how long ago you last played together (None the first time)."""
        w = self.world
        since = None if not w["last_seen"] else self.clock() - w["last_seen"]
        if not w["first_met"]:
            w["first_met"] = self.clock()
        w["sessions"] += 1
        w["last_seen"] = self.clock()
        self.session_start = self.clock()
        self.exchanges = 0
        self.save()
        return since

    def end_session(self):
        if self.world is None or self.session_start is None:
            return
        self.world["minutes"] += int((self.clock() - self.session_start) / 60)
        self.world["last_seen"] = self.clock()
        self.session_start = None
        self.save()

    # ------------------------------------------------------------------ things to remember

    def remember(self, fact):
        fact = " ".join((fact or "").split())[:200]
        if not fact:
            return False
        facts = self.you["facts"]
        if any(f["text"].lower() == fact.lower() for f in facts):
            return False
        facts.append({"text": fact, "at": self.clock()})
        del facts[:-MAX_FACTS]
        self.save()
        return True

    def forget(self, about):
        """Forgets facts and places mentioning it; returns how many things were forgotten."""
        a = (about or "").lower().strip()
        if not a:
            return 0
        before = len(self.you["facts"])
        self.you["facts"] = [f for f in self.you["facts"] if a not in f["text"].lower()]
        n = before - len(self.you["facts"])
        if self.world is not None:
            for name in [p for p in self.world["places"] if a in p.lower()]:
                del self.world["places"][name]
                n += 1
        self.save()
        return n

    def name_place(self, name, snapshot):
        w = (snapshot or {}).get("where") or {}
        if self.world is None or "x" not in w:
            return None
        name = " ".join((name or "").split())[:40] or "this place"
        self.world["places"][name] = {"x": w["x"], "y": w["y"], "z": w["z"],
                                      "dimension": w.get("dimension", "minecraft:overworld"), "at": self.clock()}
        if len(self.world["places"]) > MAX_PLACES:
            oldest = min(self.world["places"], key=lambda k: self.world["places"][k]["at"])
            del self.world["places"][oldest]
        self.save()
        return self.world["places"][name]

    def found(self, what, x, y, z, dimension):
        """Something it found or located (ores, villages...), so it can mention it later."""
        if self.world is None:
            return
        items = self.world["found"]
        for f in items:  # the same thing again: just refresh it
            if f["what"] == what and abs(f["x"] - x) < 16 and abs(f["z"] - z) < 16:
                f["at"] = self.clock()
                self.save()
                return
        items.append({"what": what, "x": x, "y": y, "z": z, "dimension": dimension, "at": self.clock()})
        del items[:-MAX_FOUND]
        self.save()

    def write_diary(self, text):
        if self.world is None or not text:
            return
        self.world["diary"].append({"day": _day(self.clock()), "text": " ".join(text.split())[:400]})
        del self.world["diary"][:-MAX_DIARY]
        self.save()

    def keep_history(self, history):
        if self.world is not None:
            self.world["history"] = history[-24:]
            self.save()

    # ------------------------------------------------------------------ what goes into the prompt

    def block(self, snapshot):
        """A short "what you remember" text for the AI, with places relative to where you stand."""
        lines = []
        facts = [f["text"] for f in self.you["facts"][-15:]]
        if facts:
            lines.append("About the player: " + "; ".join(facts) + ".")
        w = self.world
        if w is None:
            return "\n".join(lines)
        where = (snapshot or {}).get("where") or {}
        here_dim = where.get("dimension")

        def rel(p):
            if "x" not in where:
                return "at %d %d %d" % (p["x"], p["y"], p["z"])
            if p.get("dimension") and here_dim and p["dimension"] != here_dim:
                return "in %s" % p["dimension"].replace("minecraft:", "").replace("_", " ")
            dx, dz = p["x"] - where["x"], p["z"] - where["z"]
            d = math.hypot(dx, dz)
            if d < 6:
                return "right here"
            return "%d blocks %s" % (round(d), compass(dx, dz))

        if w["places"]:
            lines.append("Places the player named: " + "; ".join(
                "%s (%s)" % (n, rel(p)) for n, p in list(w["places"].items())[-8:]) + ".")
        if w["found"]:
            lines.append("Things you found together: " + "; ".join(
                "%s (%s)" % (f["what"].replace("_", " "), rel(f)) for f in w["found"][-8:]) + ".")
        if w["diary"]:
            lines.append("Your diary of past sessions: " + " | ".join(
                "%s: %s" % (d["day"], d["text"]) for d in w["diary"][-3:]))
        if w["first_met"]:
            lines.append("You have played together %d time%s in this world since %s (about %d minutes in all)." % (
                w["sessions"], "" if w["sessions"] == 1 else "s", _day(w["first_met"]), w["minutes"]))
        return "\n".join(lines)

    def welcome(self, since):
        """The greeting instruction when the player joins."""
        if since is None:
            return ("The player just joined this world, and it's your first time here together. Greet them warmly "
                    "in one short sentence, maybe noticing one thing about where they are.")
        last = self.world["diary"][-1]["text"] if self.world and self.world["diary"] else ""
        return ("The player is back after %s. Welcome them back warmly in one short sentence%s." % (
            ago(since), ", maybe recalling something from your diary: " + last if last else ""))


def main(argv):
    m = Memory()
    if argv[:1] == ["clear"]:
        if input("Forget everything Kindred remembers (all worlds)? Type yes: ").strip().lower() == "yes":
            for f in os.listdir(m.dir):
                if f.endswith(".json"):
                    os.remove(os.path.join(m.dir, f))
            print("Forgotten.")
        return 0
    print("About you:")
    for f in m.you["facts"]:
        print("  -", f["text"])
    for f in sorted(os.listdir(m.dir)):
        if f.startswith("world-") and f.endswith(".json"):
            with open(os.path.join(m.dir, f), encoding="utf-8") as fh:
                w = json.load(fh)
            print("\n%s: %d sessions, %d minutes" % (w["world"], w["sessions"], w["minutes"]))
            for n, p in w["places"].items():
                print("  place  %s at %d %d %d" % (n, p["x"], p["y"], p["z"]))
            for x in w["found"]:
                print("  found  %s at %d %d %d" % (x["what"], x["x"], x["y"], x["z"]))
            for d in w["diary"][-5:]:
                print("  diary  %s %s" % (d["day"], d["text"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
