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
    (r"\bwink\b", {"emote": "tease"}, "wink"),
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
    (r"\b(place|put|light|drop)\b.{0,30}\btorch|\btorch\b.{0,20}\b(here|down|please)|\b(give|make|need|want|some)"
     r"( me| us)?( some| a)? light\b|\blight (it|this|that|the way|us|things|everything|our way) up\b|"
     r"\blight (it|this|the way|our way)\b|\bcan'?t see\b|\bhelp (me|us) see\b|\btoo dark\b", "place_torch"),
    (r"\b(push|knock|blast|keep|get)\b.{0,30}\b(away|back|off)\b|\bprotect me\b|\bhelp\b.{0,20}\b(zombies?|skeletons?|creepers?|spiders?|monsters?|mobs?)\b|"
     r"\b(i'?m|i am|we'?re|we are) (being )?(attacked|under attack|getting (shot|hit|attacked))\b|\b(save|defend) me\b|"
     r"\b(is|are|re|theyre|s|they|it)\s?(shooting|attacking|hitting) (me|us)\b", "protect"),
    (r"\b(place|put)\b.{0,12}\b(this|that|the|a|my|one) block\b", "build"),
    # "set up three vertical wood blocks here", "place 4 wood blocks vertically", "place two above it",
    # "put something on the ground" (numbers in words are digits by now: see action_hint)
    (r"\b(place|put|set( up)?|stack|lay)\b.{0,30}\b(\d+|some|a few|more)\b.{0,20}\b(blocks?|logs?|planks?|wood|"
     r"stones?|cobble\w*|bricks?|dirt|glass)\b|\b(place|put|stack|set)\b.{0,40}\b(vertical(ly)?|on top( of)?|above (it|"
     r"that|this|them)|upwards?|on the ground|in a (row|line|column))\b", "build"),
    (r"\bbuild\b.{0,15}\b(house|hut|shelter|walls?|tower|room|pen|fence|floor|platform|pillar)\b", "build"),
    (r"(^|\b(can|could|would|will) you\b.{0,15}|\bplease\b.{0,10}|\bpip\b.{0,10})\b(stack|pile|place|put|build|make|"
     r"raise)\b.{0,40}\b(pillars?|columns?|towers?|corners?|walls?|floors?|platforms?|outlines?|borders?|pens?|"
     r"on top of each other|blocks? (high|tall|up)|\d+ blocks?)\b", "build"),
    (r"\b(chop|cut|fell|harvest|break|mine|dig out|knock down)\b.{0,25}\b(tree|trees|log|logs|wood|this|that|block|it|"
     r"stone|ore|rock)\b|\bget (me )?(some )?wood\b", "harvest"),
    (r"\b(give|gimme|get|cast|put)\b.{0,25}\b(haste|night ?vision|speed|swiftness|regen(eration)?|fire resistance|"
     r"water breathing|jump boost|strength|resistance|slow falling|invisibility|effects?|health|hearts?)\b|"
     r"\bheal (me|him|her|us|them)\b|\b(fill|refill) (my|his|her) (health|hearts|hunger)\b", "give_effect"),
    (r"\b(give|gimme|get) me\b|\bcan i (have|get)\b", "give_item"),
    (r"\b(find|where|any|nearest|closest|look for|lead me to|take me to|show me|bring me to)\b.{0,40}\b(flowers?|"
     r"pumpkins?|melons?|sugar ?cane|bamboo|cactus|chests?|beds?|water|trees?|mushrooms?|berr(y|ies)|wheat|carrots?|"
     r"potatoes|crafting table|furnace|lily pads?)\b(?!\s*(base|home|house|farm|spot|place|patch))", "find_block"),
    (r"\b(take|lead|guide|bring|show) (me|us)\b|\blead the way\b|\bshow( me)? the way\b|\b(i'?ll|i will|we'?ll) "
     r"follow you\b|\bgo ahead,? i'?ll follow\b|\bwhich way\b", "guide"),
    (r"\b(find|where|any|nearest|closest|look for|search|see)\b.{0,40}\b(sheeps?|cows?|pigs?|chickens?|horses?|"
     r"donkeys?|villagers?|wolf|wolves|cats?|foxes|fox|rabbits?|bees?|goats?|llamas?|camels?|frogs?|turtles?|"
     r"axolotls?|parrots?|pandas?|animals?|mooshrooms?)\b", "find_animal"),
    (r"\b(find|where|any|nearest|closest|look for)\b.{0,40}\b(diamonds?|iron|gold|coal|copper|redstone|lapis|emeralds?|quartz|ancient debris|netherite)\b", "find_ore"),
    (r"\b(find|where|nearest|closest|locate)\b.{0,40}\b(village|mineshaft|shipwreck|ruined portal|monument|mansion|stronghold|fortress|bastion|temple|witch hut|igloo|outpost|ancient city|trail ruins|trial chambers?|end city|buried treasure|biome|grove|forest|desert|jungle|ocean|mushroom)", "locate"),
    (r"\bmake it (day|night|morning|sunrise|sunset|noon)\b|\bset the time\b|\bskip the night\b", "set_time"),
    (r"\bremind me\b", "set_reminder"),
    (r"\b(this is|here is|here's) (my|our) \w+|\bremember (this|that) (place|spot)\b|\bcall this (place|spot)\b", "name_place"),
    (r"\bremember (that|this)?\b|\bdon'?t forget\b", "remember"),
    (r"\b(stop the rain|make it (rain|sunny|clear|storm)|clear (the|up the) weather)\b", "set_weather"),
]
_hints = [(re.compile(p), tool) for p, tool in ACTION_HINTS]
STANDING = re.compile(ACTION_HINTS[0][0], re.I)


