"""What the player is busy with: building, redstone, farming, mining, gathering wood, fighting,
crafting, from what they did over the last few minutes (Phase 4: activity understanding).

Rules, not a model: what was placed, broken, eaten, hit or gained, weighed by kind, says a lot
("placed 30 oak planks and 6 glass" is building; "placed 4 repeaters and redstone dust" is redstone;
"broke 40 deepslate and 3 iron ore" deep down is mining). It reads two kinds of input:

- the snapshot's `youDid` phrases the mod already sends ("broke 3 oak log", "placed a torch",
  "hit a zombie", "got 4 stick"; a 30-second window, at most 6 phrases), counted once even though
  every snapshot repeats them;
- structured events (`add(verb, what, n, pos)`), for the per-player activity log the playtest-fixes
  branch is adding on the world's game (blocks placed and broken, crafted, killed, ate) and for tests.

`summary()` is a short line for her prompt and for the session journal ("building with oak planks
and glass for 4 minutes, a 7x5 spot about 4 high; a little redstone"), `current()` the main activity
for expert modes and nudges. Plain Python, no I/O.
"""
import re
import time

WINDOW = 300.0  # seconds of activity that count

# what a block or item name says about the activity (checked in order; first match wins)
REDSTONE = re.compile(r"\b(redstone|repeater|comparator|piston|observer|hopper|dropper|dispenser|lever|"
                      r"button|pressure plate|daylight detector|target|tripwire|note block|powered rail|"
                      r"detector rail|activator rail|sculk sensor|crafter|redstone lamp|trapped chest)\b")
CROPS = re.compile(r"\b(wheat|carrots?|potato(es)?|beetroots?|melon|pumpkin|sugar cane|sweet berr|nether wart|"
                   r"cocoa|bamboo|cactus|seeds|sapling|farmland|bone meal|hay bale|composter|torchflower|pitcher)")
ORE = re.compile(r"\b(\w+ )?ore\b|ancient debris|raw (iron|gold|copper)|\bdiamond\b|\bemerald\b|lapis|coal\b|quartz")
STONE = re.compile(r"^(stone|deepslate|cobblestone|cobbled deepslate|tuff|andesite|diorite|granite|netherrack|"
                   r"blackstone|basalt|calcite|dripstone block|gravel|end stone|smooth basalt)$")
LOG = re.compile(r"\b(log|stem|wood|hyphae)$")
LEAVES = re.compile(r"\bleaves$")
DIRT = re.compile(r"^(dirt|grass block|sand|red sand|clay|mud|coarse dirt|rooted dirt|podzol|snow)$")
HOSTILE = re.compile(r"\b(zombie|skeleton|creeper|spider|enderman|witch|slime|phantom|drowned|husk|stray|pillager|"
                     r"vindicator|ravager|blaze|ghast|piglin brute|hoglin|magma cube|wither|warden|guardian|"
                     r"silverfish|endermite|vex|evoker|shulker|breeze|bogged|zoglin)\b")
ANIMAL = re.compile(r"\b(cow|pig|sheep|chicken|rabbit|horse|goat|llama|mooshroom|turtle|frog|camel|armadillo|"
                    r"cod|salmon)\b")

ACTIVITIES = ("building", "redstone", "farming", "mining", "wood", "fighting", "crafting", "eating")

WORDS = {
    "building": "building", "redstone": "working on redstone", "farming": "farming",
    "mining": "mining", "wood": "gathering wood", "fighting": "fighting", "crafting": "crafting",
    "eating": "eating",
}

PHRASE = re.compile(r"^(placed|broke|hit|killed|ate|used|got|crafted)\s+(?:(\d+)|an?)\s+(.+)$")


def parse_phrase(phrase):
    """'broke 3 oak log' -> ('broke', 'oak log', 3); 'placed a torch' -> ('placed', 'torch', 1)."""
    m = PHRASE.match((phrase or "").strip().lower())
    if not m:
        return None
    return m.group(1), m.group(3).strip(), int(m.group(2) or 1)


def nice(what):
    w = (what or "").lower().replace("minecraft:", "").replace("_", " ").strip()
    return w


