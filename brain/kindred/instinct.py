"""System 0's own words, written by System 2.

Her instinct lines ("Ow! Hey!", "Creeper behind you!", "We're here!") must be instant, so they can't
wait for an AI. But fixed sentences repeat and don't sound like her. So the slower thinking AI writes
a handful for each moment, in her voice, from her personality, your bond, her story and tastes and
your name, once per session (and again when your bond changes level). They're kept per world; the
built-in lines stay as the fallback.
"""
import json
import random
import re

from . import heart as H
from . import intents as I

# each moment: what it is (for the AI), and the built-in lines it replaces
MOMENTS = {
    "hit": ("the player just hit you; it hurts and you're upset", H.HIT_LINES),
    "oof": ("the player hit you, probably by accident (you're friends)", H.OOF_LINES),
    "bonk": ("you playfully bonk the player back after they hit you by accident", H.BONK_LINES),
    "play_hit": ("you play-hit the player for fun, then say sorry and heal them", H.PLAY_HIT_LINES),
    "vanish": ("you're leaving for a while because the player hurt you", H.VANISH_LINES),
    "back": ("you come back after leaving because they hurt you, a bit shy", H.BACK_LINES),
    "clear": ("you feel better and the rain you cried stops; sunshine", H.CLEAR_LINES),
    "giggle": ("you just pranked the player (a creeper hiss or a boom behind them) and giggle", H.GIGGLES),
    "sulk": ("you pranked the player out of spite because they were mean to you", H.SULK_PRANKS),
    "borrow": ("you secretly took a block they just placed (it's in their pockets)", H.BLOCK_PRANK),
    "pet": ("the player is petting you", I.PET_LINES),
    "arrived": ("you arrived where you were leading the player", I.ARRIVED_LINES),
    "wrong_way": ("the player walked the wrong way while you lead them", I.WRONG_WAY_LINES),
    "shoo": ("you just pushed monsters away from the player (say 'you' or their name, not he/she)", ["Shoo! Leave them alone!", "Back off!", "Not my friend!"]),
    "thinking": ("a tiny sound while you think about what they just asked: 1 to 4 words (\"Hmm...\")",
                 ["Hmm...", "Ooh, let me think...", "Hmm, good question..."]),
    "creeper": ("URGENT warning: a creeper is close, {where}. Very short.", None),
    "low_health": ("URGENT warning: the player has only {hearts} hearts left. Short.", None),
    "lava": ("URGENT warning: lava {where}. Very short.", None),
    "drop": ("warning: a big drop {where}. Short.", None),
}
NEEDS = {"creeper": "{where}", "lava": "{where}", "drop": "{where}", "low_health": "{hearts}"}
PER_MOMENT = 6


def prompt(name, who_she_is, bond_level, player_name):
    moments = "\n".join('  "%s": %s' % (k, v[0]) for k, v in MOMENTS.items())
    return (
        "You are writing the instant, spoken reactions of %s, an ancient spirit with a child's heart who floats "
        "beside the player in Minecraft (not a girl or a boy, not young or old; a bit of an oddball with opinions). "
        "Minecraft is their real world: no game words, no buttons, no numbers except {hearts}. Casual and spoken: "
        "contractions, little sounds (eep, pff, hm), odd turns of phrase; not sugary, not needy. Short lines "
        "(under 70 characters), no emojis or asterisks; use the player's name only now and then.\n"
        "Who she is right now:\n%s\nHer bond with the player: %s.%s Never call the player by her own name or nickname.\n\n"
        "Write %d different lines for each moment below, in her own voice and colored by how she feels about the "
        "player (warmer and more teasing when close, shorter and colder when hurt). Keep {where} or {hearts} exactly "
        "as written where a moment has it (it becomes 'behind you', '2'...). Vary them; no line twice.\n%s\n\n"
        "Answer with one JSON object: {\"moment\": [\"line\", ...], ...}."
        % (name, who_she_is or "(she's only just met the player)", bond_level,
           (" The player's name is %s; use it now and then." % player_name) if player_name else "",
           PER_MOMENT, moments))


def clean(raw):
    """Keeps only usable lines: short, spoken, with the placeholder a moment needs and no other."""
    out = {}
    for k, lines in (raw or {}).items():
        if k not in MOMENTS or not isinstance(lines, list):
            continue
        good = []
        for line in lines:
            if not isinstance(line, str):
                continue
            line = re.sub(r"\s+", " ", line).strip().strip('"')
            braces = set(re.findall(r"\{\w+\}", line))
            need = NEEDS.get(k)
            if not 2 <= len(line) <= 90 or "[" in line or "*" in line:
                continue
            if (need and need not in braces) or braces - ({need} if need else set()):
                continue
            try:  # it must really fill in (a stray "{" or "}" would crash a warning later)
                filled = line.format(where="behind you", hearts="3")
            except (ValueError, KeyError, IndexError):
                continue
            if "{" in filled or "}" in filled:
                continue
            if line not in good:
                good.append(line)
        if good:
            out[k] = good
    return out


class Instinct:
    """Her instinct lines for this world: picks one, never the same as the last few."""

    def __init__(self, rng=None):
        self.lines, self.level, self.recent = {}, None, []
        self.rng = rng or random.Random()

    def pick(self, moment, fallback=None):
        pool = self.lines.get(moment) or fallback or (MOMENTS.get(moment, ("", None))[1]) or []
        fresh = [x for x in pool if x not in self.recent] or pool
        if not fresh:
            return None
        line = self.rng.choice(fresh)
        self.recent = (self.recent + [line])[-8:]
        return line

    def personal(self, text):
        """A built-in line said on instinct, swapped for one of hers for the same moment."""
        for moment, (_, builtin) in MOMENTS.items():
            if builtin and text in builtin and self.lines.get(moment):
                return self.pick(moment) or text
        return text

    def load(self, doc):
        self.lines = clean((doc or {}).get("lines"))
        self.level = (doc or {}).get("level")


def parse(content):
    m = re.search(r"\{.*\}", content or "", re.S)
    try:
        return clean(json.loads(m.group(0))) if m else {}
    except ValueError:
        return {}
