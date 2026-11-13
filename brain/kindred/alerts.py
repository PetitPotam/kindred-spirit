"""Danger warnings, decided by rules (not the AI) so they are instant, free and reliable.

Each alert has its own cooldown, so it warns you once instead of nagging. Add new alerts here:
a function that looks at the snapshot and returns an Alert or None, plus a test in
tests/test_alerts.py.
"""
import random
import re
from dataclasses import dataclass

from .describe import where_words

SAFE_MODES = {"creative", "spectator"}


def shout(line, direction="", above=0):
    """A warning as an instinctive shout. A direction only when it matters: behind you (you can't see
    it) or right below you. Old lines written with a place to fill in get it filled with that, or
    nothing."""
    d = (direction or "").lower()
    extra = "behind you" if "behind" in d else "right below you" if (above or 0) <= -3 else ""
    if "{where}" in line:
        line = line.replace("{where}", extra)
        line = re.sub(r"\s+([!?,.])", r"\1", re.sub(r"\s{2,}", " ", line)).replace(" ,", ",").strip()
        return line[0].upper() + line[1:]
    if extra:
        line += " " + extra[0].upper() + extra[1:] + "!"
    return line


@dataclass
class Alert:
    kind: str
    text: str
    mood: str


# a warning is a shout, not directions: "Creeper! Watch out!" (and "Behind you!" only when it's behind you)
CREEPER_LINES = [
    "Creeper! Watch out!",
    "Eek, creeper! Move!",
    "Creeper! Run!",
    "Creeper! Get away from it!",
]
# a shout, not a readout: no numbers (he asked for instinct, not a health bar)
LOW_HEALTH_HUNGRY = [
    "You're hurt! Eat something!",
    "Ouch, you're hurt! Eat, quick!",
]
LOW_HEALTH_FED = [
    "You're really hurt! Back off!",
    "Careful, you're hurt! Hide a bit!",
]
LOW_HEALTH_DANGER = [
    "You're hurt! Run!",
    "Get out of there, you're hurt!",
]


LAVA_LINES = [
    "Lava! Careful!",
    "Whoa, lava! Stop!",
    "Hot hot hot! Lava!",
]
DROP_LINES = [
    "Whoa, careful! Big drop!",
    "Watch your step!",
]
DROP_LAVA_LINES = ["Stop! Lava down there!"]


class Alerts:
    CREEPER_RANGE = 8.0
    CREEPER_COOLDOWN = 20.0
    LOW_HEALTH = 6.0           # 3 hearts
    HEALTH_REARM = 12.0        # warn again only after healing back above 6 hearts...
    LOW_HEALTH_REMIND = 240.0  # ...or after this long still low (9 reminders in 30 minutes was nagging), or lower still
    MIN_GAP = 3.0              # never two warnings closer than this
    LAVA_COOLDOWN = 15.0
    DROP_COOLDOWN = 180.0      # (walking along cliffs or building at an edge shouldn't nag)

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.last = {}
        self.last_any = -1e9
        self.health_armed = True
        self.pools = {}  # her own words for each warning, written by her thinking AI (instinct.py)

    def check(self, s, now):
        """Returns at most one Alert for this snapshot (the most urgent)."""
        if not s or "health" not in s or s.get("gamemode") in SAFE_MODES or s.get("health", 0) <= 0:
            return None
        health = s.get("health", 20)
        if health >= self.HEALTH_REARM:
            self.health_armed = True
        found = self._creeper(s, now) or self._lava(s, now) or self._low_health(s, now) or self._drop(s, now)
        if found and now - self.last_any >= self.MIN_GAP:
            self.last[found.kind] = now
            self.last_any = now
            if found.kind == "low_health":
                self.health_armed = False
            return found
        return None

    def _ready(self, kind, cooldown, now):
        return now - self.last.get(kind, -1e9) >= cooldown

    def _creeper(self, s, now):
        creepers = [m for m in s.get("hostiles") or [] if m.get("type") == "minecraft:creeper"
                    and m.get("distance", 99) <= self.CREEPER_RANGE]
        if not creepers or not self._ready("creeper", self.CREEPER_COOLDOWN, now):
            return None
        c = min(creepers, key=lambda m: m.get("distance", 99))
        return Alert("creeper", shout(self.rng.choice(self.pools.get("creeper") or CREEPER_LINES),
                                      c.get("direction"), c.get("above", 0)), "scared")

    def _lava(self, s, now):
        h = next((h for h in s.get("hazards") or [] if h.get("kind") in ("lava", "drop_lava")), None)
        if not h or not self._ready("lava", self.LAVA_COOLDOWN, now):
            return None
        pool = DROP_LAVA_LINES if h["kind"] == "drop_lava" else LAVA_LINES
        return Alert("lava", shout(self.rng.choice(self.pools.get("lava") or pool), h.get("direction"),
                                   -h.get("depth", 0)), "scared")

    def _drop(self, s, now):
        h = next((h for h in s.get("hazards") or [] if h.get("kind") == "drop" and h.get("depth", 0) >= 8
                  and h.get("distance", 99) <= 3), None)  # (right at the edge, not a cliff over there)
        if not h or not self._ready("drop", self.DROP_COOLDOWN, now):
            return None
        return Alert("drop", shout(self.rng.choice(self.pools.get("drop") or DROP_LINES), h.get("direction"), 0),
                     "worried")

    def _low_health(self, s, now):
        health = s.get("health", 20)
        if health > self.LOW_HEALTH:
            return None
        if not self.health_armed and not self._ready("low_health", self.LOW_HEALTH_REMIND, now) \
                and health >= getattr(self, "health_warned", 99) - 3:
            return None  # (still low, not much lower: she said it already)
        self.health_warned = health
        hearts = health / 2  # in words she'd say: "about 2", "barely 1"
        hearts_text = ("barely 1" if hearts <= 1 else "about %d" % round(hearts)) if hearts != int(hearts) else "%d" % hearts
        close = [m for m in s.get("hostiles") or [] if m.get("distance", 99) <= 12]
        pool = LOW_HEALTH_DANGER if close else LOW_HEALTH_HUNGRY if s.get("food", 20) < 18 else LOW_HEALTH_FED
        return Alert("low_health", self.rng.choice(self.pools.get("low_health") or pool).format(hearts=hearts_text),
                     "worried")


def ambient_mood(s):
    """The mood to show when nothing else is going on."""
    if not s or "health" not in s:
        return "happy"
    if any(m.get("distance", 99) <= 12 for m in s.get("hostiles") or []) and s.get("gamemode") not in SAFE_MODES:
        return "worried"
    if s.get("health", 20) <= 8 or s.get("food", 20) <= 6:
        return "worried"
    tod = (s.get("time") or {}).get("timeOfDay", 6000) % 24000
    if 13000 <= tod <= 23000 and (s.get("where") or {}).get("skyVisible"):
        return "calm"
    return "happy"
