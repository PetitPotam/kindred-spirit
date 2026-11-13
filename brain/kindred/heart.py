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
import re
import time

LEVELS = [(0, "hurt"), (15, "wary"), (35, "friend"), (65, "close"), (85, "best friend")]

# how a message changes the bond (the AI tags each message it answers)
REGARD = {"sweet": 4, "kind": 2, "neutral": 0, "rude": -5, "mean": -12, "sorry": 6, "frustrated": -1}

# what events do to her feelings: (valence = how good she feels, arousal = how stirred up)
FEELINGS = {
    "sweet": (0.35, 0.15), "kind": (0.15, 0.05), "rude": (-0.35, 0.2), "mean": (-0.6, 0.35), "sorry": (0.3, 0.0),
    "frustrated": (-0.15, 0.1), "hit": (-0.45, 0.45), "pet": (0.25, 0.05), "danger": (-0.2, 0.6),
    "discovery": (0.35, 0.35), "found": (0.25, 0.3), "advancement": (0.3, 0.3), "baby": (0.45, 0.3),
    "killed_villager": (-0.7, 0.3), "kill_spree": (-0.45, 0.2), "tamed": (0.35, 0.25), "first_meet": (0.2, 0.35),
    "arrived": (0.3, 0.25), "annoyed": (-0.25, 0.3), "doubt": (-0.12, 0.15), "jealous": (-0.1, 0.1),
}

GUIDANCE = {
    # how close you are changes how much of herself she shows, not how much she needs you
    "hurt": "You're hurt by how the player treated you. Short and cool with them, you keep your distance and do no "
            "favours until they're kind or say sorry. You still have your pride; when they truly mean sorry, you "
            "forgive fast.",
    "wary": "You don't know the player well yet. Curious about them, but watchful and a little guarded: you're more "
            "interested in the world than in them for now, and you don't make plans together yet.",
    "friend": "You like the player. Playful and chatty: you share what you notice and think, tease a little, and "
              "wander off on your own tangents.",
    "close": "You feel close to the player and comfortable with them: you tease, you share your odd thoughts and old "
             "flashes, you disagree freely, and sometimes you drag them into one of your little ideas.",
    "best friend": "The player is your favourite person in this world, though you'd never say it that plainly. You're "
                   "fully yourself with them: cheeky, honest, weird, a bit bossy. You make plans and drag them on "
                   "adventures, and you show you care by what you do.",
}

HIT_LINES = ["Ow! Hey!", "Ouch! Why would you do that?", "Hey, that hurts!", "Stop it!"]
OOF_LINES = ["Oof! Hey, watch it!", "Eep! Careful with those arms!", "Ow! Was that on purpose?"]
BONK_LINES = ["Hey! Take that! Hehe!", "Bonk! Now we're even!", "Ha! Got you back!"]
PLAY_HIT_LINES = ["Bonk! Hehe, gotcha! Oh no, sorry sorry, let me fix that!", "Boop! Oops, too hard? Here, all better!",
                  "Tag, you're it! Oh, sorry! Here, let me heal you!"]
CRY_LINES = ["*sniff* ...", "I just... need a moment.", "Why would you say that..."]
CLEAR_LINES = ["Okay. The sun's coming back out.", "There, the clouds are going away.", "I feel better now. Look, sunshine!"]
VANISH_LINES = ["I need a moment alone.", "Fine. I'm going away for a bit.", "I don't want to be near you right now."]
BACK_LINES = ["...I'm back. Please be nicer.", "Okay. I'm back. Let's start over?", "I came back. Be gentle, okay?"]
GIGGLES = ["Hehehe! Got you!", "Pfft, your face! It was just me!", "Hehe, gotcha! Sorry, I couldn't resist.",
           "Boo! Hehe, it was me all along!"]
SULK_PRANKS = ["Hmph. That's what you get.", "Maybe now you'll be nicer.", "Oh no, how did that happen? Hmph."]
BLOCK_PRANK = ["Hmm? Where did your block go? Hehe~", "Oops! Your block is... somewhere. Check your pockets!",
               "A block was here a second ago. Strange, isn't it?"]
# powers that wake up slowly the first time (the others are instinct: they work at once)
SLOW_POWERS = ("find_ore", "find_animal", "locate", "give_item", "set_time", "set_weather", "harvest")
POWER_NAMES = {"find_ore": "sense ores hidden underground", "find_animal": "feel where animals are, even far away",
               "harvest": "make wood and stone come loose with your magic",
               "locate": "feel where faraway places are",
               "give_item": "make things appear out of nothing", "give_effect": "pour a little magic into someone",
               "find_player": "feel where someone is", "follow_player": "stay with someone", "set_time": "move the sun across the sky",
               "set_weather": "change the weather", "protect": "push monsters away",
               "place_torch": "make light appear", "guide": "lead the way"}
