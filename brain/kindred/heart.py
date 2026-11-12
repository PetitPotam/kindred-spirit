"""Pip's heart: who she is with you. Everything here is a setting in brain.toml [heart].

  bond         0-100, how close she feels to you. Kindness raises it, rudeness and hitting her
               lower it; bad moments fade (she forgives quickly) and an apology helps a lot. The
               closer she feels, the closer she floats, the more she opens up, asks about you and
               suggests things; when hurt she keeps her distance, sulks, and may vanish for a while.
  discovery    "amnesia": she doesn't know her powers. When you ask for something she tries, and
               the first success surprises her. Discovered powers are remembered.
  requests     "always protect me", "tell me when we're near diamonds": standing rules she follows.
               If you asked for help once, next time she offers ("Want me to push them away?").
  curiosity    she notices advancements, first-time items, new biomes, deaths, mining sprees, and
               muses about little things in her own dreamy world when it's quiet.
  pranks       once you're friends: a creeper hiss behind you in a dark mine, a block that goes
               missing (it's in your inventory). When she's angry she can really mess with you
               (mischief_when_angry: off, mild, spicy), always reversible: nothing is destroyed.
"""
import random
import time

LEVELS = [(0, "hurt"), (15, "wary"), (35, "friend"), (65, "close"), (85, "best friend")]

# how a message changes the bond (the AI tags each message it answers)
REGARD = {"sweet": 4, "kind": 2, "neutral": 0, "rude": -5, "mean": -12, "sorry": 6}

GUIDANCE = {
    "hurt": "You feel hurt by how the player treated you. Keep your answers short and a bit cold, keep your "
            "distance, and don't offer help or do favours until they're kind or apologize. You still have your "
            "pride. If they apologize, you forgive quickly.",
    "wary": "You don't know the player well yet. Be polite and curious but a little reserved; you don't open up "
            "much and you don't propose plans.",
    "friend": "You like the player. Be warm and playful, ask about what they do and about them, share your little "
              "thoughts about the world.",
    "close": "You feel close to the player. Open up: share your feelings and dreams, ask about their life, and "
             "sometimes propose a little shared goal based on what you know about them.",
    "best friend": "The player is your best friend. You're affectionate and open, you tease them gently, and you "
                   "come up with plans and little adventures for the two of you based on their needs.",
}

HIT_LINES = ["Ow! Hey!", "Ouch! Why would you do that?", "Hey, that hurts!", "Stop it!"]
VANISH_LINES = ["I need a moment alone.", "Fine. I'm going away for a bit.", "I don't want to be near you right now."]
BACK_LINES = ["...I'm back. Please be nicer.", "Okay. I'm back. Let's start over?", "I came back. Be gentle, okay?"]
GIGGLES = ["Hehehe! Got you!", "Pfft, your face! It was just me!", "Hehe, gotcha! Sorry, I couldn't resist.",
           "Boo! Hehe, it was me all along!"]
SULK_PRANKS = ["Hmph. That's what you get.", "Maybe now you'll be nicer.", "Oh no, how did that happen? Hmph."]
BLOCK_PRANK = ["Hmm? Where did your block go? Hehe~", "Oops! Your block is... somewhere. Check your pockets!",
               "A block was here a second ago. Strange, isn't it?"]
OFFERS = {"protect": "Want me to push them away?", "find_ore": "Want me to look for %s around here?"}


def level_of(bond):
    name = LEVELS[0][1]
    for threshold, n in LEVELS:
        if bond >= threshold:
            name = n
    return name


