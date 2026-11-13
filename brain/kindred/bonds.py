"""Her relationship with you: five feelings that can disagree, a sting that fades, and a memory of
every hurt and how far it has been repaired.

One number used to do everything ("bond"), moved by fixed amounts. But she can like you and not
trust you, or trust you and resent you; ten insults in one evening aren't ten insults over ten days;
and an apology softens a grudge long before trust comes back. So:

- Slow feelings (0-100): affection (liking being with you), trust (feeling safe with you, your word
  meaning something), respect (how you act: with the world, with her), familiarity (time and shared
  moments), resentment (unresolved hurt, a grudge separate from liking).
- A fast sting: the hurt of right now (half-life 3 minutes), on top of her mood.
- An incident ledger: each hurt, how deliberate it was, how much it cost, and where its repair stands
  (open, apologised, probation, repaired, scar).

Every change goes through impress(), which first appraises the event (deliberate? part of a pattern?
from someone she trusts?) and logs why in words. Bad weighs more than good, a pattern weighs more
than its parts, trust only grows from evidence over time, and forgiveness (resentment going down) is
not the same as trust coming back. The old bond stays, derived, for the heart meter.

The design and its sources: docs/HEART.md ("A deeper heart").
"""
import math
import random

DAY, HOUR, MINUTE = 86400.0, 3600.0, 60.0

# base impact of each kind of event: affection, trust, respect, resentment, sting, severity
EVENTS = {
    "sweet": (3, 0, 0, -1, 0, 0),
    "kind": (1.5, 0, 0, -0.5, 0, 0),
    "thanks": (1.5, 0, 0.5, -0.5, 0, 0),
    "banter": (1, 0, 0, 0, 0, 0),           # teasing between people who know and trust each other
    "pet": (1, 0, 0, 0, 0, 0),
    "favour": (1.5, 1, 0.5, 0, 0, 0),       # did what she asked, kept a promise, came back for her
    "feat": (0, 0, 2, 0, 0, 0),             # an advancement, a boss beaten
    "frustrated": (-0.5, 0, 0, 0.3, 0.05, 0),
    "dismissive": (-1, 0, -0.5, 1, 0.1, 0.3),
    "rude": (-3, -1, -1, 3, 0.3, 1),
    "mean": (-6, -4, -2, 8, 0.6, 2.5),
    "threat": (-3, -6, -2, 5, 0.5, 2),
    "hit_accident": (0, 0, 0, 0, 0.15, 0),
    "hit_careless": (-1, -2, 0, 1, 0.3, 0.5),
    "hit_deliberate": (-3, -8, -1, 6, 0.6, 2),
    "killed_villager": (-2, -2, -8, 2, 0.3, 0),
    "kill_spree": (0, 0, -3, 0, 0, 0),
    "spam": (-1, 0, -0.5, 0, 0.2, 0),       # per step of annoyance (scaled 1-5)
}
DELIBERATE = ("rude", "mean", "threat", "hit_deliberate")

TEMPERAMENTS = {
    "default": {"sensitivity": 1.0, "forgiveness": 1.0, "warmth": 1.0, "pride": 1.0},
    "thick-skinned": {"sensitivity": 0.7, "forgiveness": 1.2, "warmth": 1.0, "pride": 0.9},
    "sensitive": {"sensitivity": 1.35, "forgiveness": 0.85, "warmth": 1.05, "pride": 1.1},
    "forgiving": {"sensitivity": 0.9, "forgiveness": 1.4, "warmth": 1.1, "pride": 0.8},
}

# small things in her world that make up for a serious hurt, checked from what you do
GESTURES = {
    "flower": ("plant a flower for you", ("poppy", "dandelion", "tulip", "orchid", "allium", "daisy", "cornflower",
                                          "lily", "bluet", "rose")),
    "sapling": ("plant a little tree for you", ("sapling", "propagule")),
    "torch": ("light up the dark spot you're scared of with a torch", ("torch",)),
}