def classify(verb, what, below_y=None):
    """The activity one action counts toward (and its weight), or (None, 0)."""
    w = nice(what)
    if verb == "placed":
        if REDSTONE.search(w):
            return "redstone", 2.0
        if CROPS.search(w):
            return "farming", 1.5
        if w in ("torch", "wall torch", "ladder", "scaffolding"):
            return "mining" if below_y else "building", 0.3
        if DIRT.match(w) and below_y is None:
            return "building", 0.5
        return "building", 1.0
    if verb == "broke":
        if CROPS.search(w):
            return "farming", 1.5
        if ORE.search(w):
            return "mining", 3.0
        if STONE.match(w):
            return "mining", 1.0 if not below_y else 1.3
        if LOG.search(w):
            return "wood", 1.2
        if LEAVES.search(w):
            return "wood", 0.2
        if DIRT.match(w):
            return "mining", 0.4
        if REDSTONE.search(w):
            return "redstone", 0.8
        return "building", 0.4  # taking apart, reshaping
    if verb in ("hit", "killed"):
        if HOSTILE.search(w):
            return "fighting", 1.5 if verb == "hit" else 3.0
        if ANIMAL.search(w):
            return "farming", 0.6
        return None, 0
    if verb in ("crafted", "got"):
        return ("crafting", 0.5) if verb == "crafted" else (None, 0)
    if verb == "ate":
        return "eating", 0.5
    if verb == "used":
        if "bone meal" in w or "hoe" in w:
            return "farming", 1.0
        return None, 0
    return None, 0


class Activity:
    """A rolling picture of what the player is doing."""

    def __init__(self, clock=time.time, window=WINDOW):
        self.clock = clock
        self.window = window
        self.events = []      # (t, verb, what, n, activity, weight, pos)
        self._seen = {}       # youDid phrase key -> last count seen (snapshots repeat the 30 s window)

    # ------------------------------------------------------------------ input

    def add(self, verb, what, n=1, pos=None, t=None, y=None):
        """One thing done (n times). pos: (x, y, z) when known (building sites, depth)."""
        t = self.clock() if t is None else t
        depth = y if y is not None else (pos[1] if pos else None)
        act, weight = classify(verb, what, below_y=(depth is not None and depth < 50) or None)
        if act:
            self.events.append((t, verb, nice(what), int(n), act, weight, pos))
        self._forget(t)

    def from_snapshot(self, snapshot):
        """Counts what's new in the snapshot's youDid phrases (each phrase repeats while in its window)."""
        now = self.clock()
        y = ((snapshot or {}).get("where") or {}).get("y")
        current = {}
        for phrase in (snapshot or {}).get("youDid") or []:
            p = parse_phrase(phrase)
            if not p:
                continue
            verb, what, n = p
            current[(verb, what)] = n
            before = self._seen.get((verb, what), 0)
            if n > before:
                self.add(verb, what, n - before, t=now, y=y)
        self._seen = current

    def _forget(self, now):
        cut = now - self.window
        while self.events and self.events[0][0] < cut:
            self.events.pop(0)

    # ------------------------------------------------------------------ reading

    def scores(self):
        self._forget(self.clock())
        s = {}
        for _, _, _, n, act, w, _ in self.events:
            s[act] = s.get(act, 0.0) + w * n
        return dict(sorted(s.items(), key=lambda kv: -kv[1]))

    def current(self, threshold=6.0):
        """The main activity now, or None (too little going on to say)."""
        s = self.scores()
        if not s:
            return None
        act, score = next(iter(s.items()))
        if act == "eating":  # eating is never what you're "doing"
            rest = [(a, v) for a, v in s.items() if a != "eating"]
            if not rest:
                return None
            act, score = rest[0]
        return act if score >= threshold else None

    def materials(self, activity, verb=None, top=3):
        counts = {}
        for _, v, what, n, act, _, _ in self.events:
            if act == activity and (verb is None or v == verb):
                counts[what] = counts.get(what, 0) + n
        return [w for w, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:top]]

    def minutes(self, activity):
        ts = [e[0] for e in self.events if e[4] == activity]
        return 0 if not ts else max(1, round((max(ts) - min(ts)) / 60))

    def site(self):
        """Where the building happens: the box around placed blocks with positions, or None."""
        pts = [e[6] for e in self.events if e[4] == "building" and e[1] == "placed" and e[6]]
        if len(pts) < 6:
            return None
        xs, ys, zs = zip(*pts)
        return {"x": (min(xs), max(xs)), "y": (min(ys), max(ys)), "z": (min(zs), max(zs)),
                "size": (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1, max(zs) - min(zs) + 1)}

    def summary(self):
        """A short line: 'building with oak planks and glass for 4 minutes (a 7x5 spot, 4 high); a little redstone'."""
        s = self.scores()
        main = self.current()
        if not main:
            return ""
        parts = []
        mats = self.materials(main, "placed" if main in ("building", "redstone", "farming") else None)
        line = WORDS[main]
        if mats:
            line += " with " + " and ".join(mats[:2]) if main == "building" else " (" + ", ".join(mats) + ")"
        mins = self.minutes(main)
        if mins >= 2:
            line += " for %d minutes" % mins
        if main == "building":
            site = self.site()
            if site:
                w, h, l = site["size"]
                line += " (a %dx%d spot, %d high)" % (w, l, h)
        parts.append(line)
        for act, score in list(s.items())[1:3]:
            if act in ("eating",) or score < 3:
                continue
            parts.append(("a little " if score < 8 else "") + WORDS[act].replace("working on ", ""))
        return "; ".join(parts)
