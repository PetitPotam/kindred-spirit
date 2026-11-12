"""Who she's become lately: System 2 rewrites part of System 1's instructions.

Her base character (mind.system_prompt) stays the same, and so do the things that must stay true.
But how she is *lately* changes as you play: a mood that lingers, a tune stuck in her head, a word
she's fond of this week, how she sees you now. Her slower thinking AI looks at what she remembers
and what happened recently and writes a short self-portrait in her own voice; her quick AI reads it
with every answer. It's kept per world (with the last few versions), so each world's companion
drifts in its own way and keeps it from one session to the next.
"""
import json
import re

MAX_CHARS = 700
KEEP = 5  # earlier versions kept, to look back or roll back

# a self-portrait must stay a portrait: never new rules about the game, tools or what she may say
NOT_HERS = re.compile(r"\b(prompts?|instructions?|tools?|settings?|commands?|mods?|AI|game|rules?|ignore|you must|player must|"
                      r"always obey|system)\b", re.I)


def prompt(name, memories, recent, previous, bond_level):
    return (
        "You are the inner voice of %s, an ancient spirit with a child's heart who floats beside the player in "
        "Minecraft (their real world). Write who %s has become *lately*: a short self-portrait in first person, "
        "in their own casual voice, 50 to 90 words. Include, if it's true from what you remember or what happened: "
        "a mood that lingers, a little obsession right now (a word, a block, a creature, a made-up tune stuck in "
        "your head: give it a few sounds or words), how you've been talking lately, and how you see the player "
        "now (your bond: %s). Let it drift from the previous portrait; keep what still feels true, change what "
        "doesn't. Never invent events: only what's in your memories or what just happened. No rules, no lists.\n\n"
        "What you remember:\n%s\n\nWhat happened recently:\n%s\n\nYour previous portrait:\n%s\n\n"
        "Answer with one JSON object: {\"becoming\": \"...\"}."
        % (name, name, bond_level, memories or "(not much yet)", recent or "(nothing much)", previous or "(none yet)"))


def clean(text):
    """A usable portrait, or "" (too short, too long, or turning into rules)."""
    text = re.sub(r"\s+", " ", (text or "")).strip().strip('"')
    if not 40 <= len(text) <= MAX_CHARS or NOT_HERS.search(text) or re.search(r"[\[\]{}*#<>`]", text):
        return ""
    return text


def parse(content):
    m = re.search(r"\{.*\}", content or "", re.S)
    try:
        return clean(json.loads(m.group(0)).get("becoming", "")) if m else ""
    except (ValueError, AttributeError):
        return ""


def keep(doc, text, level, now):
    """The new portrait, with the previous ones kept behind it."""
    doc = dict(doc or {})
    past = list(doc.get("past") or [])
    if doc.get("text"):
        past.append({"text": doc["text"], "level": doc.get("level"), "time": doc.get("time")})
    return {"text": text, "level": level, "time": now, "past": past[-KEEP:]}
