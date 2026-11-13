"""Facts about people: who is called what, their pronouns, who they are to the player (designs-2026-11.md, part 1).

Her memories are sentences, so the same thing said five ways piled up ("The player's nickname is Dumb", "...is
Damb", "Walid's nickname is Dumber" twice) and contradictions sat side by side. memory.replace_older already
deletes an older nickname or pronoun when a new one is remembered; this reads the sentences she keeps about
people into slots (person, key) where the newest value wins, so her prompt says it once, per person, in one
place: "People: the player (TamBoudX): nickname Dumb, he/him | waterwalid: the player's brother, nickname
Dumber". Nothing is stored differently: it's a view over the memories she has, so old worlds get it too.
"""
import re

WHO = r"(?P<who>the player|[A-Za-z0-9_]+)"
POSS = r"(?:'s)?(?: \([^)]*\))?"  # ("Walid's (waterwalid) nickname is...")
NAME = r"(?P<v>[A-Za-z0-9_][\w' -]{0,24}?)"
RELATIONS = ("brother", "sister", "cousin", "friend", "best friend", "dad", "father", "mum", "mom", "mother", "son",
             "daughter", "partner", "wife", "husband", "girlfriend", "boyfriend", "uncle", "aunt", "nephew", "niece",
             "classmate", "neighbour", "neighbor")
PATTERNS = [
    ("nickname", re.compile(r"^%s%s nick ?name is %s$" % (WHO, POSS, NAME), re.I)),
    ("nickname", re.compile(r"^%s (?:wants|likes|prefers|asked) to be called %s$" % (WHO, NAME), re.I)),
    ("nickname", re.compile(r"^%s goes by %s$" % (WHO, NAME), re.I)),
    ("pronouns", re.compile(r"^%s%s pronouns are (?P<v>he/him|she/her|they/them)\b" % (WHO, POSS), re.I)),
    ("name", re.compile(r"^the player(?:'s)? (?:real )?name is %s$" % NAME, re.I)),
    ("relation", re.compile(r"^%s(?: \([^)]*\))? is the player'?s (?P<v>%s)\b" % (WHO, "|".join(RELATIONS)), re.I)),
]


def parse(text):
    """[(who, key, value)] for each clause of a memory sentence that states a fact about a person."""
    out = []
    for clause in re.split(r"[.;]\s*|\s+and\s+(?=(?:the player|[A-Za-z0-9_]+)(?:'s)? (?:nick ?name|pronouns|name)\b)",
                          text or ""):
        c = clause.strip().rstrip(".!")
        for key, rx in PATTERNS:
            m = rx.match(c)
            if m:
                who = m.groupdict().get("who") or "the player"
                out.append((who.lower(), key, m.group("v").strip().strip("'\"")))
                break
    return out


def consumed(text):
    """True when every clause of the sentence is a fact read into a slot (then it needn't be said twice)."""
    clauses = [c for c in re.split(r"[.;]\s*|\s+and\s+(?=(?:the player|[A-Za-z0-9_]+)(?:'s)? (?:nick ?name|pronouns|name)\b)",
                                    text or "") if c.strip()]
    return bool(clauses) and len(parse(text)) == len(clauses)


def who_is(who, names, player_name=""):
    """'walid' -> 'waterwalid' when that's a player here; 'the player' (or their own name) stays the player."""
    w = who.lower()
    if w in ("the player", "player", "me", "i") or (player_name and w == player_name.lower()):
        return "the player"
    for n in names:
        if n and (n.lower() == w or (len(w) >= 4 and w in n.lower())):
            return n
    return who


def people(rows, here=(), player_name=""):
    """The 'People' line: per person, the newest value of each slot. rows: memories (text, created)."""
    slots = {}
    for r in sorted(rows, key=lambda r: r.get("created", 0)):  # (oldest first: the newest wins)
        for who, key, value in parse(r.get("text", "")):
            slots.setdefault(who_is(who, here, player_name), {})[key] = value
    if not slots:
        return ""
    parts = []
    for who in sorted(slots, key=lambda w: (w != "the player", w)):
        s = slots[who]
        label = "the player" + (" (%s)" % player_name if player_name and who == "the player" else "") \
            if who == "the player" else who
        bits = (["the player's " + s["relation"]] if "relation" in s else []) + \
               (["named %s" % s["name"]] if "name" in s else []) + \
               (["nickname %s" % s["nickname"]] if "nickname" in s else []) + \
               ([s["pronouns"]] if "pronouns" in s else [])
        parts.append("%s: %s" % (label, ", ".join(bits)))
    return "People (the latest of each is what's true now): " + " | ".join(parts) + "."
