"""Expert modes: survival, redstone, builder, speedrun (Phase 4).

A mode changes what she pays attention to and how she helps, not who she is: the same Pip, more
useful for what you're doing. Each mode is a few lines of guidance for her prompt, what to look up in
the knowledge base when you ask, which of her comments to keep or drop, and (speedrun) splits.

- **auto** (default): the mode follows what you're doing (activity.py): building → builder hints,
  redstone → redstone, otherwise survival. Never speedrun by itself: you say so.
- You can set one ("Pip, speedrun mode", "help me with redstone"), and switch back ("normal mode").

Splits for speedruns come from what the game already tells her (dimension changes, items gained,
advancements when the snapshot carries them): Nether, fortress (blaze rods), pearls, eyes of ender,
stronghold, the End, the dragon. Plain Python; wiring into her prompt and System 0's words waits for
the playtest-fixes branch (mind.py, intents.py).
"""
import re
import time

MODES = {
    "survival": {
        "title": "survival helper",
        "guidance": (
            "Help them stay alive and get ahead: food and health, light and shelter before night, the next "
            "tool or armor worth making, what they could do with what they carry. One useful tip at a time, "
            "when it fits."),
        "lookup": ("crafting", "food", "mob", "tool", "armor"),
        "quiet": (),
    },
    "redstone": {
        "title": "redstone partner",
        "guidance": (
            "They're working on redstone. Think like an engineer friend: signal strength (15 blocks), repeater "
            "delay in ticks, comparators (compare or subtract), quasi-connectivity of pistons, observers and "
            "update order. Explain why a circuit does what it does, suggest the smallest change that fixes it, "
            "and only what you know is true for Java 1.21.1."),
        "lookup": ("redstone", "repeater", "comparator", "piston", "observer", "hopper", "tutorial:redstone"),
        "quiet": ("small_talk",),
    },
    "builder": {
        "title": "building buddy",
        "guidance": (
            "They're building. Notice shapes and materials, suggest a detail that would make it nicer (depth in "
            "walls, a roof overhang, a palette that fits the biome, light inside so nothing spawns), offer to "
            "help build or to remember it when it's done. Don't criticise; be delighted and specific."),
        "lookup": ("building", "block", "tutorial:building"),
        "quiet": (),
    },
    "speedrun": {
        "title": "speedrun coach",
        "guidance": (
            "They're speedrunning: be brief and fast. Say the next objective and the time, call out danger, "
            "no chit-chat, no questions back. Standard route: wood and stone tools, iron, a portal (lava pool "
            "or ruined portal), the Nether: bastion for pearls or barter, fortress for blaze rods (6-7), eyes "
            "of ender (12 at most), triangulate the stronghold, the End, the dragon."),
        "lookup": ("speedrun", "blaze", "ender pearl", "eye of ender", "stronghold", "bartering"),
        "quiet": ("small_talk", "noticed", "curiosity", "urges", "pranks"),
    },
}

ALIASES = {
    "survival": ("survival", "normal", "default", "regular", "help me survive"),
    "redstone": ("redstone", "engineer", "circuits", "technical"),
    "builder": ("builder", "building", "build mode", "architect"),
    "speedrun": ("speedrun", "speed run", "speedrunning", "coach"),
    "auto": ("auto", "automatic", "whatever i'm doing"),
}

MODE_WORDS = re.compile(r"\b(?:(\w[\w ]*?) mode|mode (?:to )?(\w+)|help me with (redstone|building)|"
                        r"(?:let'?s|i'?m going to|i want to) (speedrun|speed ?run))\b", re.I)


def asked_mode(text):
    """The mode a player's words ask for, or None: 'Pip, speedrun mode' -> 'speedrun'."""
    t = (text or "").lower()
    m = MODE_WORDS.search(t)
    if not m:
        return None
    said = next(g for g in m.groups() if g).strip()
    for mode, words in ALIASES.items():
        if any(said == w or said.endswith(" " + w) or w in said for w in words):
            return mode
    return None


def effective(mode, activity_now):
    """The mode in force: an explicit one, else what the activity suggests (auto)."""
    if mode and mode != "auto":
        return mode
    if activity_now == "redstone":
        return "redstone"
    if activity_now == "building":
        return "builder"
    return "survival"


def guidance(mode, activity_now=None):
    m = MODES[effective(mode, activity_now)]
    return "Right now you're their %s. %s" % (m["title"], m["guidance"])


def allows(mode, comment_kind, activity_now=None):
    """Whether a comment of hers of this kind fits the mode (speedrun keeps only what matters)."""
    return comment_kind not in MODES[effective(mode, activity_now)]["quiet"]


def lookup_terms(mode, activity_now=None):
    return MODES[effective(mode, activity_now)]["lookup"]


# ---------------------------------------------------------------------- speedrun splits

SPLITS = (
    ("nether", "entered the Nether"),
    ("blaze_rods", "6 blaze rods"),
    ("pearls", "12 ender pearls (or eyes)"),
    ("eyes", "eyes of ender ready"),
    ("end", "entered the End"),
    ("dragon", "the dragon is down"),
)


class Splits:
    """Times of the classic any% milestones, from snapshots (dimension, inventory, advancements)."""

    def __init__(self, clock=time.time):
        self.clock = clock
        self.start = None
        self.times = {}

    def begin(self):
        self.start, self.times = self.clock(), {}

    def update(self, snapshot):
        """Returns the splits reached by this snapshot: [(key, words, seconds since start)]."""
        if self.start is None or not snapshot:
            return []
        inv = snapshot.get("inventory") or {}
        dim = (snapshot.get("where") or {}).get("dimension", "")
        adv = set(snapshot.get("advancements") or [])
        eyes = inv.get("minecraft:ender_eye", 0)
        reached = {
            "nether": dim == "minecraft:the_nether",
            "blaze_rods": inv.get("minecraft:blaze_rod", 0) + eyes // 2 >= 6,
            "pearls": inv.get("minecraft:ender_pearl", 0) + eyes >= 12,
            "eyes": eyes >= 12,
            "end": dim == "minecraft:the_end",
            "dragon": "minecraft:end/kill_dragon" in adv,
        }
        out = []
        for key, words in SPLITS:
            if reached[key] and key not in self.times:
                self.times[key] = self.clock() - self.start
                out.append((key, words, self.times[key]))
        return out

    def next_objective(self):
        for key, words in SPLITS:
            if key not in self.times:
                return words
        return None

    @staticmethod
    def clock_text(seconds):
        m, s = divmod(int(seconds), 60)
        return "%d:%02d" % (m, s)
