"""Things you can ask the companion to *do* that need no AI: "stay here", "come here",
"look at me", "do a spin". Recognized in a millisecond, acted on at once, and the AI is told
it already happened so its answer fits ("Okay, I'll wait right here!").

Each rule is a regular expression on what you said (lowercase) and the act it sends to the mod:
  move:  stay | follow | come | stop (stop leading the way)        side: left | right | above | auto
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
    (r"\b(stop (guiding|leading)( me)?|you can stop( now)?|we'?re here)\b", {"move": "stop"}, "stop leading the way"),
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


# Clear requests for an action: the AI is then required to use that tool (when allowed), so it
# can't just *say* it placed a torch without doing it.
ACTION_HINTS = [
    (r"\b(always|every time|whenever)\b.{0,40}\b(protect|defend|help|tell|warn|notify|let me know)\b|"
     r"\b(protect|defend|tell|warn|notify) me (always|every time|whenever)\b|\blet me know when\b", "standing_request"),
    (r"\b(place|put|light|drop)\b.{0,30}\btorch|\btorch\b.{0,20}\b(here|down|please)", "place_torch"),
    (r"\b(push|knock|blast|keep|get)\b.{0,30}\b(away|back|off)\b|\bprotect me\b|\bhelp\b.{0,20}\b(zombies?|skeletons?|creepers?|spiders?|monsters?|mobs?)\b", "protect"),
    (r"\b(give|gimme|get) me\b|\bcan i (have|get)\b", "give_item"),
    (r"\b(take|lead|guide|bring|show) (me|us)\b", "guide"),
    (r"\b(find|where|any|nearest|closest|look for)\b.{0,40}\b(diamonds?|iron|gold|coal|copper|redstone|lapis|emeralds?|quartz|ancient debris|netherite)\b", "find_ore"),
    (r"\b(find|where|nearest|closest|locate)\b.{0,40}\b(village|mineshaft|shipwreck|ruined portal|monument|mansion|stronghold|fortress|bastion|temple|witch hut|igloo|outpost|ancient city|trail ruins|trial chambers?|end city|buried treasure|biome|grove|forest|desert|jungle|ocean|mushroom)", "locate"),
    (r"\bmake it (day|night|morning|sunrise|sunset|noon)\b|\bset the time\b|\bskip the night\b", "set_time"),
    (r"\bremind me\b", "set_reminder"),
    (r"\b(this is|here is|here's) (my|our) \w+|\bremember (this|that) (place|spot)\b|\bcall this (place|spot)\b", "name_place"),
    (r"\bremember (that|this)?\b|\bdon'?t forget\b", "remember"),
    (r"\b(stop the rain|make it (rain|sunny|clear|storm)|clear (the|up the) weather)\b", "set_weather"),
]
_hints = [(re.compile(p), tool) for p, tool in ACTION_HINTS]


def action_hint(text, allowed):
    """The tool a clear request asks for, if it's allowed; else None."""
    t = (text or "").lower()
    for rx, tool in _hints:
        if tool in allowed and rx.search(t):
            return tool
    return None


YES = re.compile(r"^\s*(yes|yeah|yep|yup|sure|please|ok(ay)?|go ahead|do it|help( me)?)\b", re.I)
PUT_BACK = re.compile(r"\b(put|give|bring) (it|that|my block|the block|them) back\b|\bwhere(?:'s| is| did) my block\b", re.I)


ARRIVED_LINES = [
    "We're here! Ta-da!",
    "Here we are! That wasn't so far, was it?",
    "We made it! What a trip!",
    "Here it is! I told you I'd find it!",
]

PET_LINES = [
    "Hehe, that tickles!",
    "Aww, thank you!",
    "I like you too!",
    "Wheee, more please!",
    "You're the best, you know that?",
]
