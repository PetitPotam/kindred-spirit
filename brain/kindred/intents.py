"""Things you can ask the companion to *do* that need no AI: "stay here", "come here",
"look at me", "do a spin". Recognized in a millisecond, acted on at once, and the AI is told
it already happened so its answer fits ("Okay, I'll wait right here!").

Each rule is a regular expression on what you said (lowercase) and the act it sends to the mod:
  move:  stay | follow | come | stop (stop leading the way)        side: left | right | above | auto
  look:  me | there | ahead | up | down | around
  emote: nod | shake | spin | hop | wiggle | happy | shy | think | doze | tease
  perform: a little show of several gestures (the brain plays them one after the other)
Add new ones at the bottom of RULES (and a test in tests/test_intents.py).
"""
import re

RULES = [
    # moving
    # (stand still / don't move / freeze: she said "Frozen!" and kept following)
    (r"\b(stand|hold|stay|keep|be) (still|put)\b|\bdon'?t (move|follow( me)?)\b|\bstop (moving|following( me)?)\b|"
     r"\bfreeze\b|\bstop right there\b|\b(stay|wait)( right)?( here| there| put)?\b(?! away| with| close| by| near| beside)",
     {"move": "stay"}, "stay where you are"),
    # (never a reason to lead anywhere: "follow me" twice sent her 488 blocks to the old plains)
    (r"\b(follow (me|us)|keep following|come with (me|us)|stay (with|close to|by|near) (me|us)|let'?s go|come along)\b",
     {"move": "follow"}, "follow the player again (beside them: not leading anywhere)"),
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
    # her glow ("hey pip light the way" got "my light's being shy"): brighter for a few minutes, or off
    (r"\b(stop glowing|glow off|don'?t glow|turn (your|the) (light|glow) off|dim (your|the) light)\b",
     {"glow": "off", "seconds": 600}, "stop glowing for a while"),
    (r"(^|\bpip,? |\bplease |\bcan you |\bcould you )(glow|shine)\b|\b(glow|shine) (brighter|more|for (me|us)|up)\b|"
     r"\blight the way\b|\blight (us|me) up\b|\bbe (my|our|a) "
     r"(light|lantern|torch)\b|\b(make|give) (some |more )?light\b(?! level)", {"glow": "bright", "seconds": 180},
     "glow brighter for a few minutes (you're the light: no torch needed)"),
    # a little show: several gestures in a row (asked for "fancy emotes", she gave enchanted apples)
    (r"\b(do|show( me)?|perform|make)\b.{0,25}\b(emotes?|tricks?|moves|a dance|a show|gestures|dance moves)\b|"
     r"\bshow off\b", {"perform": True}, "a little show of your gestures (spins, hops, a wink)"),
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
    (r"\b(always|every time|whenever|from now on|all the time|keep)\b.{0,40}\b(protect|defend|help|tell|warn|notify|let me "
     r"know|protecting|defending|guarding)\b|\b(protect|defend|tell|warn|notify|guard) (me|us|him|her|them|\w+) (always|every "
     r"time|whenever|from now on|all the time)\b|\blet me know when\b|\b(protect|defend|guard|keep) (me|us)( safe)? from\b.{0,80}"
     r"\b(and )?(everything|everyone|all of them|anything|all the monsters|all monsters|mobs)\b|"
     r"\b(follow|stay with|go with) and (protect|defend|guard)\b|\b(protect|defend|guard) and (follow|stay with)\b|"
     r"\b(look after|watch over|guard) (him|her|them|\w+) for (me|us)\b", "standing_request"),
    (r"\b(place|put|set|drop)\b.{0,30}\b(campfire|bed|chest|barrel|door|crafting table|furnace|lantern|anvil|"
     r"enchanting table|bookshel(f|ves)|cauldron|bell|smoker|blast furnace|loom|composter|beacon|jukebox|"
     r"flower ?pot|ladder|sign|banner|trapdoor|fence gate)\b|\b(campfire|bed|chest|door)\b.{0,15}\b(here|there)\b",
     "build"),
    (r"\b(place|put|light|drop)\b.{0,30}\btorch|\btorch\b.{0,20}\b(here|down|please)|\b(give|make|need|want|some)"
     r"( me| us)?( some| a)? light\b(?=.{0,20}\btorch)|\blight (it|this|that|things|everything) up\b|"
     r"\blight (it|this)\b|\bcan'?t see\b|\bhelp (me|us) see\b|\btoo dark\b", "place_torch"),
    (r"\b(poke|prod|boop|bonk|tickle)\b|\b(hit|push|shove|smack|tap)\b.{0,15}\b(playfully|for fun|gently|a little)\b|"
     r"\b(push|knock|blast|keep|get)\b.{0,30}\b(away|back|off)\b|\bprotect me\b|\bhelp\b.{0,20}\b(zombies?|skeletons?|creepers?|spiders?|monsters?|mobs?)\b|"
     r"\b(i'?m|i am|we'?re|we are) (being )?(attacked|under attack|getting (shot|hit|attacked))\b|\b(save|defend) me\b|"
     r"\b(is|are|re|theyre|s|they|it)\s?(shooting|attacking|hitting) (me|us)\b", "protect"),
    (r"\b(place|put)\b.{0,12}\b(this|that|the|a|my|one) block\b", "build"),
    # "set up three vertical wood blocks here", "place 4 wood blocks vertically", "place two above it",
    # "put something on the ground" (numbers in words are digits by now: see action_hint)
    (r"\b(place|put|set( up)?|stack|lay)\b.{0,30}\b(\d+|some|a few|more)\b.{0,20}\b(blocks?|logs?|planks?|wood|"
     r"stones?|cobble\w*|bricks?|dirt|glass)\b|\b(place|put|stack|set)\b.{0,40}\b(vertical(ly)?|on top( of)?|above (it|"
     r"that|this|them)|upwards?|on the ground|in a (row|line|column))\b", "build"),
    (r"\b(flatten|level( out)?|clear( out| away)?|remove|dig away|get rid of|squash)\b.{0,40}\b(ground|land|area|hill|"
     r"terrain|space|blocks?|everything|this|it|above|trees?|dirt|grass)\b|\bmake (it|this|the (ground|area|land)) "
     r"(flat|level)\b", "build"),
    (r"\b(make|build|create|open|light)\b.{0,25}\b(nether )?portal\b", "build"),
    (r"\b(build|make|create)\b.{0,25}\b(a |an |our |my )?(house|home|hut|cabin|shelter|cottage)\b", "build"),
    (r"(^|\b(can|could|would|will) you\b.{0,15}|\bplease\b.{0,10}|\bpip\b.{0,10})\bbuild\b.{0,15}\b(house|hut|"
     r"shelter|walls?|tower|room|pen|fence|floor|platform|pillar)\b", "build"),
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


def same_person(said, name):
    """Is this (said roughly, maybe misheard) this player's name? "walid", "water walid" -> waterwalid."""
    a = re.sub(r"[^a-z0-9]", "", (said or "").lower())
    b = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    if len(a) < 3 or not b:
        return False
    return a == b or a in b or b in a or _close(a, b)


# words that do ask for a trip ("follow me to the village", "lead us home")
LEADING = re.compile(r"\b(lead|guide|take|bring|show)\b.{0,20}\b(me|us|the way|there|home|back)\b|\bto the\b|\bwhere is\b",
                     re.I)


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


# a block they named ("with dirt", "cherry planks"): kept for the build that follows, even a message later
_WOODS = "oak|spruce|birch|jungle|acacia|dark oak|mangrove|cherry|bamboo|crimson|warped"
BLOCK_WORD = re.compile(r"\b((?:%s) (?:planks?|logs?|wood|slabs?|stairs)|(?:stone |mossy |cracked )?(?:stone )?bricks?|"
                        r"cobblestone|cobble|smooth stone|stone|deepslate|dirt|grass block|sand(?:stone)?|red sand|gravel|glass|"
                        r"(?:white|black|red|blue|green|yellow|orange|pink|purple|cyan|lime|gray|light blue|magenta|brown) "
                        r"(?:wool|concrete|terracotta|glass)|wool|concrete|terracotta|obsidian|andesite|granite|diorite|"
                        r"tuff|calcite|clay|mud bricks?|quartz|prismarine|blackstone|netherrack|snow block|ice|planks?|logs?)\b"
                        % _WOODS, re.I)


def block_named(texts):
    """The block they named most recently (newest message first), as an id: "cherry planks" -> cherry_planks."""
    for t in reversed([x for x in texts if x]):
        found = BLOCK_WORD.findall(t)
        if found:
            w = found[-1].lower().strip()
            w = {"cobble": "cobblestone", "plank": "planks", "log": "logs", "brick": "bricks"}.get(w, w)
            if re.fullmatch(r"(%s) (plank|log|slab|stair)" % _WOODS, w):
                w += "s"
            w = re.sub(r"\b(planks|logs|slabs|stairs)\b", lambda m: {"planks": "planks", "logs": "log", "slabs": "slab",
                                                                      "stairs": "stairs"}[m.group(1)], w)
            return w.replace(" ", "_")
    return ""


# a friend asking where they are (answered from where the player stands)
WHERE_AM_I = re.compile(r"\bwhere am i\b|\bwhere('?s| is) my position\b|\bhow far (am i|is \w+) from\b", re.I)
# "for both of us", "for me and him": each gets one
BOTH = re.compile(r"\b(both of us|for us\b|us both|each of us|all of us|for (me|him|her) and (me|him|her|\w+)|"
                  r"for everyone)\b", re.I)
_VOUCH = re.compile(r"\b(do what|listen to|obey|take orders from|you can follow|follow) (\w[\w ]{1,20}?)( says| asks| tells you)?"
                    r"\b.{0,20}$|\b(from now on|you can)\b.{0,25}\b(do what|listen to|obey|follow) (\w[\w ]{1,20}?)( says| asks)?\b",
                    re.I)
_UNVOUCH = re.compile(r"\b(don'?t|do not|stop|no longer)\b.{0,10}\b(listen(ing)? to|obey(ing)?|taking orders from|"
                      r"do(ing)? what) (\w[\w ]{1,20}?)( says| asks)?\b", re.I)


def vouches_for(text, here, known=()):
    """"From now on do what Walid says" -> (the friend, True); "stop listening to him" -> (friend, False). For a name
    she knows (a player here or a friend she's met, said even roughly); a nickname ("do what Dumber says") when only
    one friend is here means that one."""
    t = (text or "").strip()
    for rx, yes, group in ((_UNVOUCH, False, 6), (_VOUCH, True, None)):
        m = rx.search(t)
        if not m:
            continue
        said = m.group(group) if group else (m.group(2) or m.group(6) or "")
        said = re.sub(r"\b(says|asks|tells|you|me|the|my|brother|friend)\b", "", said, flags=re.I).strip()
        if not said or said.lower() in ("i", "it", "that", "this", "what", "them", "us"):
            continue
        hit = next((n for n in list(here) + list(known) if n and same_person(said, n)), None)
        if hit:
            return hit, yes
        others = [n for n in here if n]
        if len(others) == 1 and (yes or re.search(r"\b(him|her|them)\b", said, re.I) is None):
            return others[0], yes
    return None


# their pronouns, said ("I am a him, not a her", "I'm a boy", "my pronouns are they/them")
PRONOUNS = re.compile(r"\b(?:i'?m|i am)( not)? an? (him|her|he|she|boy|girl|guy|man|woman|dude|lady)\b|\bmy pronouns are "
                      r"(\w+(?:/\w+)?)|\b(?:call me|use) (he|she|they)(?:/(him|her|them))?\b", re.I)
_PRON = {"him": "he/him", "he": "he/him", "boy": "he/him", "guy": "he/him", "man": "he/him", "dude": "he/him",
         "her": "she/her", "she": "she/her", "girl": "she/her", "woman": "she/her", "lady": "she/her",
         "they": "they/them", "them": "they/them"}


def pronouns_said(text):
    """The pronouns they just told her, or "" ("I am a him, not a her" -> he/him)."""
    for m in PRONOUNS.finditer(text or ""):
        if m.group(2) and not m.group(1):
            return _PRON.get(m.group(2).lower(), "")
        if m.group(3):
            w = m.group(3).lower()
            return w if "/" in w else _PRON.get(w, "")
        if m.group(4):
            return _PRON.get(m.group(4).lower(), "")
    return ""


DIARY = re.compile(r"\b(your|ur|her|pip'?s) diary\b|\bdiary\b.{0,20}\b(write|wrote|say|read|tell)\b|\bwhat did you write\b", re.I)

# a place she remembers on her own, asked for in words ("back to where I died", "where we saw the first cow")
BACK_TO_SPOT = re.compile(r"\bwhere (i|we|you) (died|saw|met|found|built|were building|was building|slept|started)\b|"
                          r"\b(the )?first (\w+ ){0,2}(we|i) (saw|met|found)\b|\bwhat i was building\b|"
                          r"\b(my|our|the) (bed|chest|building|build|portal|house)\b", re.I)

# speech-to-text: what it should expect (names, Minecraft words), and names it mishears, put right afterwards
MC_WORDS = ("Minecraft, creeper, zombie, skeleton, enderman, ender pearl, Nether, the End, villager, diamond, "
            "netherite, redstone, obsidian, crafting table, furnace, pickaxe, axe, coordinates, biome, cherry grove, "
            "spawn, Elytra, totem, enchant, efficiency, potion, torch, wolf, sheep, cow.")
HER_NAME_MISHEARD = re.compile(r"^\s*(q|pep|peep|pib|bip|pipp|pit|piv|beep|pipe)\b[,!.]?\s*", re.I)


def stt_prompt(her_name, people):
    """The prompt for speech-to-text: her name, the people she knows (names and nicknames), Minecraft words."""
    names = ", ".join(dict.fromkeys(n for n in [her_name] + list(people) if n))
    return "%s. %s" % (names, MC_WORDS)


def fix_names(text, her_name, people):
    """Names speech-to-text got nearly right ("Waleed" for Walid, "Q," or "Pep," for Pip at the start): put right.
    Only capitalized words (it writes names that way) and her name at the very start, so ordinary words stay."""
    t = HER_NAME_MISHEARD.sub(her_name + ", ", text or "", count=1) if her_name else text or ""

    def fix(m):
        w = m.group(0)
        if w.lower() in COMMON or len(w) < 4:
            return w
        hit = next((n for n in people if n and n.lower() != w.lower() and _close(w.lower(), n.lower())
                    and abs(len(w) - len(n)) <= 4), None)
        return hit or w
    t = re.sub(r"\b[A-Z][a-z]{3,}\b", fix, t)
    for rx, word in MC_FIXES:
        t = rx.sub(word, t)
    return t


# Minecraft words it mishears (heard in play): put right after transcription
MC_FIXES = [(re.compile(r"\b(under ?pair|under ?pearl|ender ?pair|end of pearl)s?\b", re.I), "ender pearl"),
            (re.compile(r"\b(nether ?right|nether ?white)\b", re.I), "netherite"),
            (re.compile(r"\b(red stone)\b", re.I), "redstone"),
            (re.compile(r"\b(ellie ?tra|ely ?tra)\b", re.I), "elytra")]


# the player stepping in for her ("stop hitting Pip", "leave her alone", "be nice to her")
DEFEND = re.compile(r"\b(stop|quit|don'?t|do not|no)\b.{0,12}\b(hit(ting)?|hurt(ing)?|punch(ing)?|attack(ing)?|"
                    r"bully(ing)?|being mean|being rude|insult(ing)?|tease|teasing|picking on)\b|\bleave (her|pip|it|them)"
                    r" alone\b|\bbe (nice|kind|gentle) (to|with) (her|pip)\b|\b(apologi[sz]e|say sorry) to (her|pip)\b|"
                    r"\bdon'?t (talk|speak) to (her|pip) like that\b|\bthat'?s (not nice|mean|rude)\b|\bback off\b", re.I)

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

FRIEND_HIT_LINES = {  # a friend hit her: [False] she still likes them, [True] she doesn't
    False: ["Ow! {who}! What was that for?", "Hey! {who}, I'm not a piñata!", "Oof. Rude, {who}."],
    True: ["Again, {who}? Stop it.", "Leave me alone, {who}.", "That's enough, {who}."],
}
FRIEND_PET_LINES = ["Hehe, thanks {who}!", "Ooh, {who} gives good pats.", "{who}! That tickles!"]

PET_LINES = [
    "Hehe, that tickles!",
    "Aww, thank you!",
    "I like you too!",
    "Wheee, more please!",
    "You're the best, you know that?",
]
