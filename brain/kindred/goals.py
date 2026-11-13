"""Goals you share with her, kept across restarts (Phase 4: goals, routines, goal nudges).

"Let's build a castle", "I want full diamond armor", "we need to find a village": a goal is a short
text, maybe a few steps, and optionally a check the game can answer by itself (you have 24 diamonds,
you're in the Nether), so she notices when it's done without being told. Goals live per world in the
memory store (`world:<id>:goals`, like her heart), so they're still there tomorrow.

Nudges: when the player has been idle a while and nothing's urgent, she may bring one up ("we still
need 9 more diamonds for the armor, shall we go mining?"), rarely (`nudge_minutes` apart, longer when
the bond is low or she was told to be quiet), and never the same one twice in a row. Routines are
reminders that repeat ("every night we check the farm"): the existing reminders already do that
(memory.add_reminder with "every night"), so they aren't duplicated here.

Wiring (waits for the playtest-fixes branch, which is changing server.py, tools.py and mind.py):
tools `set_goal`, `goal_progress`, `drop_goal`; `context()` in her prompt with memories; `check()` on
each snapshot; `nudge()` from the idle loop where she proposes little goals today.
"""
import re
import time
import uuid

MAX_GOALS = 12
NUDGE_MINUTES = 20


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def check_done(check, snapshot):
    """Whether a goal's machine check is met by a snapshot. Checks:
    {"have": {"item": "minecraft:diamond", "count": 24}}, {"dimension": "minecraft:the_nether"},
    {"advancement": "minecraft:story/enter_the_nether"} (when the snapshot lists advancements)."""
    if not check or not snapshot:
        return False
    if "have" in check:
        h = check["have"]
        item = h.get("item", "")
        if ":" not in item:
            item = "minecraft:" + item
        return (snapshot.get("inventory") or {}).get(item, 0) >= int(h.get("count", 1))
    if "dimension" in check:
        dim = check["dimension"] if ":" in check["dimension"] else "minecraft:" + check["dimension"]
        return (snapshot.get("where") or {}).get("dimension") == dim
    if "advancement" in check:
        return check["advancement"] in (snapshot.get("advancements") or [])
    return False


