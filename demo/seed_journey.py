#!/usr/bin/env python3
"""Prepares "Pip's journey": the memories of a companion who has already played a while with a
(fictional) player called Sam, so the tour can show her later in the story without filming hours
of play. The tour imports it in-game with /kindred memory import journey, exactly as a player
would bring her from one world to another.

Everything here is made up for the demo and lives in its own world ("sp:Pip's journey (demo)");
run it again to start that world over.

    brain/.venv/bin/python demo/seed_journey.py     (the gateway must be running: scripts/start.sh)
"""
import json
import time
import urllib.request

GATEWAY = "http://127.0.0.1:11437/v1/memory/"
WORLD = "sp:Pip's journey (demo)"

PLAYER = [
    ("The player's name is Sam.", 9),
    ("Sam loves building cozy cottages out of spruce and birch.", 7),
    ("Sam is scared of the dark caves but goes in anyway when I'm there.", 6),
    ("Sam's dream is a big farm with sheep of every color.", 7),
]
SELF = [
    ("Sam named me Pip on our very first day, and I love my name.", 8),
    ("I discovered I can light the dark: I glow, and I can set torches.", 7),
    ("I discovered I can find animals and lead the way to them.", 7),
    ("I discovered I can push monsters away from Sam.", 7),
    ("I am small and I can't fight, but I am brave for Sam.", 7),
]
HABITS = [("Sam often asks me to lead the way home after mining.", 5)]
WORLD_FACTS = [("Our cottage is made of spruce, with a pumpkin patch beside it.", 6)]
ORIGIN = [
    ("I woke up for the first time on a starry night, floating above a field of lilies of the valley.", 9),
    ("When we found the old stone ruins, they hummed when I came near, as if they remembered me.", 9),
]
TASTES = [
    {"about": "sunsets", "feeling": "love", "why": "the sky turns my color"},
    {"about": "sheep", "feeling": "like", "why": "they are soft and Sam loves them"},
    {"about": "deep caves", "feeling": "dislike", "why": "too quiet, and they swallow the light"},
]
CORES = [
    {"text": "The night the skeletons chased us and Sam shielded me with their own body. I felt so small, "
             "and so loved.", "feeling": "loved", "pain": False},
    {"text": "The first time Sam hit me by accident, I was so scared I hid for a while. We made up after.",
     "feeling": "hurt", "pain": True, "healed": True},
]
HEART = {"bond": 78.0, "discovered": ["guide", "protect", "place_torch", "find_ore", "find_animal", "find_block",
                                      "locate", "harvest", "name_place", "set_reminder", "standing_request",
                                      "give_item", "set_time", "set_weather"],
         "asked": {}, "seen_items": [], "requests": [], "last_prank": 0, "hurt_until": 0,
         "seen_species": ["sheep", "cow", "chicken", "pig", "horse", "creeper", "zombie", "skeleton"],
         "sorries": [], "hits": [], "rained": False}


def call(op, **body):
    req = urllib.request.Request(GATEWAY + op, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main():
    call("delete", world=WORLD, strict=True,  # (only this demo world)
         kinds=["player", "self", "habit", "world", "origin", "taste", "core", "diary", "episode", "place"])
    n = 0
    for kind, rows in (("player", PLAYER), ("self", SELF), ("habit", HABITS), ("world", WORLD_FACTS),
                       ("origin", ORIGIN)):
        for text, importance in rows:
            call("add", kind=kind, text=text, world=WORLD, importance=importance, dedupe=0)
            n += 1
    for t in TASTES:
        call("add", kind="taste", text="I %s %s (%s)" % (t["feeling"], t["about"], t["why"]), world=WORLD,
             importance=6, meta={"about": t["about"], "feeling": t["feeling"]}, dedupe=0)
        n += 1
    for c in CORES:
        call("add", kind="core", text=c["text"], world=WORLD, importance=10,
             meta={"feeling": c["feeling"], "pain": c["pain"], **({"healed": True} if c.get("healed") else {})},
             dedupe=0)
        n += 1
    call("doc", key="world:%s:heart" % WORLD, value=HEART)
    now = time.time()  # three weeks of playing together, the last time two days ago
    call("doc", key="world:%s:stats" % WORLD, value={"first_met": now - 21 * 86400, "last_seen": now - 2 * 86400,
                                                       "sessions": 14, "minutes": 960})
    print("Seeded %d memories and her heart (bond %d) in %s" % (n, HEART["bond"], WORLD))


if __name__ == "__main__":
    main()
