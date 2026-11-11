"""Things you can ask the companion to *do* that need no AI: "stay here", "come here",
"look at me", "do a spin". Recognized in a millisecond, acted on at once, and the AI is told
it already happened so its answer fits ("Okay, I'll wait right here!").

Each rule is a regular expression on what you said (lowercase) and the act it sends to the mod:
  move:  stay | follow | come        side: left | right | above | auto
  look:  me | there | ahead | up | down | around
  emote: nod | shake | spin | hop | wiggle | happy | shy | think | doze
Add new ones at the bottom of RULES (and a test in tests/test_intents.py).
"""
import re

RULES = [
    # moving
    (r"\b(stay|wait)( right)?( here| there| put)?\b(?! away)", {"move": "stay"}, "stay where you are"),
    (r"\b(follow me|come with me|let'?s go|come along)\b", {"move": "follow"}, "follow the player again"),
    (r"\b(come (here|back|closer)|over here|get over here)\b", {"move": "come"}, "come close to the player"),
    (r"\b(go|float|move|fly|stay)( over)?( to)?( on)?( my| the)? left\b", {"side": "left"}, "float on the player's left"),
    (r"\b(go|float|move|fly|stay)( over)?( to)?( on)?( my| the)? right\b", {"side": "right"}, "float on the player's right"),
    (r"\b(above|over) (me|my head|my shoulder)\b", {"side": "above"}, "float above the player's shoulder"),
    # looking
    (r"\blook at me\b", {"look": "me", "seconds": 4}, "look at the player"),
    (r"\blook (at )?(that|this|there|over there)\b", {"look": "there", "seconds": 4}, "look where the player looks"),
    (r"\blook up\b", {"look": "up", "seconds": 3}, "look up"),
    (r"\blook down\b", {"look": "down", "seconds": 3}, "look down"),
    (r"\blook around\b", {"look": "around", "seconds": 4}, "look around"),
    # gestures
    (r"\b(spin|twirl|do a (spin|flip|twirl)|turn around)\b", {"emote": "spin"}, "do a spin"),
    (r"\b(jump|hop|bounce)\b", {"emote": "hop"}, "hop"),
    (r"\b(dance|wiggle)\b", {"emote": "wiggle"}, "wiggle"),
    (r"\bnod\b", {"emote": "nod"}, "nod"),
    (r"\bshake your head\b", {"emote": "shake"}, "shake its head"),
    (r"\b(go to sleep|take a nap|nap time|sleep now)\b", {"emote": "doze"}, "doze off"),
]

_compiled = [(re.compile(p), act, what) for p, act, what in RULES]


def match(text):
    """Returns (acts, descriptions) for everything asked in this sentence."""
    t = (text or "").lower()
    acts, done = [], []
    used = set()
    for rx, act, what in _compiled:
        key = next(iter(act))
        if key in used:  # one move, one look, one gesture per sentence
            continue
        if rx.search(t):
            acts.append(dict(act))
            done.append(what)
            used.add(key)
    return acts, done


PET_LINES = [
    "Hehe, that tickles!",
    "Aww, thank you!",
    "I like you too!",
    "Wheee, more please!",
    "You're the best, you know that?",
]
