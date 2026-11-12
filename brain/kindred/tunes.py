"""Her hums and little songs, as music instead of voice.

"La-dee-dum, dum-dee-doo" read by the voice engine came out flat and robotic, and sung syllable by
syllable it was creepy. So a hum isn't spoken at all: the words stay in her subtitle, and the game
plays the tune with its own note-block sounds where she floats (a bell, a chime, a flute...). Each
syllable is a note of a small pentatonic tune chosen from the words, so the same words always make
the same tune: a song stuck in her head stays the same song.
"""
import random
import re

SYLLABLE = r"(?:la|lee|li|dee|di|dum|doo|da|dah|lu|loo|ba|bum|bah|na|nah|tra|tum|ti|do|ta|ra|hmm|mm|bzz|buzz)"
HUM = re.compile(r"(?i)(?<![\w])(%s(?:[-\s,~]+%s){2,})(?![\w])[.!?…~]*" % (SYLLABLE, SYLLABLE))
SCALE = [-5, -3, 0, 2, 4, 7, 9, 12]  # semitones from her home note (note-block pitch stays within 0.5-2)
INSTRUMENT = {"happy": "bell", "excited": "chime", "calm": "flute", "sleepy": "flute", "sad": "harp",
              "curious": "xylophone"}


def split(text):
    """(what she says aloud, [hums]): the hums taken out of her spoken words."""
    hums = [m.group(1) for m in HUM.finditer(text or "")]
    spoken = HUM.sub(" ", text or "")
    spoken = re.sub(r"\s+([,.!?…])", r"\1", re.sub(r"\s{2,}", " ", spoken)).strip(" ,-~")
    if not re.search(r"[A-Za-z]", spoken):
        spoken = ""
    return spoken, hums


def melody(hum):
    """Notes for a hum: [(semitones, beats)], a walk up and down the scale that comes home at the end;
    a comma or a long syllable ("doo", "loo") is held longer."""
    syllables = re.findall(r"(%s)([-\s,~]*)" % SYLLABLE, hum, re.I)
    rng = random.Random(sum((i + 1) * ord(c) for i, c in enumerate(hum.lower())))
    step, notes = rng.choice([2, 3]), []
    for i, (syl, after) in enumerate(syllables):
        step = max(0, min(len(SCALE) - 1, step + rng.choice([-2, -1, 1, 1, 2])))
        semi = SCALE[2] if i == len(syllables) - 1 else SCALE[step]
        beats = 2 if ("," in after or syl.lower() in ("doo", "loo", "dum", "hmm", "bum")) else 1
        notes.append((semi, beats))
    return notes


def tune_message(hums, mood="happy"):
    """What the mod plays: notes in order with their length, and the instrument for her mood."""
    notes = []
    for k, h in enumerate(hums):
        if k:
            notes.append((None, 2))  # a little breath between two hums
        notes += melody(h)
    return {"type": "tune", "instrument": INSTRUMENT.get(mood or "", "bell"), "beat_ms": 260,
            "notes": [{"semi": s, "beats": b} for s, b in notes]}
