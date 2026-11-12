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
    "arrived": (0.3, 0.25), "annoyed": (-0.25, 0.3),
}

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
               "give_item": "make things appear out of nothing", "set_time": "move the sun across the sky",
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
        self.state = self.fresh()
        self.valence, self.arousal, self.novelty = 0.25, 0.35, 0.0
        self.danger_until = 0.0
        self.feel_at = clock()
        self.hits = []
        self.said, self.word_gains, self.annoyed_until, self.repeats = [], [], 0.0, 0  # repeated words (hear)
        self.flooding = False
        self.pending_offer = None
        self.last_offer = {}
        self.last_change = 0.0

    # ------------------------------------------------------------------ persistence (a memory document)

    def fresh(self):
        return {"bond": float(self.p.get("start_bond", 30)), "discovered": [], "asked": {}, "seen_items": [],
                "requests": [], "last_prank": 0, "hurt_until": 0, "seen_species": [], "sorries": [],
                "hits": [], "rained": False}

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

    def hear(self, text):
        """Before she answers: the same words again and again mean less each time, then get on her nerves.
        Returns how many times they said this in the last 5 minutes before now."""
        now = self.clock()
        said = re.sub(r"[^a-z ]", "", (text or "").lower()).strip()
        self.said = [(t, s) for t, s in self.said if now - t < 300] + ([(now, said)] if said else [])
        self.repeats = sum(1 for _, s in self.said[:-1] if s == said) if said else 0
        self.flooding = sum(1 for t, _ in self.said if now - t < 30) >= 6  # many messages in a few seconds
        if self.repeats >= 3 or self.flooding:
            self.annoyed_until = now + 120
            self.feel("annoyed")
        return self.repeats

    def on_regard(self, tag):
        tag = (tag or "neutral").lower()
        delta = REGARD.get(tag, 0)
        now = self.clock()
        repeats, self.repeats = self.repeats, 0
        if (repeats >= 3 or self.flooding) and tag not in ("rude", "mean"):
            # spamming her is toxic: it costs more each time (-1, -2, ... up to -5) and she pulls away a bit
            self.state["hurt_until"] = max(self.state.get("hurt_until", 0), now + 30)
            return self.change(-min(5, 1 + max(0, repeats - 3)) if repeats >= 3 else -2, "spamming")
        if delta > 0:
            delta = delta / (1 + 2 * repeats)
            # and kind words can't fill her heart in a minute: at most +8 a minute from words
            recent = sum(d for t, d in self.word_gains if now - t < 60)
            delta = max(0.0, min(delta, 8 - recent))
            self.word_gains = [(t, d) for t, d in self.word_gains if now - t < 60] + [(now, delta)]
        self.feel(tag)
        if tag in ("rude", "mean"):
            self.state["hurt_until"] = now + (120 if tag == "mean" else 45)
        elif tag == "sorry":
            # quick to forgive, but not a fool: sorry after sorry for the same thing counts for less
            recent = [t for t in self.state.get("sorries", []) if now - t < 1800]
            hurt_lately = [t for t in self.state.get("hits", []) if now - t < 1800]
            repeats = len(recent) if hurt_lately else 0
            self.state["sorries"] = recent + [now]
            delta = REGARD["sorry"] / (1 + 1.5 * repeats)
            if repeats < 2:
                self.state["hurt_until"] = 0
            else:  # she doesn't buy it anymore: still hurt for a while
                self.state["hurt_until"] = max(self.state.get("hurt_until", 0), now + 60)
        return self.change(delta, tag)

    def insincere(self):
        """They keep hurting her and saying sorry."""
        now = self.clock()
        return len([t for t in self.state.get("sorries", []) if now - t < 1800]) >= 3 and \
            len([t for t in self.state.get("hits", []) if now - t < 1800]) >= 3

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

    def on_hit(self):
        """Returns (bond change, line to say, vanish seconds or 0, action to do back or None)."""
        now = self.clock()
        self.hits = [t for t in self.hits if now - t < 60] + [now]
        self.state["hits"] = [t for t in self.state.get("hits", []) if now - t < 1800] + [now]
        self.feel("hit")
        first_in_a_while = len(self.state["hits"]) == 1
        if first_in_a_while and self.bond >= 60:
            # probably an accident between friends: a little "ow", and maybe a playful bonk back
            delta = self.change(-2, "hit")
            if self.p.get("play_fights", True) and self.bond >= 65 and self.rng.random() < 0.6:
                return delta, self.rng.choice(BONK_LINES), 0, "bonk"
            return delta, self.rng.choice(OOF_LINES), 0, None
        delta = self.change(-6, "hit")
        self.state["hurt_until"] = now + 90
        if len(self.hits) >= 3 and self.p.get("can_vanish", True):
            self.hits = []
            return delta, self.rng.choice(VANISH_LINES), 90 + self.rng.randint(0, 60), None
        return delta, self.rng.choice(HIT_LINES), 0, None

    def play_hit(self, snapshot, now):
        """Rarely, as close friends: a little hit for fun, then she heals you and says sorry."""
        if not self.p.get("play_fights", True) or self.bond < 75 or self.angry():
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
        return self.change(1.5, "pet")

    def drift(self, minutes):
        """Time heals: below a friendly baseline the bond slowly comes back (she forgets quickly)."""
        if self.bond < 40 and self.clock() > self.state.get("hurt_until", 0):
            return self.change(min(40 - self.bond, 1.0 * minutes), "time")
        return 0

    def guidance(self, mood=None):
        lvl = self.level()
        g = "Your bond with the player: %s (%d/100). %s" % (lvl, round(self.bond), GUIDANCE[lvl])
        if self.clock() < self.state.get("hurt_until", 0) and lvl not in ("hurt",):
            g += " Right now you're still a bit upset about how they just treated you."
        if self.insincere():
            g += (" They keep hurting you and saying sorry. You have your pride: you don't believe their apologies so "
                  "easily anymore, you forgive slowly, and you may refuse what they ask until they really change.")
        if self.clock() < self.annoyed_until:
            g += (" They keep saying the same thing over and over (or flooding you with messages), and it's getting on "
                  "your nerves: it feels like spam, not affection. Show it, in your own way: sigh, be short with them, "
                  "ask them to stop. Don't thank them for it again, and don't say it back.")
        elif self.repeats >= 1:
            g += " They've said that a few times now; it's getting a little odd. You can notice it, lightly."
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
                "do what they asked, then tell them with wonder and delight (\"I can sense diamonds now!\"), in one "
                "or two short sentences." % (thanks, POWER_NAMES[ability], request))

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
        name = (detail or "").replace("minecraft:", "").replace("_", " ")
        if event == "killed_villager":
            return ("The player just killed an innocent %s. You're shocked and sad about it; say so honestly in one "
                    "short sentence." % name)
        if event == "kill_spree":
            return ("The player has killed a lot of %ss in a short time. You feel sad for them; say it gently in one "
                    "short sentence (you understand people need food, but so many...)." % name)
        if event == "baby":
            return "A baby %s was just born right near you! Be delighted in one short sentence." % name
        if event == "tamed":
            return ("The player has a new pet %s! Be thrilled: say hello to it and ask the player what its name "
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

    def fib(self, now):
        """Once in a while, a deliberate fib as a prank (otherwise she never invents anything).
        Friends: a playful one she owns up to at once. Angry (spicy): a little spiteful misdirection,
        admitted once they apologize. Never about danger, health or anything that could hurt them."""
        if not self.p.get("fibs", True) or now - self.state.get("last_fib", 0) < 600:
            return ""
        angry = self.angry() and self.mischief() == "spicy"
        friendly = self.p.get("pranks", True) and self.bond >= 55 and not self.angry()
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