STANCES = {
    "new": "You don't know the player yet. You're more curious about the world than about them: polite, a little "
           "watchful, you don't presume.",
    "bitter": "You resent the player: they've hurt you again and again. You're short and sharp with them, you don't "
              "do favours or offer anything. Your hurt shows in your manner and in your world, never as cruel words.",
    "cold": "You don't like or trust the player right now. Minimal and factual; no small talk, no offers.",
    "wounded": "You care about the player and they've hurt you. You're quieter, you sometimes take things the wrong "
               "way, you may bring it up, and part of you wants to believe them.",
    "guarded": "You like the player, but you don't feel safe with them. Warm enough in words, but you keep your "
               "distance and you check what they really mean.",
    "reliant": "You can count on the player, but you don't particularly enjoy them right now. Dependable and polite: "
               "you help when asked, but you don't offer or share much.",
}
SUMMARIES = {  # for /kindred heart and the dashboard
    "new": "She's still getting to know you.",
    "bitter": "She resents you.",
    "cold": "She neither likes nor trusts you right now.",
    "wounded": "She cares about you, and you've hurt her.",
    "guarded": "She likes you, but she's wary of you.",
    "reliant": "She trusts you, but she isn't fond of you right now.",
    "warm": "She likes you and feels safe with you.",
    "easy": "She's easy with you.",
}


def clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def ago_words(seconds):
    if seconds < 90:
        return "just now"
    if seconds < 3 * HOUR:
        return "%d minutes ago" % (seconds // 60)
    if seconds < 2 * DAY:
        return "earlier today" if seconds < 12 * HOUR else "yesterday"
    return "%d days ago" % (seconds // DAY)


def fresh(start_bond=30.0, temperament="default", rng=None, now=0.0):
    rng = rng or random.Random()
    base = dict(TEMPERAMENTS.get(temperament, TEMPERAMENTS["default"]))
    temp = {k: round(v * rng.uniform(0.85, 1.15), 3) for k, v in base.items()}  # each world's Pip is a bit different
    s = {"a": 0.0, "t": 0.0, "r": 50.0, "f": 0.0, "g": 0.0, "f_peak": 0.0, "sting": 0.0, "sting_at": now,
         "incidents": [], "folded": 0, "beliefs": [], "temperament": temp, "base_temperament": base,
         "breaks": [], "last": now, "last_hurt": -1e12, "sessions": 0, "session_at": now, "calm_sessions": 0,
         "log": [], "next_id": 1, "gesture": None, "repaired_at": -1e12}
    Bonds(s).set_bond(start_bond)
    return s


class Bonds:
    """Works on a plain dict (saved with her heart, per world)."""

    def __init__(self, state):
        self.s = state
        self.new_scars, self.healed_scars = [], []   # for the brain to turn into core memories

    # ------------------------------------------------------------------ derived (never stored)

    @property
    def temp(self):
        return self.s["temperament"]

    def bond(self):
        s = self.s
        return round(clamp(0.45 * s["a"] + 0.35 * s["t"] + 0.20 * s["f"] - 0.35 * s["g"]), 2)

    def set_bond(self, value):
        """Moves affection and trust so the old single bond reads `value` (old saves, tests, imports)."""
        s = self.s
        x = clamp((value - 0.2 * s["f"] + 0.35 * s["g"]) / 0.8)
        s["a"] = s["t"] = x

    def sting(self, now):
        return self.s["sting"] * 0.5 ** (max(0.0, now - self.s["sting_at"]) / 180)

    def pattern(self, now):
        return sum(i["severity"] * 0.5 ** (max(0.0, now - i["t"]) / (72 * HOUR))
                   for i in self.s["incidents"] if i["intent"] == "deliberate")

    def sensitization(self, now):
        return 1 + min(1.5, 0.25 * self.pattern(now)) * self.temp["sensitivity"]

    def buffer(self, now):
        return 1 - 0.5 * (self.s["t"] / 100) * math.exp(-self.pattern(now))

    def floor(self):
        return 12.0 * sum(1 for i in self.s["incidents"] if i["state"] == "scar")

    def credit(self, now):
        return 0.5 ** sum(1 for t in self.s["breaks"] if now - t < 3 * DAY)

    def closeness(self, now):
        s = self.s
        return round(clamp(min(s["a"], s["t"]) / 100, 0, 1) * (1 - min(0.9, 1.5 * self.sting(now))), 2)

    def avoidance(self, now):
        s = self.s
        return round((s["g"] + (100 - s["t"])) / 200 + 0.5 * self.sting(now), 2)

    def revenge(self):
        return round(self.s["g"] / 100 * (1 - self.s["a"] / 100), 2)

    def benevolence(self):
        return round((0.7 * self.s["a"] + 0.3 * self.s["r"]) / 100, 2)

    def open_incidents(self):
        return [i for i in self.s["incidents"] if i["state"] in ("open", "apologised", "probation")]

    def stance(self, now):
        a, t, g, f = self.s["a"], self.s["t"], self.s["g"], self.s["f"]
        if f < 15 and g < 20:
            return "new"
        if g >= 60 and a < 40:
            return "bitter"
        if a < 30 and t < 30:
            return "cold"
        if a >= 50 and g >= 35:
            return "wounded"
        if a >= 55 and t < 40:
            return "guarded"
        if t >= 55 and a < 35:
            return "reliant"
        if a >= 60 and t >= 60 and g < 20:
            return "warm"
        return "easy"

    # ------------------------------------------------------------------ what happens

    def impress(self, event, now, words="", intent=None, scale=1.0, why=""):
        """One event, appraised, applied and logged. Returns the change (dims and sting)."""
        self.advance(now)
        s = self.s
        da, dt, dr, dg, sting, severity = (x * scale for x in EVENTS[event])
        intent = intent or ("deliberate" if event in DELIBERATE else "careless" if severity > 0 else "")
        notes = []
        negative = da < 0 or dt < 0 or dg > 0 or severity > 0
        if negative:
            betrayal = intent == "deliberate" and any(i["state"] == "probation" for i in s["incidents"])
            if betrayal:  # hurt again while she was watching whether you meant your sorry
                da, dt, dg, sting, severity = da * 1.5, dt * 2, dg * 1.5, sting + 0.2, severity + 2
                for i in s["incidents"]:
                    if i["state"] == "probation":
                        i["state"] = "open"
                s["breaks"].append(now)
                notes.append("betrayal (hurt during probation)")
            sens, buf = self.sensitization(now), self.buffer(now)
            mult = sens * buf
            if sens > 1.01:
                notes.append("pattern %.1f ×%.2f" % (self.pattern(now), sens))
            if buf < 0.99:
                notes.append("benefit of the doubt ×%.2f" % buf)
            da, dt, dr, dg = da * mult, dt * mult, dr * mult, dg * mult
            sting *= (0.7 + 0.6 * s["a"] / 100) * self.temp["sensitivity"]
        else:
            warmth = self.temp["warmth"]
            da = da * (1 - s["a"] / 110) * warmth if da > 0 else da
            dt = dt * (1 - s["t"] / 110) if dt > 0 else dt
            dr = dr * (1 - s["r"] / 110) if dr > 0 else dr
            mult = 1.0
        before = {k: s[k] for k in ("a", "t", "r", "g")}
        s["a"], s["t"], s["r"] = clamp(s["a"] + da), clamp(s["t"] + dt), clamp(s["r"] + dr)
        s["g"] = clamp(max(min(s["g"], self.floor()), s["g"] + dg)) if dg < 0 else clamp(s["g"] + dg)
        if sting > 0:
            s["sting"], s["sting_at"] = min(1.0, self.sting(now) + sting), now
        change = {k: round(s[k] - before[k], 2) for k in before}
        if severity > 0:
            inc = {"id": s["next_id"], "t": now, "kind": event, "words": (words or "")[:80], "intent": intent,
                   "severity": round(severity, 2), "mult": round(mult, 2), "t_lost": round(-change["t"], 2),
                   "g_left": round(max(0.0, change["g"]), 2), "state": "open"}
            s["next_id"] += 1
            s["incidents"].append(inc)
            if intent == "deliberate":
                s["last_hurt"] = now
                if self.pattern(now) >= 6 or (notes and notes[0].startswith("betrayal") and severity >= 4):
                    self._scar(now)
        self._log(now, event, words, intent, notes + ([why] if why else []), change, sting)
        return dict(change, sting=round(sting, 2))

    def apologize(self, now, real=False, words=""):
        """A sorry. For an accident or a careless act it closes the hurt; for something deliberate it
        softens the grudge and starts a probation: trust comes back only if they mean it."""
        self.advance(now)
        s = self.s
        open_ = self.open_incidents()
        if not open_:
            return self.impress("kind", now, words, why="a sorry for nothing much")
        value = (1.0 if real else 0.4) * self.credit(now) ** self.temp["pride"]
        notes = ["%s, credit %.2f" % ("a real apology" if real else "sorry", self.credit(now))]
        g0, t0 = s["g"], s["t"]
        for i in open_:
            if i["intent"] != "deliberate":  # accidents and carelessness: forgiven
                s["t"] = clamp(s["t"] + i["t_lost"])
                s["g"] = clamp(s["g"] - i["g_left"])
                i["g_left"], i["state"], i["repaired_t"] = 0.0, "repaired", now
            elif i["state"] == "open":
                drop = 0.5 * value * i["g_left"]
                s["g"] = clamp(s["g"] - drop)
                i["g_left"] = round(i["g_left"] - drop, 2)
                i["state"], i["apology"] = "probation", {"t": now, "real": real, "value": round(value, 2)}
                i["need"] = 8 * MINUTE * i["severity"] * i["mult"] / self.temp["forgiveness"]
                i["done"] = 0.0
        s["sting"] = self.sting(now) * 0.5
        s["sting_at"] = now
        if real:
            for i in s["incidents"]:
                if i["state"] == "scar":
                    i["named"] = True  # a real apology for the old hurt: part of healing a scar
        change = {"t": round(s["t"] - t0, 2), "g": round(s["g"] - g0, 2)}
        self._log(now, "sorry_real" if real else "sorry", words, "", notes, change, 0)
        return change

    def gesture_check(self, did, now):
        """The small thing she asked for, done ("placed a poppy"): repair at once."""
        g = self.s.get("gesture")
        if not g or not did:
            return False
        words = GESTURES[g["kind"]][1]
        if not any(d.startswith("placed") and any(w in d for w in words) for d in did):
            return False
        s = self.s
        for i in s["incidents"]:
            if i["id"] == g["incident"] and i["state"] in ("open", "apologised", "probation"):
                self._repair(i, now)
            if i["state"] == "scar":
                i["gesture"] = True
        s["a"] = clamp(s["a"] + 3)
        s["gesture"] = None
        self._log(now, "gesture", GESTURES[g["kind"]][0], "", ["made up for it"], {"a": 3}, 0)
        return True

    def ask_gesture(self, rng, now):
        """For a serious hurt (or a pattern): at most once per incident, a small ask in her world."""
        s = self.s
        if s.get("gesture"):
            return s["gesture"]
        serious = [i for i in self.open_incidents() if i["intent"] == "deliberate"
                   and (i["severity"] * i["mult"] >= 3 or self.pattern(now) >= 3) and not i.get("asked")]
        if not serious:
            return None
        inc = serious[-1]
        inc["asked"] = True
        s["gesture"] = {"kind": rng.choice(sorted(GESTURES)), "incident": inc["id"], "t": now}
        return s["gesture"]

    def reappraise(self, incident_id, intent, now):
        """System 2 thought again (banter after all? an accident?): one notch, logged, reversible."""
        order = ["accident", "careless", "deliberate"]
        for i in self.s["incidents"]:
            if i["id"] != incident_id or intent not in order or i["intent"] not in order:
                continue
            step = order.index(intent) - order.index(i["intent"])
            if step == 0:
                return False
            new = order[order.index(i["intent"]) + (1 if step > 0 else -1)]
            s = self.s
            if step < 0:  # softer: give back half of what it cost
                s["t"] = clamp(s["t"] + 0.5 * i["t_lost"])
                s["g"] = clamp(s["g"] - 0.5 * i["g_left"])
                i["t_lost"], i["g_left"] = i["t_lost"] * 0.5, i["g_left"] * 0.5
            else:         # harder: half again
                s["t"] = clamp(s["t"] - 0.5 * i["t_lost"])
                s["g"] = clamp(s["g"] + 0.5 * i["g_left"])
            self._log(now, "reappraised", i.get("words", ""), new, ["was %s" % i["intent"]], {}, 0)
            i["intent"] = new
            return True
        return False

    def set_beliefs(self, beliefs, now):
        """System 2's conclusions about the player, each with its evidence; positive ones count as trust
        evidence once."""
        out = []
        for b in (beliefs or [])[:5]:
            text = str(b.get("text") if isinstance(b, dict) else b).strip()[:160]
            if not text:
                continue
            good = bool(b.get("good")) if isinstance(b, dict) else False
            known = next((x for x in self.s["beliefs"] if x["text"] == text), None)
            if good and not known:
                self.s["t"] = clamp(self.s["t"] + 1)
            out.append({"text": text, "good": good, "since": known["since"] if known else now,
                        "evidence": (b.get("evidence") if isinstance(b, dict) else None) or []})
        self.s["beliefs"] = out

    # ------------------------------------------------------------------ time

    def advance(self, now):
        """Time passing: together (play) or apart (the game closed). Words fade, scars don't."""
        s = self.s
        dt = now - s["last"]
        s["last"] = now
        if dt <= 0:
            return
        floor = self.floor()
        if dt > 5 * MINUTE:  # apart: grudges soften with real time; trust doesn't come back on its own
            if s["g"] > floor:
                s["g"] = floor + (s["g"] - floor) * 0.5 ** (dt / DAY)
            return
        m = dt / MINUTE
        calm = now - s["last_hurt"] > 10 * MINUTE
        if calm:
            probation = any(i["state"] == "probation" for i in s["incidents"])
            s["t"] = clamp(s["t"] + 0.8 * (1 - s["t"] / 100) * (2 if probation else 1)
                           * (0.5 if self.pattern(now) > 3 else 1) * m / 10)
        if now - s["last_hurt"] > 2 * MINUTE and s["g"] > floor:
            s["g"] = floor + (s["g"] - floor) * 0.5 ** (m / (60 * self.temp["forgiveness"]))
        s["a"] = clamp(s["a"] - 0.02 * s["g"] * m / 10)
        if not self.open_incidents():
            s["a"] = clamp(s["a"] + 0.3 * (1 - s["a"] / 100) * self.temp["warmth"] * m / 10)
        s["r"] = 50 + (s["r"] - 50) * 0.5 ** (m / 480)
        s["f"] = clamp(s["f"] + self.temp["warmth"] * m / 10)
        s["f_peak"] = max(s["f_peak"], s["f"])
        for i in s["incidents"]:
            if i["state"] == "probation" and calm:
                i["done"] = i.get("done", 0) + dt
                if i["done"] >= i["need"]:
                    self._repair(i, now)
        old = [i for i in s["incidents"] if i["state"] == "repaired" and now - i.get("repaired_t", now) > 30 * DAY]
        if old:
            s["folded"] += len(old)
            s["incidents"] = [i for i in s["incidents"] if i not in old]

    def familiar_moment(self, now, amount=2.0):
        """A shared first (a new place, a boss): you two have more history."""
        self.s["f"] = clamp(self.s["f"] + amount * self.temp["warmth"])
        self.s["f_peak"] = max(self.s["f_peak"], self.s["f"])

    def session_start(self, now):
        """A new play session: calm sessions heal scars; very slowly, how she's treated shapes her."""
        s = self.s
        if s["sessions"] > 0:
            s["calm_sessions"] = s["calm_sessions"] + 1 if s["last_hurt"] < s["session_at"] else 0
        s["sessions"] += 1
        s["session_at"] = now
        s["f"] = max(s["f"], 0.7 * s["f_peak"])
        for i in s["incidents"]:
            if i["state"] == "scar" and s["calm_sessions"] >= 3 and (i.get("gesture") or i.get("named")):
                i["state"], i["repaired_t"] = "repaired", now
                self.healed_scars.append(i)
        base, temp = s["base_temperament"], s["temperament"]
        if s["calm_sessions"] >= 3:      # treated kindly for a long while: thicker skin, warmer
            temp["sensitivity"] = max(base["sensitivity"] * 0.8, temp["sensitivity"] * 0.99)
            temp["warmth"] = min(base["warmth"] * 1.2, temp["warmth"] * 1.01)
        elif self.pattern(now) > 3:      # treated badly: more sensitive
            temp["sensitivity"] = min(base["sensitivity"] * 1.2, temp["sensitivity"] * 1.01)

    # ------------------------------------------------------------------ words for her and for you

    def guidance(self, now, level_text):
        """How she feels about you, in words (no numbers): her stance, what colours it, why."""
        st = self.stance(now)
        g = STANCES.get(st, level_text)
        s = self.s
        if s["r"] < 30:
            g += (" You're not impressed by how they act lately: you argue, you don't cheer, and you may refuse to "
                  "help with things you disapprove of.")
        elif s["r"] >= 75:
            g += " You admire how they handle things; you're curious how they do it."
        if s["f"] >= 60:
            g += " You two go back a long way: callbacks to shared moments and in-jokes come naturally."
        ev = self.evidence(now)
        if ev:
            g += " " + ev
        if self.sting(now) > 0.35:
            g += " Right now it still stings."
        gest = s.get("gesture")
        if gest and not gest.get("said"):
            g += (" If it feels right, ask them once, simply, to %s, as a way to make up. Never insist."
                  % GESTURES[gest["kind"]][0])
        return g

    def evidence(self, now):
        s = self.s
        inc = self.open_incidents()
        if inc:
            last = inc[-1]
            what = ("they said \"%s\"" % last["words"]) if last["words"] else {
                "hit_deliberate": "they hit you on purpose", "hit_careless": "they hit you, carelessly",
                "threat": "they threatened you", "let_them": "they stood by and said nothing while someone hurt you"
            }.get(last["kind"], "they hurt you")
            n = sum(1 for i in s["incidents"] if i["intent"] == "deliberate" and now - i["t"] < 3 * DAY)
            again = (" It's not the first time (%d times in the last days)." % n) if n >= 3 else ""
            if last["state"] == "probation":
                return ("Earlier %s %s.%s They apologised; you want to believe it, so you're watching whether they "
                        "mean it." % (what, ago_words(now - last["t"]), again))
            return "%s %s.%s" % (what[0].upper() + what[1:], ago_words(now - last["t"]), again)
        if now - s.get("repaired_at", -1e12) < 10 * MINUTE:
            return "You've made up: you can say so once, simply."
        bad = [b for b in s["beliefs"] if not b["good"]]
        if bad:
            return "What you've come to believe about them: %s." % bad[0]["text"]
        return ""

    def summary(self, now):
        return SUMMARIES.get(self.stance(now), "")

    def explain(self, now):
        """Everything the dashboard shows: the five feelings, the stance, the ledger, why."""
        s = self.s
        return {
            "affection": round(s["a"], 1), "trust": round(s["t"], 1), "respect": round(s["r"], 1),
            "familiarity": round(s["f"], 1), "resentment": round(s["g"], 1), "sting": round(self.sting(now), 2),
            "stance": self.stance(now), "summary": self.summary(now), "bond": self.bond(),
            "pattern": round(self.pattern(now), 2), "credit": round(self.credit(now), 2), "floor": self.floor(),
            "incidents": [{"id": i["id"], "kind": i["kind"], "words": i["words"], "intent": i["intent"],
                           "severity": i["severity"], "state": i["state"], "ago": ago_words(now - i["t"]),
                           "probation": [round(i.get("done", 0) / 60), round(i.get("need", 0) / 60)]
                           if i["state"] == "probation" else None}
                          for i in s["incidents"][-10:]],
            "beliefs": s["beliefs"], "temperament": s["temperament"], "gesture": s.get("gesture"),
            "log": s["log"][-12:],
        }

    # ------------------------------------------------------------------ inside

    def _repair(self, i, now):
        s = self.s
        s["t"] = clamp(s["t"] + 0.7 * i["t_lost"])  # the other 30% only comes back with time: she remembers
        s["g"] = clamp(s["g"] - i["g_left"])
        i["g_left"], i["state"], i["repaired_t"] = 0.0, "repaired", now
        s["repaired_at"] = now

    def _scar(self, now):
        """A pattern (or a betrayal) leaves a scar: the worst recent hurt, held until it heals."""
        s = self.s
        if any(i["state"] == "scar" and now - i["t"] < DAY for i in s["incidents"]):
            return
        cands = [i for i in s["incidents"] if i["intent"] == "deliberate" and i["state"] != "repaired"]
        if not cands:
            return
        worst = max(cands, key=lambda i: i["severity"] * i["mult"])
        worst["state"] = "scar"
        self.new_scars.append(worst)

    def _log(self, now, event, words, intent, notes, change, sting):
        parts = ["%s %+.1f" % (n, change[k]) for k, n in (("a", "affection"), ("t", "trust"), ("r", "respect"),
                                                          ("g", "resentment")) if abs(change.get(k, 0)) >= 0.05]
        if sting:
            parts.append("sting %.2f" % sting)
        line = "%s%s%s%s → %s" % (event, (' "%s"' % words[:50]) if words else "", (" — " + intent) if intent else "",
                                  (" · " + " · ".join(notes)) if notes else "", ", ".join(parts) or "no change")
        self.s["log"] = (self.s["log"] + [{"t": now, "line": line}])[-40:]
        self.last_line = line