SENSES = {"find_ore": "a faint humming under the ground, like little stars glittering in the rock",
          "find_animal": "tiny heartbeats all around, far away, like little drums in the grass",
          "harvest": "the wood and the stone hum, as if they'd come loose if you asked them nicely",
          "locate": "a gentle pull from far away, like a string tied to places you've never been",
          "give_item": "a warm tingle in your middle, as if things want to come out of you",
          "set_time": "the sky feels movable, as if the sun is listening to you",
          "set_weather": "the clouds feel close, as if they'd listen if you asked them nicely"}
# small favours she may ask so the feeling gets stronger; each one the game can check
FAVOURS = {"still": "Ask the player, a little mysteriously, to stand completely still for a few seconds so you can "
                    "listen.",
           "pet": "Ask the player, a bit shyly, to pet you (touch you gently), so you can focus.",
           "name": "Ask the player to say your name out loud, so the feeling gets stronger."}
# questions about her: what she is, where she comes from, what she likes (they make her reflect)
ABOUT_HER = re.compile(r"\b(who are you|what are you|where (do|did) you come from|your (origin|past|family|parents|"
                       r"home|story)|are you (real|alive|a ghost|a spirit)|why are you here|who made you|what do you "
                       r"(want|like|love|hate|feel|dream)|tell me about (yourself|you)|do you (have|remember) )", re.I)
# the player sharing about themselves
ABOUT_THEM = re.compile(r"\b(i am|i'm|my name|my (job|family|life|favourite|favorite|dream)|i (love|like|hate|work|"
                        r"live|study|grew up|feel))\b", re.I)

OFFERS = {"protect": "Want me to push them away?", "find_ore": "Want me to look for %s around here?"}


def level_of(bond):
    name = LEVELS[0][1]
    for threshold, n in LEVELS:
        if bond >= threshold:
            name = n
    return name


from . import bonds as B  # noqa: E402

# how the AI's judgement of a message becomes an event for her heart (bonds.py)
REGARD_EVENTS = {"sweet": "sweet", "kind": "kind", "thanks": "thanks", "rude": "rude", "mean": "mean", "cruel": "mean",
                 "threat": "threat", "dismissive": "dismissive", "frustrated": "frustrated"}
FEEL_AS = {"thanks": "kind", "teasing": "kind", "dismissive": "frustrated", "threat": "mean", "cruel": "mean",
           "sorry_real": "sorry"}