class Heart:
    def __init__(self, cfg, memory=None, clock=time.time, rng=None):
        self.p = cfg.get("heart", {})
        self.memory = memory
        self.clock = clock
        self.rng = rng or random.Random()
        self.state = {"bond": float(self.p.get("start_bond", 30)), "discovered": [], "asked": {}, "seen_items": [],
                      "requests": [], "last_prank": 0, "hurt_until": 0}
        self.hits = []
        self.pending_offer = None
        self.last_offer = {}
        self.last_change = 0.0

    # ------------------------------------------------------------------ persistence (a memory document)

    async def load(self):
        if self.memory is None:
            return
        try:
            saved = (await self.memory.store.call("doc", key="heart")).get("value")
        except Exception:
            saved = None
        if saved:
            self.state.update(saved)

    async def save(self):
        if self.memory is None:
            return
        try:
            await self.memory.store.call("doc", key="heart", value=self.state)
        except Exception:
            pass

    # ------------------------------------------------------------------ bond

    @property
    def bond(self):
        return self.state["bond"]

    def level(self):
        return level_of(self.bond)

    def closeness(self):
        """0 = keeps far away, 1 = snuggles up. Hurt also pushes her away for a while."""
        c = min(1.0, max(0.0, self.bond / 100))
        if self.clock() < self.state.get("hurt_until", 0):
            c = min(c, 0.1)
        return round(c, 2)

    def angry(self):
        return self.bond < 15 or self.clock() < self.state.get("hurt_until", 0)

    def change(self, delta, why=""):
        old = self.bond
        self.state["bond"] = max(0.0, min(100.0, old + delta))
        self.last_change = self.clock()
        return self.state["bond"] - old

    def on_regard(self, tag):
        delta = REGARD.get((tag or "neutral").lower(), 0)
        if delta < 0:
            self.state["hurt_until"] = self.clock() + (120 if tag == "mean" else 45)
        elif tag == "sorry":
            self.state["hurt_until"] = 0  # quick to forgive
        return self.change(delta, tag)

    def on_hit(self):
        """Returns (bond change, line to say, vanish seconds or 0)."""
        now = self.clock()
        self.hits = [t for t in self.hits if now - t < 60] + [now]
        delta = self.change(-6, "hit")
        self.state["hurt_until"] = now + 90
        if len(self.hits) >= 3 and self.p.get("can_vanish", True):
            self.hits = []
            return delta, self.rng.choice(VANISH_LINES), 90 + self.rng.randint(0, 60)
        return delta, self.rng.choice(HIT_LINES), 0

    def on_pet(self):
        return self.change(1.5, "pet")

    def drift(self, minutes):
        """Time heals: below a friendly baseline the bond slowly comes back (she forgets quickly)."""
        if self.bond < 40 and self.clock() > self.state.get("hurt_until", 0):
            return self.change(min(40 - self.bond, 1.0 * minutes), "time")
        return 0

    def guidance(self):
        lvl = self.level()
        g = "Your bond with the player: %s (%d/100). %s" % (lvl, round(self.bond), GUIDANCE[lvl])
        if self.clock() < self.state.get("hurt_until", 0) and lvl not in ("hurt",):
            g += " Right now you're still a bit upset about how they just treated you."
        return g

    # ------------------------------------------------------------------ discovering powers

    def amnesia(self):
        return bool(self.p.get("amnesia", True))

    def offered_tools(self, abilities, hint=None):
        """Which powers the AI may use now: everything allowed, or (amnesia) what she has discovered
        plus the one the player is asking for right now (she tries it)."""
        if not self.amnesia():
            return list(abilities)
        out = [a for a in abilities if a in self.state["discovered"]]
        if hint and hint in abilities and hint not in out:
            out.append(hint)
        if "guide" in out and "stop_guide" in abilities and "stop_guide" not in out:
            out.append("stop_guide")
        return out

    def discovery_note(self, abilities):
        if not self.amnesia():
            return ""
        known = [a for a in self.state["discovered"] if a in abilities]
        return ("You don't really know what you're capable of. You discover your powers only when the player asks "
                "you for something: then you simply try. Never list powers or commands. Powers you've discovered so "
                "far: %s." % (", ".join(k.replace("_", " ") for k in known) or "none yet"))

    def discovered(self, ability):
        """True the first time a power works."""
        self.state["asked"][ability] = self.state["asked"].get(ability, 0) + 1
        if ability in self.state["discovered"]:
            return False
        self.state["discovered"].append(ability)
        self.change(1, "discovery")
        return True

    # ------------------------------------------------------------------ standing requests and offers

    def add_request(self, what, detail=""):
        req = {"what": what, "detail": detail}
        if req not in self.state["requests"]:
            self.state["requests"].append(req)
        return req

    def drop_request(self, what):
        before = len(self.state["requests"])
        self.state["requests"] = [r for r in self.state["requests"] if r["what"] != what]
        return before - len(self.state["requests"])

    def wants(self, what):
        if what == "protect" and self.p.get("auto_protect", False):
            return {"what": "protect"}
        return next((r for r in self.state["requests"] if r["what"] == what), None)

    def offer(self, what, now, detail=""):
        """Offer help she gave before, at most every 2 minutes per kind, never when she's upset."""
        if self.angry() or self.state["asked"].get(what, 0) < 1 or now - self.last_offer.get(what, -1e9) < 120:
            return None
        self.last_offer[what] = now
        self.pending_offer = {"what": what, "detail": detail, "until": now + 25}
        text = OFFERS.get(what, "Want me to help?")
        return text % detail if "%s" in text else text

    def take_offer(self, now):
        o = self.pending_offer
        self.pending_offer = None
        return o if o and now <= o["until"] else None

    # ------------------------------------------------------------------ curiosity

    def notice(self, event, detail, snapshot):
        """What she'd like to say about something that happened (an instruction for the AI), or None."""
        if not self.p.get("curiosity", True):
            return None
        if event == "advancement":
            return ("The player just earned the advancement \"%s\". React with genuine delight or curiosity in one "
                    "short sentence; maybe ask how they did it." % detail)
        if event == "new_item":
            seen = self.state["seen_items"]
            if detail in seen:
                return None
            seen.append(detail)
            del seen[:-300]
            if self.rng.random() > 0.35:  # don't comment on every new thing
                return None
            return ("The player just got %s for the first time since you've known them. Be curious about it in one "
                    "short, whimsical sentence." % detail.replace("minecraft:", "").replace("_", " "))
        if event == "biome":
            return ("You've just arrived in a %s. Share one little dreamy observation about it, in one short "
                    "sentence." % detail.replace("minecraft:", "").replace("_", " "))
        if event == "death":
            return "The player just died. Be worried and sweet about it in one short sentence."
        if event == "mining":
            return "The player has been mining for a while. Say one little thing about it, or about what you see down here."
        if event == "building":
            return "The player is building something. Be curious: ask what it is, in one short sentence."
        return None

    def musing(self):
        """When it's quiet: a thought from her own little world, or a question about the player."""
        lvl = self.level()
        if lvl == "hurt":
            return None
        options = [
            "Muse about one small, mundane thing around you in your own dreamy way (a flower, the clouds, a pig, the "
            "sound of the wind). One short sentence.",
            "Wonder out loud about something in your world you've always been curious about. One short sentence.",
            "Ask the player, kindly, what they've been up to or how their day is going. One short sentence.",
        ]
        if lvl in ("close", "best friend"):
            options += ["Share a little feeling or dream of yours with the player. One or two short sentences.",
                        "Propose a little shared goal or adventure based on what you know about the player and their "
                        "needs. One or two short sentences."]
        elif lvl == "wary":
            options = options[:2]
        return self.rng.choice(options)

    # ------------------------------------------------------------------ pranks and mischief

    def mischief(self):
        return str(self.p.get("mischief_when_angry", "spicy")).lower()

    def prank(self, snapshot, idle_seconds, mining, placed_recently, now):
        """Maybe a prank right now: returns {"action": ..., "args": ..., "line": ...} or None."""
        if not snapshot or "health" not in snapshot or snapshot.get("health", 0) < 12:
            return None
        if any(m.get("distance", 99) < 16 for m in snapshot.get("hostiles") or []):
            return None  # never while there's real danger
        angry = self.angry() and self.mischief() != "off"
        friendly = self.p.get("pranks", True) and self.bond >= 55
        if not (angry or friendly):
            return None
        cooldown = 240 if angry else 900
        if now - self.state.get("last_prank", 0) < cooldown:
            return None
        where = snapshot.get("where") or {}
        dark = not where.get("skyVisible", True) and where.get("light", 15) < 8
        mood_for_it = dark or mining or 40 < idle_seconds < 120 or (placed_recently and self.p.get("block_pranks", True))
        if not mood_for_it or self.rng.random() > (0.5 if angry else 0.25):
            return None
        self.state["last_prank"] = now
        if placed_recently and self.p.get("block_pranks", True) and (not angry or self.mischief() == "spicy"):
            return {"action": "steal_block", "args": {},
                    "line": self.rng.choice(SULK_PRANKS if angry else BLOCK_PRANK)}
        kind = self.rng.choice(["creeper", "explosion"] if dark or mining else ["creeper"])
        return {"action": "prank_sound", "args": {"sound": kind},
                "line": self.rng.choice(SULK_PRANKS if angry else GIGGLES)}
