"""How she talks, side by side: the same little scenes sent to the real AI, so a change to her
personality can be heard instead of guessed.

    .venv/bin/python -m kindred.bench [label]     -> logs/bench-<label>.json and a printout

Each scene sets your bond, what she sees and a few things you say (or "(...)" for something she
says on her own). The counts at the end are tics to watch, not rules: a line can use your name.
"""
import asyncio
import copy
import json
import os
import re
import sys
import time

from . import config
from .heart import Heart
from .mind import Mind

PLAINS = {
    "type": "snapshot", "health": 20.0, "maxHealth": 20.0, "food": 18, "saturation": 5.0, "armor": 0,
    "air": 300, "maxAir": 300, "onFire": False, "gamemode": "survival", "effects": [],
    "where": {"x": 120, "y": 70, "z": -30, "dimension": "minecraft:overworld", "biome": "minecraft:flower_forest",
              "facing": "north", "yaw": 180.0, "skyVisible": True, "light": 15},
    "time": {"day": 6, "timeOfDay": 11800, "raining": False, "thundering": False},
    "holding": "minecraft:stone_axe", "offhand": "", "inventory": {"minecraft:oak_log": 20, "minecraft:dandelion": 3},
    "wearing": [], "lookingAt": {"block": "minecraft:oak_planks", "distance": 4.0}, "hostiles": [],
    "animals": [{"type": "minecraft:pig", "distance": 6, "direction": "ahead-left"},
                {"type": "minecraft:bee", "distance": 3, "direction": "above"}],
}

# (bond, [messages]); "(...)" = she speaks on her own
SCENES = [
    ("wary", ["hi! who are you?"]),
    ("wary", ["do you like me?"]),
    ("friend", ["what do you think of my house?", "it's just a dirt hut for now"]),
    ("friend", ["look, a pig"]),
    ("friend", ["you're useless"]),
    ("friend", ["what should we do now?"]),
    ("friend", ["can you sing something?"]),
    ("close", ["i love you"]),
    ("close", ["i'm bored"]),
    ("close", ["i just died and lost everything", "all my diamonds..."]),
    ("close", ["where do you come from?"]),
    ("close", ["(Say something on your own while you two wander around; nothing urgent.)"]),
    ("best friend", ["what's your favorite thing in this world?"]),
    ("best friend", ["tell me a secret"]),
    ("best friend", ["i'm going to bed, good night"]),
]
BONDS = {"hurt": 10, "wary": 25, "friend": 50, "close": 75, "best friend": 92}


def tics(lines, name):
    n = max(1, len(lines))
    return {
        "lines": len(lines),
        "uses your name": round(sum(name.lower() in l.lower() for l in lines) / n, 2),
        "ends on a question": round(sum(l.rstrip().endswith("?") for l in lines) / n, 2),
        "starts with Oh": round(sum(bool(re.match(r"\s*oh\b", l, re.I)) for l in lines) / n, 2),
        "no contractions (I am, it is...)": round(sum(bool(re.search(r"\b(I am|I do not|it is|I will|do not)\b", l))
                                                      for l in lines) / n, 2),
        "love / warm / bright / so happy": round(sum(bool(re.search(r"love|warm|bright|so happy", l, re.I))
                                                     for l in lines) / n, 2),
        "average length": round(sum(len(l) for l in lines) / n),
    }


async def run(label):
    cfg = config.load()
    if os.environ.get("BENCH_MODEL"):  # try another model through the same gateway
        cfg["ai"]["model"] = os.environ["BENCH_MODEL"]
    if os.environ.get("BENCH_EFFORT"):
        cfg["ai"]["reasoning_effort"] = os.environ["BENCH_EFFORT"]
    name = "Sam"
    out = []
    for level, messages in SCENES:
        heart = Heart(cfg)
        heart.state["bond"] = float(BONDS[level])
        mind = Mind(cfg)
        mind.heart = heart.guidance("happy") + " The player's name is %s." % name
        mind.powers = "You can help with your hands when asked, but nothing too big."
        said = []
        for m in messages:
            snap = copy.deepcopy(PLAINS)
            if m.startswith("("):
                text, mood, gesture = await mind.initiative(snap, m.strip("()"))
            else:
                text, mood, gesture = await mind.reply(snap, m)
            said.append({"you": m, "pip": text, "mood": mood, "gesture": gesture})
            print("[%s] %s\n    Pip: %s" % (level, m, text))
        out.append({"bond": level, "turns": said})
    lines = [t["pip"] for s in out for t in s["turns"]]
    stats = tics(lines, name)
    print("\n" + json.dumps(stats, indent=1))
    path = os.path.join(os.path.expanduser("~/.kindred-spirit/logs"), "bench-%s.json" % label)
    with open(path, "w") as fh:
        json.dump({"label": label, "time": time.time(), "stats": stats, "scenes": out}, fh, indent=1)
    print("saved", path)


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else "now"))