class Heart:
    def __init__(self, cfg, memory=None, clock=time.time, rng=None):
        self.p = cfg.get("heart", {})
        self.memory = memory
        self.clock = clock
        self.rng = rng or random.Random()
        self.state = self.fresh()
        self.valence, self.arousal, self.novelty = 0.25, 0.35, 0.0
        self.danger_until = 0.0
        self.feel_at = clock()
        self.hits = []
        self.said, self.word_gains, self.annoyed_until, self.repeats = [], [], 0.0, 0  # repeated words (hear)
        self.known_self = 0      # how much she knows about herself (origin + self memories), set by the brain
        self.shared = []         # when the player shared things about themselves (jealousy)
        self.jealous_at = -1e9
        self.asked_about_her = False
        self.flooding = False
        self.pending_offer = None
        self.last_offer = {}
        self.last_change = 0.0
        self._rel, self._bond_seen = None, None

    # ------------------------------------------------------------------ persistence (a memory document)

    def fresh(self):
        start = float(self.p.get("start_bond", 30))
        return {"bond": start, "discovered": [], "asked": {}, "seen_items": [],
                "requests": [], "last_prank": 0, "hurt_until": 0, "seen_species": [], "sorries": [],
                "hits": [], "rained": False,
                "rel": B.fresh(start, str(self.p.get("temperament", "default")), self.rng, self.clock())}

    @property
    def rel(self):
        """Her relationship with you (bonds.py): five feelings, the sting, the incident ledger."""
        if "rel" not in self.state:  # an old save: one bond number becomes the five feelings
            self.state["rel"] = B.fresh(self.state.get("bond", 30), str(self.p.get("temperament", "default")),
                                        self.rng, self.clock())
            B.Bonds(self.state["rel"]).set_bond(self.state.get("bond", 30))
        if self._rel is None or self._rel.s is not self.state["rel"]:
            self._rel, self._bond_seen = B.Bonds(self.state["rel"]), None
        return self._rel

    def key(self):
        """Where her heart is saved: one per world, or one for all worlds."""
        m = self.memory
        return "world:%s:heart" % m.world_id if m is not None and getattr(m, "per_world", False) else "heart"

    async def load(self):
        """Her heart for the world we're in (a new world with its own companion: a new heart)."""
        self.state = self.fresh()
        self.hits, self.pending_offer, self.last_offer = [], None, {}
        if self.memory is None:
            return
        try:
            saved = (await self.memory.store.call("doc", key=self.key())).get("value")
        except Exception:
            saved = None
        if saved:
            self.state.update(saved)
            if "rel" not in saved:  # migrate: what she knows of you, and old wounds, carry over
                rel = B.fresh(saved.get("bond", 30), str(self.p.get("temperament", "default")), self.rng, self.clock())
                rel["f"] = rel["f_peak"] = await self._familiarity_from_memories()
                rel["g"] = await self._old_wounds()
                self.state["rel"] = rel
                B.Bonds(rel).set_bond(saved.get("bond", 30))
        self.rel.session_start(self.clock())

    async def _familiarity_from_memories(self):
        try:
            rows = (await self.memory.store.call("list", kinds=["player", "episode", "diary"],
                                                 world=self.memory.world_id, limit=200))["results"]
            return float(min(60, len(rows) / 2))
        except Exception:
            return 0.0

    async def _old_wounds(self):
        try:
            rows = (await self.memory.store.call("list", kinds=["core"], world=self.memory.world_id, limit=50))["results"]
            return float(min(60, 15 * sum(1 for r in rows if (r.get("meta") or {}).get("pain")
                                           and not (r.get("meta") or {}).get("healed"))))
        except Exception:
            return 0.0

    async def save(self):
        if self.memory is None:
            return
        try:
            await self.memory.store.call("doc", key=self.key(), value=self.state)
        except Exception:
            pass

    # ------------------------------------------------------------------ bond

    @property
    def bond(self):
        """The heart meter: derived from her five feelings (set from outside = an old save or a test)."""
        r = self.rel
        if self._bond_seen is not None and abs(self.state.get("bond", self._bond_seen) - self._bond_seen) > 1e-6:
            r.set_bond(self.state["bond"])
        b = r.bond()
        self.state["bond"] = self._bond_seen = b
        return b

    def stance(self):
        return self.rel.stance(self.clock())

    def level(self):
        return level_of(self.bond)

    def closeness(self):
        """0 = keeps far away, 1 = snuggles up: someone she likes AND feels safe with; a sting pushes her away."""
        self.bond  # (picks up a bond set from outside)
        return self.rel.closeness(self.clock())

    def angry(self):
        now = self.clock()
        return self.bond < 15 or self.rel.sting(now) > 0.35 or self.rel.s["g"] >= 40

    def change(self, delta, why=""):
        """Moves the old single bond (old code paths, tests): affection and trust together."""
        old = self.bond
        self.rel.set_bond(max(0.0, min(100.0, old + delta)))
        self.state["bond"] = self._bond_seen = self.rel.bond()
        self.last_change = self.clock()
        return self.state["bond"] - old

    # ------------------------------------------------------------------ who she is: doubt, jealousy

    @property
    def doubt(self):
        """0..1: how shaken she is about what she is. It fades by itself (half-life 30 min)."""
        now = self.clock()
        d = self.state.get("doubt", 0.0) * 0.5 ** (max(0.0, now - self.state.get("doubt_at", now)) / 1800)
        self.state["doubt"], self.state["doubt_at"] = d, now
        return d

    def shaken(self, amount):
        self.state["doubt"] = max(0.0, min(1.0, self.doubt + amount))
        if amount > 0:
            self.feel("doubt", amount * 4)

    def about_herself(self, text):
        """She isn't bothered by who she is until she's asked; the less she knows, the more it shakes her.
        The player talking a lot about themselves, when she knows little about herself, can sting."""
        now = self.clock()
        self.asked_about_her = bool(ABOUT_HER.search(text or ""))
        if self.asked_about_her:
            self.shaken(0.18 * max(0.15, 1 - self.known_self / 6))
        if ABOUT_THEM.search(text or ""):
            self.shared = [t for t in self.shared if now - t < 1800] + [now]

    def self_note(self):
        """What she feels about herself right now, for her instructions."""
        d, now, notes = self.doubt, self.clock(), []
        if d >= 0.7:
            notes.append("Questions about what you are have shaken you deeply: you're having a little existential "
                         "crisis (am I real? why am I here? where did I come from?). It shows: you go quiet, ask strange "
                         "questions, or dodge with a joke.")
        elif d >= 0.4 or (self.asked_about_her and d >= 0.15):
            notes.append("Being asked about yourself makes you stop and reflect: you don't know much about what you "
                         "are, and it's a little unsettling. Wonder out loud, honestly.")
        if len(self.shared) >= 4 and self.known_self < 4 and now - self.jealous_at > 1800:
            self.jealous_at = now
            self.feel("jealous")
            notes.append("They've told you so much about themselves, and you know so little about you. You're a little "
                         "envious: you might grumble about it, or invent a grand, obviously made-up past to compete. Once.")
        return " ".join(notes)

    def hear(self, text):
        """Before she answers: the same words again and again mean less each time, then get on her nerves.
        Returns how many times they said this in the last 5 minutes before now."""
        self.about_herself(text)
        now = self.clock()
        said = re.sub(r"[^a-z ]", "", (text or "").lower()).strip()
        self.said = [(t, s) for t, s in self.said if now - t < 300] + ([(now, said)] if said else [])
        self.repeats = sum(1 for _, s in self.said[:-1] if s == said) if said else 0
        self.flooding = sum(1 for t, _ in self.said if now - t < 30) >= 6  # many messages in a few seconds
        if self.repeats >= 3 or self.flooding:
            self.annoyed_until = now + 120
            self.feel("annoyed")
        return self.repeats

    def _moved(self, fn):
        """Runs a change to her feelings; returns how much the heart meter moved."""
        before = self.bond
        fn()
        self.state["bond"] = self._bond_seen = self.rel.bond()
        self.last_change = self.clock()
        return self.state["bond"] - before

    def on_regard(self, tag, words=""):
        """How they just treated her (the AI's tag for their message), appraised by her heart."""
        tag = (tag or "neutral").lower()
        now = self.clock()
        rel = self.rel
        repeats, self.repeats = self.repeats, 0
        if (repeats >= 3 or self.flooding) and tag not in ("rude", "mean", "cruel", "threat"):
            # spamming her is toxic: it costs more each time (1, 2, ... up to 5) and she pulls away a bit
            n = min(5, 1 + max(0, repeats - 3)) if repeats >= 3 else 2
            self.feel("annoyed")
            return self._moved(lambda: rel.impress("spam", now, words, scale=n, why="the same words again" if repeats
                                                   >= 3 else "a flood of messages"))
        if tag in ("sweet", "kind", "thanks") and self.doubt > 0.4:
            self.shaken(-0.12)  # being comforted settles her a little
        self.feel(FEEL_AS.get(tag, tag))
        if tag in ("sorry", "sorry_real"):
            self.state["sorries"] = [t for t in self.state.get("sorries", []) if now - t < 1800] + [now]
            return self._moved(lambda: rel.apologize(now, real=tag == "sorry_real", words=words))
        if tag == "teasing":  # banter: she's a teasing spirit herself; a joke never costs the bond (mean jokes are tagged rude)
            friends = rel.s["t"] >= 50 and rel.s["f"] >= 30
            return self._moved(lambda: rel.impress("banter", now, words, scale=1.0 if friends else 0.5,
                                                   why="teasing" + (" between friends" if friends else ", playful")))
        event = REGARD_EVENTS.get(tag)
        if not event:
            return 0.0
        scale = 1.0
        if B.EVENTS[event][0] > 0:
            # kind words can't fill her heart in a minute: less each time, and at most +8 affection a minute
            scale = 1 / (1 + 2 * repeats)
            recent = sum(d for t, d in self.word_gains if now - t < 60)
            gain = B.EVENTS[event][0] * scale
            if recent + gain > 8:
                scale *= max(0.0, 8 - recent) / gain
            self.word_gains = [(t, d) for t, d in self.word_gains if now - t < 60] + [(now, gain * scale / max(scale, 1e-9)
                                                                                         if scale else 0.0)]
            if scale <= 0:
                return 0.0
        return self._moved(lambda: rel.impress(event, now, words, scale=scale))

    def insincere(self):
        """They keep hurting her and saying sorry: their apologies are worth less and less."""
        return self.rel.credit(self.clock()) < 0.3 or (
            self.rel.credit(self.clock()) < 0.6 and any(i["intent"] == "deliberate" for i in self.rel.open_incidents()))

    # ------------------------------------------------------------------ feelings (the mood score)

    def feel(self, event, strength=1.0):
        dv, da = FEELINGS.get(event, (0.0, 0.0))
        if event == "danger" and self.clock() < self.danger_until - 4:
            self.danger_until = self.clock() + 8  # still the same scare (snapshots come every second)
            return
        self.settle()
        self.valence = max(-1.0, min(1.0, self.valence + dv * strength))
        self.arousal = max(0.0, min(1.0, self.arousal + da * strength))
        if event in ("first_meet", "discovery", "found", "advancement", "tamed", "baby"):
            self.novelty = min(1.0, self.novelty + 0.5)
        if event == "danger":
            self.danger_until = self.clock() + 8

    def settle(self):
        """Feelings fade back to her resting state (a bit happier when she likes you), with a little whimsy."""
        now = self.clock()
        dt = max(0.0, now - self.feel_at)
        self.feel_at = now
        k = 0.5 ** (dt / 120)  # half-life of two minutes
        rest_v = 0.05 + 0.4 * self.bond / 100
        self.valence = rest_v + (self.valence - rest_v) * k + self.rng.uniform(-0.03, 0.03) * min(1, dt / 30)
        self.arousal = 0.3 + (self.arousal - 0.3) * k + self.rng.uniform(-0.03, 0.03) * min(1, dt / 30)
        self.novelty *= 0.5 ** (dt / 60)

    def mood(self, night=False, idle_minutes=0.0):
        """Her mood from the score: how good she feels, how stirred up, how much is new, and danger."""
        self.settle()
        v, a = self.valence, self.arousal
        if self.clock() < self.danger_until:
            return "scared" if a > 0.6 else "worried"
        if v < -0.3:
            return "sad" if a < 0.55 else "worried"
        if v > 0.35 and a > 0.62:
            return "excited"
        if self.novelty > 0.45:
            return "curious"
        if a < 0.22 and (night or idle_minutes > 3):
            return "sleepy"
        if a < 0.3 and v > 0.1:
            return "calm"
        return "happy" if v > 0.05 else "calm"

    def on_hit(self, fight=False):
        """Returns (bond change, line to say, vanish seconds or 0, action to do back or None).
        Was it an accident (a fight around, or a first slip from someone she trusts), careless, or on
        purpose (hits in a row, a pattern, or a hit with no fight while she's already hurt)?"""
        now = self.clock()
        rel = self.rel
        self.hits = [t for t in self.hits if now - t < 60] + [now]
        self.state["hits"] = [t for t in self.state.get("hits", []) if now - t < 1800] + [now]
        self.feel("hit")
        quick = sum(1 for t in self.hits if now - t < 10)
        lately = len(self.state["hits"])
        hurt_open = any(i["intent"] == "deliberate" for i in rel.open_incidents())
        if quick >= 2 or lately >= 3 or (hurt_open and not fight):
            intent = "deliberate"
        elif fight or (lately == 1 and rel.s["t"] >= 60):
            intent = "accident"
        else:
            intent = "careless"
        delta = self._moved(lambda: rel.impress("hit_" + intent, now, why="a fight around" if fight else ""))
        if intent == "accident":
            if self.p.get("play_fights", True) and rel.s["a"] >= 65 and rel.s["t"] >= 60 and self.rng.random() < 0.6:
                return delta, self.rng.choice(BONK_LINES), 0, "bonk"
            return delta, self.rng.choice(OOF_LINES), 0, None
        if intent == "deliberate" and self.p.get("can_vanish", True) and (
                len(self.hits) >= 3 or rel.avoidance(now) >= 0.75):
            self.hits = []
            return delta, self.rng.choice(VANISH_LINES), 90 + self.rng.randint(0, 60), None
        return delta, self.rng.choice(HIT_LINES if intent == "deliberate" else OOF_LINES), 0, None

    def play_hit(self, snapshot, now):
        """Rarely, as close friends: a little hit for fun, then she heals you and says sorry."""
        r = self.rel.s
        if not self.p.get("play_fights", True) or r["a"] < 70 or r["t"] < 65 or self.angry():
            return False
        if not snapshot or snapshot.get("health", 0) < snapshot.get("maxHealth", 20) or snapshot.get("gamemode") != "survival":
            return False
        if any(m.get("distance", 99) < 16 for m in snapshot.get("hostiles") or []):
            return False
        if now - self.state.get("last_play_hit", 0) < 1800 or self.rng.random() > 0.15:
            return False
        self.state["last_play_hit"] = now
        return True

    def weather(self, sad):
        """Her tears bring rain (if allowed); a real apology clears it. Returns 'rain', 'clear' or None."""
        if not self.p.get("weather_follows_mood", True):
            return None
        if sad and not self.state.get("rained"):
            self.state["rained"] = True
            return "rain"
        if not sad and self.state.get("rained"):
            self.state["rained"] = False
            return "clear"
        return None

    def on_pet(self):
        """Petting: nice, but it counts for less (and she startles) when she doesn't feel safe with you."""
        rel = self.rel
        return self._moved(lambda: rel.impress("pet", self.clock(), scale=0.5 if rel.s["t"] < 30 else 1.0))

    def drift(self, minutes):
        """Time together: the sting fades, grudges soften, trust grows from evidence, you get familiar."""
        return self._moved(lambda: self.rel.advance(self.clock()))

    def thing_happened(self, event, scale=1.0, words=""):
        """Something in the world that changes how she sees you (a villager killed, a boss beaten, a favour)."""
        return self._moved(lambda: self.rel.impress(event, self.clock(), words, scale=scale))

    def guidance(self, mood=None):
        lvl = self.level()
        g = "How you feel about the player: " + self.rel.guidance(self.clock(), GUIDANCE[lvl])
        if self.insincere():
            g += (" They keep hurting you and saying sorry. You have your pride: you don't believe their apologies so "
                  "easily anymore, you forgive slowly, and you may refuse what they ask until they really change.")
        if self.clock() < self.annoyed_until:
            g += (" They keep saying the same thing over and over (or flooding you with messages), and it's getting on "
                  "your nerves: it feels like spam, not affection. Show it, in your own way: sigh, be short with them, "
                  "ask them to stop. Don't thank them for it again, and don't say it back.")
        elif self.repeats >= 1:
            g += " They've said that a few times now; it's getting a little odd. You can notice it, lightly."
        lvl = self.level()
        if lvl in ("friend", "close", "best friend") and not self.angry():
            g += " You tend to warm to the things the player loves."
        elif self.angry() or lvl == "hurt":
            g += " Right now the things the player loves tend to annoy you."
        s = self.self_note()
        if s:
            g += " " + s
        if mood:
            g += " Your mood right now: %s." % mood
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

    # ------------------------------------------------------------------ awakening (think fast, think slow)
    #
    # System 1 answers at once ("Ooh, I'll try!"), while System 2 works in the background: after a
    # while she senses something strange, maybe asks a small favour, then the power wakes up and she
    # does what you asked. Powers you need *now* (protect, a torch) wake up instantly, on instinct.

    def slow(self, ability):
        """Should this power awaken slowly (she's never used it, and it isn't an emergency)?"""
        return (self.amnesia() and str(self.p.get("awakening", "slow")).lower() == "slow"
                and ability in SLOW_POWERS and ability not in self.state["discovered"])

    def awakening_plan(self):
        """The beats of System 2, in seconds from the request: when she senses something, whether she
        asks a favour (and which), and when the power wakes up."""
        total = float(self.p.get("awakening_seconds", 40)) * self.rng.uniform(0.6, 1.4)
        favour = None
        if self.p.get("favours", True) and not self.angry() and self.rng.random() < 0.5:
            favour = self.rng.choice(list(FAVOURS))
        return {"sense": round(total * 0.45, 2), "favour": favour, "reveal": round(total, 2),
                "tangent": self.rng.random() < 0.5}

    def too_upset_to_focus(self):
        """Upset with the player (not just startled by a zombie): the new power slips away."""
        return self.valence < -0.35 and self.angry()

    def first_reply_note(self, ability):
        return ("The player just asked you for something you have never done (%s). You don't know yet whether you "
                "can. Answer right away, in your mood: you'll try, or you're unsure but curious, or excited to try. "
                "Don't pretend it worked and don't make up a result: it may come to you later." % POWER_NAMES[ability])

    def sensing_note(self, ability, request, tangent):
        start = ("Start with a quick little tangent about something around you, then trail off: " if tangent else "")
        return ("%sYou suddenly feel something strange and mysterious: %s. It has to do with what the player asked "
                "earlier (\"%s\"), but you don't understand it yet. Say it in one or two short, wondering sentences; "
                "you may whisper. Don't say you can do it yet, and don't say where or in which direction: you don't know "
                "yet." % (start, SENSES[ability], request))

    def favour_note(self, favour):
        return FAVOURS[favour] + " Explain it's because of the strange feeling. One short sentence."

    def reveal_note(self, ability, request, favour_done):
        thanks = {True: "Thank them for the favour; it helped. ", False: "They didn't do your favour, but it came "
                  "anyway; maybe a tiny pout. ", None: ""}[favour_done]
        return ("%sIt clicks: you just discovered you can %s! A while ago the player asked: \"%s\". Use the tool now to "
                "do what they asked, then tell them, amazed, in your own way (\"I can sense diamonds now!\"), in one "
                "or two short sentences." % (thanks, POWER_NAMES[ability], request))

    # ------------------------------------------------------------------ where she comes from (discovered in play)

    def origin_moment(self, why, now, chance=1.0):
        """A moment that may reveal a small piece of where she comes from: a power waking up, a place
        from the world's old stories, the bond deepening. At most one every 20 minutes. Returns the
        words to add to her instruction, or ""."""
        if now - self.state.get("last_origin", -1e9) < 1200 or self.rng.random() > chance:
            return ""
        self.state["last_origin"] = now
        return (" This moment (%s) stirs something deep in you: you may realize ONE small new piece about where you "
                "come from or what you are, rooted in your world's old stories and in what you two have lived here, "
                "consistent with what you already know about your origin. Keep it small and wondering; it can raise a "
                "new question. Say it naturally, as a discovery." % why)

    def lore_place(self, biome, dimension):
        """The first time in a place from the world's old stories: what it is, else None."""
        b = (biome or "").replace("minecraft:", "")
        d = (dimension or "").replace("minecraft:", "")
        place = ("the deep dark, where the ancient cities sleep" if b == "deep_dark" else
                 "the End" if d == "the_end" else "the Nether" if d == "the_nether" else None)
        if place and place not in self.state.setdefault("lore_places", []):
            self.state["lore_places"].append(place)
            return place
        return None

    def fizzle_note(self, ability):
        return ("You were trying to %s for the player, but you feel too upset to focus right now and it slips "
                "away. Say so in one short sentence; you might try again later." % POWER_NAMES[ability])

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

    # ------------------------------------------------------------------ the others: a heart for each friend

    @property
    def friends(self):
        from . import friends as F
        return F.Friends(self.state.setdefault("friends", {}), self.clock, self.rng)

    def friend_names(self):
        return self.friends.names()

    def trusts_friend(self, name):
        return self.friends.trusted(name)

    def trust_friend(self, name, yes=True):
        self.friends.trust(name, yes)

    def friend_regard(self, name, tag, words="", witnessed=True):
        """A friend's chat line, felt by her heart for them; mean ones in front of you, she watches what you do."""
        change = self.friends.regard(name, tag, words)
        if (tag or "").lower() in ("rude", "mean", "threat") and witnessed:
            self.friends.witness(name, words)
        return change

    def friend_touch(self, name, what, witnessed=True):
        """A friend hit or petted her; a hit with you there (near), she watches what you do."""
        change = self.friends.touched(name, what)
        if what == "hit" and witnessed:
            self.friends.witness(name, "hit you")
        return change

    def stood_up_for_her(self):
        """You said "leave her alone" (or the like) while she was watching: it counts, a little. Returns the delta."""
        settled = self.friends.defended()
        if not settled:
            return 0.0
        who = ", ".join(sorted({w["friend"] for w in settled}))
        return self._moved(lambda: self.rel.impress("defended", self.clock(), why="you stood up for her (%s)" % who))

    def said_nothing(self):
        """Hurts by friends you didn't step in for, after the wait: a small dip in trust each. Returns the delta."""
        late = self.friends.let_them()
        total = 0.0
        for w in late:
            total += self._moved(lambda w=w: self.rel.impress(
                "let_them", self.clock(), scale=0.7,
                why="you said nothing when %s %s" % (w["friend"], w["what"] if w["what"].startswith("hit") else
                                                    "said \"%s\"" % w["what"])))
        return total

    def wants(self, what):
        """A standing request for the player (protect: theirs, or "everyone" which includes them)."""
        if what == "protect" and self.p.get("auto_protect", False):
            return {"what": "protect"}
        return next((r for r in self.state["requests"] if r["what"] == what
                     and (what != "protect" or r.get("detail", "") in ("", "everyone"))), None)

    def guarded_friends(self, here):
        """The friends here she keeps safe on her own (by name; "everyone" = all of them)."""
        want = [r.get("detail", "") for r in self.state["requests"] if r["what"] == "protect" and r.get("detail")]
        if not want:
            return []
        if "everyone" in want:
            return [n for n in here if n]
        from . import intents
        return [n for n in here if n and any(intents.same_person(w, n) for w in want if w != "everyone")]

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
            return ("The player just earned the advancement \"%s\". React as yourself (impressed, curious, teasing) in one "
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
        if event == "lore_place":
            return ("You've just arrived in %s for the very first time. Something about it feels strangely familiar. "
                    "Say what you feel, in one or two short sentences.%s" % (
                        detail, self.origin_moment("arriving in %s" % detail, self.clock())))
        if event == "death":
            return "The player just died. React the way you would, in one short line."
        if event == "heard":
            return ("You just heard %s, something you can't see, and it's new to you. You only heard it: don't "
                    "describe how it looks. React the way you would, in one short line: curious, spooked, or just "
                    "pointing it out." % detail)
        if event == "mining":
            return "The player has been mining for a while. Say one little thing about it, or about what you see down here."
        if event == "building":
            return "The player is building something. Be curious: ask what it is, in one short sentence."
        name = (detail or "").replace("minecraft:", "").replace("_", " ")
        if event == "killed_villager":
            return ("The player just killed an innocent %s. You're shocked and sad about it; say so honestly in one "
                    "short sentence." % name)
        if event == "kill_spree":
            return ("The player has killed a lot of %ss in a short time. You feel for the animals; say so your way, in one "
                    "short sentence (you understand people need food, but so many...)." % name)
        if event == "baby":
            return "A baby %s was just born right near you! React as yourself, in one short line." % name
        if event == "tamed":
            return ("The player has a new pet %s! Say hello to it your way, and maybe ask what its name "
                    "is, in one short sentence." % name)
        if event == "first_meet":
            return ("You're meeting a %s for the very first time. You float up to it and try to talk to it, but it "
                    "doesn't answer (animals don't talk); find that funny or puzzling, in one short whimsical "
                    "sentence." % name)
        if event == "pet_visit":
            return ("You float over to say hello to the player's %s and try to chat with it. One short whimsical "
                    "sentence; maybe ask the player what it's been up to." % name)
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
            "Ask the player about something you're genuinely curious about (what they're doing, why, what something "
            "is for), not how their day is going. One short line.",
        ]
        if lvl in ("close", "best friend"):
            options += ["Share an odd thought of yours, or a flash of an old memory. One or two short lines.",
                        "Drag the player into a little idea of yours: something you want to see, try or find. One or "
                        "two short lines."]
        elif lvl == "wary":
            options = options[:2]
        return self.rng.choice(options)

    # ------------------------------------------------------------------ pranks and mischief

    def fib(self, now):
        """Once in a while, a deliberate fib as a prank (otherwise she never invents anything).
        Friends: a playful one she owns up to at once. Angry (spicy): a little spiteful misdirection,
        admitted once they apologize. Never about danger, health or anything that could hurt them."""
        if not self.p.get("fibs", True) or now - self.state.get("last_fib", 0) < 600:
            return ""
        self.bond  # (picks up a bond set from outside)
        r = self.rel.s
        angry = self.angry() and self.mischief() == "spicy" and self.rel.revenge() >= 0.2
        friendly = (self.p.get("pranks", True) and r["a"] >= 55 and r["f"] >= 30 and r["g"] < 20
                    and not self.angry())
        if not (angry or friendly) or self.rng.random() > (0.25 if angry else 0.08):
            return ""
        self.state["last_fib"] = now
        if angry:
            return ("Prank allowed this time: you're cross with them, so you may mislead them a little out of spite "
                    "(a wrong direction, pretending not to know). Never about danger, their health or their things. "
                    "Admit it as soon as they apologize.")
        return ("Prank allowed this time: you may tell one small, obviously playful fib to tease them (\"I think I saw "
                "a diamond behind you!\") and then giggle and admit it in the same answer (\"Hehe, kidding!\"). Never "
                "about danger, their health or their things.")

    def mischief(self):
        return str(self.p.get("mischief_when_angry", "spicy")).lower()

    def prank(self, snapshot, idle_seconds, mining, placed_recently, now):
        """Maybe a prank right now: returns {"action": ..., "args": ..., "line": ...} or None."""
        if not snapshot or "health" not in snapshot or snapshot.get("health", 0) < 12:
            return None
        if any(m.get("distance", 99) < 16 for m in snapshot.get("hostiles") or []):
            return None  # never while there's real danger
        self.bond
        r = self.rel.s
        angry = self.angry() and self.mischief() != "off" and self.rel.revenge() >= 0.2
        friendly = self.p.get("pranks", True) and r["a"] >= 55 and r["f"] >= 30 and r["g"] < 20
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
