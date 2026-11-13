"""Talker first: a plain command is System 0's alone (docs/research/designs-2026-11.md, part 3).

"Follow me", "stand still, don't move", "come here", "stay with me": her body already did it the moment
the words came (intents.match), and there's nothing else to answer. Waiting ~2 s for the AI to say
"Right behind you!" was the slowest part of the simplest requests, and the AI sometimes added things
nobody asked for (a guide to somewhere 488 blocks away, 64 fireworks). So for a sentence that is only
such a command, she answers with an instinct line (System 2 rewrites them in her own voice, like her
other instinct lines) and the AI is not called; it hears the exchange in the conversation afterwards.

Anything more in the sentence ("follow me and tell me what you see", "follow Robin", a question) still
goes to the AI.
"""
import re

LINES = {
    "follow_ok": ["Right behind you!", "Coming!", "With you!", "Lead on!", "Okay, sticking close."],
    "stay_ok": ["Staying put!", "I'll wait right here.", "Not moving a bit.", "Frozen!", "Okay, I'll stay."],
    "come_ok": ["Coming!", "Here I am!", "On my way!", "Zooming over!"],
    # thanks and praise, nothing else: answered at once, no AI (#20)
    "thanks_ok": ["Hehe!", "Anytime!", "Yay!", "Happy to!", "You're welcome!", "Hee, thank you!"],
    # a clear request she's about to work on: said at once, before the AI and the tool (#19); never "done"
    "on_it": ["On it!", "Okay!", "Let's see...", "Leave it to me!", "Ooh, okay!", "Mm-hm!"],
}
MOMENTS = {
    "follow_ok": "the player asked you to follow them, and you do; a tiny answer, 1 to 4 words (\"Right behind you!\")",
    "stay_ok": "the player asked you to stay where you are, and you do; 1 to 5 words (\"Staying put!\")",
    "come_ok": "the player called you over, and you come; 1 to 4 words (\"Coming!\")",
    "thanks_ok": "the player thanked or praised you; a tiny happy answer, 1 to 4 words (\"Hehe!\")",
    "on_it": "the player asked you to do something and you're just starting: 1 to 3 words, never saying it's done or "
             "how it went (\"On it!\")",
}

# words that don't change what's asked
FILLER = re.compile(r"\b(hey|hi|oh|pip|pep|please|pls|plz|now|ok(ay)?|alright|again|just|right now|for (a|one) "
                    r"(sec(ond)?|while|bit|moment)|thanks?( you)?|thank you|(can|could|would|will) you|you can|"
                    r"i want you to|i need you to|go ahead and|and|then|so|yes|yeah|well|little|a bit|back)\b")
PLAIN = {
    "follow": re.compile(r"^(follow( me| us)?|come (with|along with) (me|us)|(stay|keep|stick) (with|close to|by|beside|near) "
                         r"(me|us)|with me|follow along|don'?t lead( me| us)?|stop (leading|guiding)( me| us)?|no leading)$"),
    "stay": re.compile(r"^(stay( here| there| put| where you are| right there)?|stand still|don'?t move|do not move|"
                       r"wait( here| there)?( for me| for us)?|stop moving|stop following( me| us)?|freeze|hold on|be still|"
                       r"stay still)$"),
    "come": re.compile(r"^(come( here| closer| to me)?|over here|get over here)$"),
}


def plain_command(text, moving):
    """'follow', 'stay' or 'come' when the sentence is only that command (and it's what the body did), else None."""
    if not moving:
        return None
    kinds = set()
    for clause in re.split(r"[.!?,;:]+|\bthen\b", (text or "").lower()):
        c = re.sub(r"[^a-z' ]", " ", FILLER.sub(" ", clause.replace("’", "'")))
        c = " ".join(c.split())
        if not c:
            continue
        kind = next((k for k, rx in PLAIN.items() if rx.match(c)), None)
        if kind is None:
            return None  # (something more was said: the AI answers)
        kinds.add(kind)
    if len(kinds) != 1:
        return None
    kind = kinds.pop()
    if kind == moving or (kind == "come" and moving == "follow") or (kind == "follow" and moving == "come"):
        return kind
    return None