class Goals:
    def __init__(self, memory=None, clock=time.time):
        self.memory = memory
        self.clock = clock
        self.goals = []
        self.last_nudge = 0.0
        self.last_nudged_id = None

    def key(self):
        world = getattr(self.memory, "world_id", None) or "unknown"
        return "world:%s:goals" % world

    async def load(self):
        self.goals, self.last_nudge, self.last_nudged_id = [], 0.0, None
        if self.memory is None:
            return
        try:
            saved = (await self.memory.store.call("doc", key=self.key())).get("value") or {}
        except Exception:
            saved = {}
        self.goals = list(saved.get("goals") or [])
        self.last_nudge = float(saved.get("last_nudge") or 0.0)
        self.last_nudged_id = saved.get("last_nudged_id")

    async def save(self):
        if self.memory is None:
            return
        try:
            await self.memory.store.call("doc", key=self.key(), value={
                "goals": self.goals, "last_nudge": self.last_nudge, "last_nudged_id": self.last_nudged_id})
        except Exception:
            pass

    # ------------------------------------------------------------------ changing them

    def active(self):
        return [g for g in self.goals if g["status"] == "active"]

    def find(self, about):
        """The active goal whose text best matches some words (the latest when several do)."""
        words = set(_norm(about).split()) - {"the", "a", "an", "our", "my", "goal", "to", "of"}
        best, best_score = None, 0
        for g in self.active():
            score = len(words & set(_norm(g["text"]).split()))
            if score > best_score or (score == best_score and score and g["created"] > best["created"]):
                best, best_score = g, score
        return best

    async def add(self, text, steps=None, check=None, who="player"):
        text = (text or "").strip()
        if not text:
            return None
        same = next((g for g in self.active() if _norm(g["text"]) == _norm(text)), None)
        if same:
            return same
        now = self.clock()
        g = {"id": uuid.uuid4().hex[:8], "text": text, "who": who, "status": "active", "created": now, "updated": now,
             "steps": [{"text": s, "done": False} for s in (steps or []) if s], "check": check or None}
        self.goals.append(g)
        # keep the newest active ones and a few finished ones to remember
        active = self.active()
        if len(active) > MAX_GOALS:
            oldest = min(active, key=lambda x: x["updated"])
            oldest["status"] = "dropped"
        done = [x for x in self.goals if x["status"] != "active"]
        if len(done) > MAX_GOALS:
            done.sort(key=lambda x: x["updated"])
            for x in done[:len(done) - MAX_GOALS]:
                self.goals.remove(x)
        await self.save()
        return g

    async def progress(self, about, step=None):
        """Marks a step done (the one matching `step`, else the first open one); the goal is done when
        every step is. Returns the goal or None."""
        g = self.find(about)
        if not g:
            return None
        open_steps = [s for s in g["steps"] if not s["done"]]
        if open_steps:
            target = next((s for s in open_steps if step and _norm(step) in _norm(s["text"])), open_steps[0])
            target["done"] = True
        g["updated"] = self.clock()
        if g["steps"] and all(s["done"] for s in g["steps"]):
            g["status"] = "done"
        await self.save()
        return g

    async def complete(self, about):
        g = self.find(about)
        if g:
            g["status"], g["updated"] = "done", self.clock()
            await self.save()
        return g

    async def drop(self, about):
        g = self.find(about)
        if g:
            g["status"], g["updated"] = "dropped", self.clock()
            await self.save()
        return g

    async def check(self, snapshot):
        """Goals the game says are done now (she can cheer: 'twenty-four diamonds, we did it!')."""
        done = []
        for g in self.active():
            if check_done(g.get("check"), snapshot):
                g["status"], g["updated"] = "done", self.clock()
                done.append(g)
        if done:
            await self.save()
        return done

    # ------------------------------------------------------------------ talking about them

    def describe(self, g, snapshot=None):
        line = g["text"]
        steps = g.get("steps") or []
        if steps:
            left = [s["text"] for s in steps if not s["done"]]
            line += " (%d of %d steps done%s)" % (len(steps) - len(left), len(steps),
                                                   "; next: " + left[0] if left else "")
        h = (g.get("check") or {}).get("have")
        if h and snapshot is not None:
            item = h.get("item", "")
            item = item if ":" in item else "minecraft:" + item
            have = (snapshot.get("inventory") or {}).get(item, 0)
            line += " (%d of %d %s so far)" % (min(have, h.get("count", 1)), h.get("count", 1),
                                               item.split(":")[1].replace("_", " "))
        return line

    def context(self, snapshot=None, limit=4):
        """For her prompt: what you two are working toward."""
        act = sorted(self.active(), key=lambda g: -g["updated"])[:limit]
        if not act:
            return ""
        return "Goals you share with the player: " + "; ".join(self.describe(g, snapshot) for g in act) + "."

    def nudge(self, idle_seconds, bond=50, quiet=False, danger=False, minutes=NUDGE_MINUTES):
        """A goal worth bringing up now, or None. Rare by design: idle for a minute or more, nothing
        dangerous, not quiet mode, `minutes` since the last nudge (twice as long when the bond is low)."""
        if quiet or danger or idle_seconds < 60 or not self.active():
            return None
        wait = minutes * 60 * (2 if bond < 30 else 1)
        now = self.clock()
        if now - self.last_nudge < wait:
            return None
        options = sorted(self.active(), key=lambda g: g["updated"])  # the one left alone longest
        pick = next((g for g in options if g["id"] != self.last_nudged_id), options[0])
        if pick["id"] == self.last_nudged_id and len(options) == 1 and now - self.last_nudge < 3 * wait:
            return None  # only one goal: bring it up less often
        self.last_nudge, self.last_nudged_id = now, pick["id"]
        return pick
