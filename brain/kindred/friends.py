"""Her heart for each other person: friends on your LAN world, by name.

The player she lives with stays first: the bond, the stance, everything in heart.py and bonds.py. But
she meets your friends too, and she isn't the same with each of them. Each friend gets the same five
feelings (affection, trust, respect, familiarity, resentment, see bonds.py), moved by how *they* treat
her: what they say to her in chat (the AI's regard tag for their words), hitting or petting her (their
game reports it), thanks. Lighter than with you (she lives with you; they visit), and kept with her
heart across sessions, so the kind one stays a friend and the mean one stays someone she's wary of.

Witnessing: when a friend is mean to her or hits her and you're there, she watches what *you* do.
Step in ("stop hitting Pip", "leave her alone") within about 20 seconds and she trusts you a bit more;
say nothing and it costs a little trust ("you let them"), logged with why. Small on purpose: you can't
always see what happens in chat.

Trust at your word: "from now on, do what Robin says" lets that friend ask her to follow them or stay.

Everything here works on plain dicts saved inside her heart's state ("friends").
"""
import random

from . import bonds as B

WEIGHT = 0.6            # how much a friend's words and touches count, next to yours
WITNESS_SECONDS = 20.0  # how long she waits to see whether you stand up for her
REGARD_EVENTS = {"sweet": "sweet", "kind": "kind", "thanks": "thanks", "rude": "rude", "mean": "mean",
                 "threat": "threat", "dismissive": "dismissive", "frustrated": "frustrated"}
# what happens to her heart for YOU when someone else hurts her while you're there
B.EVENTS.setdefault("defended", (2, 2, 1.5, -1, 0, 0))       # you stood up for her
B.EVENTS.setdefault("let_them", (-0.5, -2, -0.5, 1, 0.1, 0.4))  # you said nothing (a small incident, logged)


def key(name):
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


class Friends:
    def __init__(self, state, clock, rng=None):
        self.s = state                  # {"people": {key: {...}}, "watch": [...]}
        self.s.setdefault("people", {})
        self.s.setdefault("watch", [])
        self.clock = clock
        self.rng = rng or random.Random()

    # ------------------------------------------------------------------ who

    def person(self, name, create=True):
        k = key(name)
        if not k:
            return None
        p = self.s["people"].get(k)
        if p is None and create:
            now = self.clock()
            p = self.s["people"][k] = {"name": name, "rel": B.fresh(32, "default", self.rng, now), "met": now,
                                       "last": now, "trusted": False, "said": 0}
        return p

    def find(self, said):
        """A friend she knows, by a name said roughly ("robin" for riverrobin)."""
        from .intents import same_person
        k = key(said)
        if k in self.s["people"]:
            return self.s["people"][k]
        return next((p for p in self.s["people"].values() if same_person(said, p["name"])), None)

    def names(self):
        return [p["name"] for p in self.s["people"].values()]

    def bonds(self, name):
        p = self.person(name)
        return B.Bonds(p["rel"]) if p else None

    # ------------------------------------------------------------------ what they do to her

    def regard(self, name, tag, words=""):
        """How a friend's chat line treated her (the AI's tag), appraised by her heart for them."""
        p = self.person(name)
        if not p:
            return {}
        now = self.clock()
        p["last"], p["said"] = now, p.get("said", 0) + 1
        rel = B.Bonds(p["rel"])
        rel.familiar_moment(now, 0.5)
        tag = (tag or "neutral").lower()
        if tag == "teasing":
            return rel.impress("banter", now, words, scale=WEIGHT * 0.5, why="%s teasing" % p["name"])
        event = REGARD_EVENTS.get(tag)
        return rel.impress(event, now, words, scale=WEIGHT, why=p["name"]) if event else {}

    def touched(self, name, what):
        """A friend hit or petted her (their game told the world's game, which told her)."""
        p = self.person(name)
        if not p:
            return {}
        now = self.clock()
        p["last"] = now
        rel = B.Bonds(p["rel"])
        if what == "petted":
            return rel.impress("pet", now, scale=WEIGHT, why="%s petted you" % p["name"])
        hits = [t for t in p.setdefault("hits", []) if now - t < 30] + [now]
        p["hits"] = hits
        event = "hit_deliberate" if len(hits) >= 2 else "hit_careless"
        return rel.impress(event, now, scale=WEIGHT, why="%s hit you" % p["name"])

    # ------------------------------------------------------------------ you, watching

    def witness(self, friend, what):
        """Someone hurt her in front of you: she waits a little to see what you do."""
        now = self.clock()
        self.s["watch"] = [w for w in self.s["watch"] if now - w["t"] < WITNESS_SECONDS * 3] + [
            {"friend": friend, "what": (what or "")[:80], "t": now}]

    def watching(self):
        return [w for w in self.s["watch"] if self.clock() - w["t"] <= WITNESS_SECONDS]

    def defended(self):
        """You stood up for her: everything she was watching is settled, kindly. Returns who it was about."""
        now = self.clock()
        open_ = [w for w in self.s["watch"] if now - w["t"] <= WITNESS_SECONDS]
        self.s["watch"] = [w for w in self.s["watch"] if w not in open_]
        return open_

    def let_them(self):
        """What you didn't step in for (older than the wait). Returns them, and forgets them."""
        now = self.clock()
        late = [w for w in self.s["watch"] if now - w["t"] > WITNESS_SECONDS]
        self.s["watch"] = [w for w in self.s["watch"] if w not in late]
        return late

    # ------------------------------------------------------------------ at your word

    def trust(self, name, yes=True):
        p = self.person(name)
        if p:
            p["trusted"] = bool(yes)

    def trusted(self, name):
        p = self.find(name)
        return bool(p and p.get("trusted"))

    # ------------------------------------------------------------------ in words

    def guidance(self, name):
        """How she feels about this friend, in words for the AI (no numbers)."""
        p = self.find(name)
        if not p:
            return "You've just met %s." % name
        now = self.clock()
        rel = B.Bonds(p["rel"])
        st = rel.stance(now)
        feel = {
            "new": "You don't know %s yet: curious, polite, a little watchful.",
            "warm": "You like %s and feel safe with them: warm, playful, you tease them like a friend.",
            "easy": "You're easy with %s.",
            "guarded": "You like %s, but you're a bit wary of them.",
            "reliant": "You can count on %s, but you're not especially fond of them right now.",
            "wounded": "You like %s, and they've hurt you: you're quieter with them and you may bring it up.",
            "cold": "You don't like or trust %s right now: short and cool with them, no favours offered.",
            "bitter": "You resent %s: they've hurt you again and again. Prickly and short with them (never cruel).",
        }.get(st, "You know %s a little.") % p["name"]
        ev = rel.evidence(now)
        if ev:
            ev = ev.replace("They ", p["name"] + " ", 1).replace("they ", p["name"] + " ", 1)
        return feel + ((" " + ev) if ev else "")

    def explain(self):
        """For the dashboard: one card per friend."""
        now = self.clock()
        out = []
        for p in sorted(self.s["people"].values(), key=lambda p: -p.get("last", 0)):
            e = B.Bonds(p["rel"]).explain(now)
            e.update({"name": p["name"], "trusted": bool(p.get("trusted")), "met": p.get("met"), "last": p.get("last")})
            out.append(e)
        return out