COMMON = set("water lava fire night light dark home house cave tree trees stone wood iron gold diamond sand dirt "
             "grass flower flowers sheep cows pigs village farm base please there here where with what that this "
             "them they your mine craft block blocks door wall roof floor chest food bread apple apples".split())


def _close(word, name):
    """Speech-to-text spelling: "waleed" for "walid" (same consonants)."""
    strip = lambda x: re.sub(r"[aeiouy]", "", x)  # noqa: E731
    return len(strip(word)) >= 3 and strip(word) in strip(name)


def player_hint(text, names, allowed):
    """A request about another player here, named even roughly ("find walid", "stay with water walid")."""
    t = re.sub(r"[^a-z0-9 ]", "", (text or "").lower())
    flat = t.replace(" ", "")
    words = [w for w in t.split() if len(w) >= 4 and w not in COMMON]  # ("find water" is not "find waterwalid")
    named = [n for n in names or [] if len(n) >= 3 and (n.lower() in flat or any(w in n.lower() for w in words)
                                                        or any(_close(w, n.lower()) for w in words))]
    if not named:
        return None, None
    if "follow_player" in allowed and re.search(r"\b(follow|stay with|go with|be with|keep .{0,10} company|"
                                                 r"look after|watch over|hang out with)\b", t):
        return "follow_player", named[0]
    if "find_player" in allowed and re.search(r"\b(find|where|look for|search|lead|take|bring|guide|show)\b", t):
        return "find_player", named[0]
    return None, named[0]


NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
           "ten": 10, "twelve": 12, "twenty": 20}


def action_hint(text, allowed):
    """The tool a clear request asks for, if it's allowed; else None."""
    t = re.sub(r"\b(%s)\b" % "|".join(NUMBERS), lambda m: str(NUMBERS[m.group(1)]), (text or "").lower())
    for rx, tool in _hints:
        if tool in allowed and rx.search(t):
            return tool
    return None


_FOLLOW_UP = re.compile(r"\b(them|it|those|one|any|some)\b")
_SEEK = re.compile(r"\b(find|where|look for|search|see|spot)\b")
SEEKING = ("find_animal", "find_ore", "locate")


def hint_in_context(text, earlier, allowed):
    """"Can you find them?" right after "I need sheep": the thing to find was named earlier."""
    t = (text or "").lower()
    if not (_SEEK.search(t) and _FOLLOW_UP.search(t)):
        return None
    for prev in reversed(earlier[-3:]):
        tool = action_hint("find " + prev, [a for a in SEEKING if a in allowed])
        if tool:
            return tool
    return None


WRONG_WAY_LINES = ["Hey, this way! Follow me!", "Wrong way, silly! Over here!", "No no, it's this way!",
                   "Psst! I'm over here! Follow the sparkles!"]

# her own offers ("Should I light it up for you?"): a "yes" then means do exactly that
_OFFERING = re.compile(r"\b(should i|shall i|want me to|do you want me to|would you like me to|i could|i can try to|"
                       r"let me)\b", re.I)


def offered_in(her_line, allowed):
    """The action she just offered in her own words, if her line is an offer."""
    if not her_line or not _OFFERING.search(her_line):
        return None
    return action_hint(her_line, allowed)


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
