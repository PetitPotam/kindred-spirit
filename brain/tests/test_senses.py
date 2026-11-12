"""Her senses: what she sees from where she floats, what she hears, feels, and watched you do."""
from fixtures import snap, zombie

from kindred.describe import describe
from kindred.senses import Novelty


def test_she_only_sees_what_is_in_sight():
    s = snap(animals=[{"type": "minecraft:sheep", "distance": 12, "direction": "ahead", "seen": True},
                      {"type": "minecraft:cow", "distance": 9, "direction": "left", "seen": False}])
    text = describe(s)
    assert "You see: 1 sheep" in text and "cow" not in text, "a cow behind the wall isn't seen"


def test_danger_she_senses_even_out_of_sight():
    z = dict(zombie(8, "behind"), seen=False)
    assert "zombie 8 blocks behind you (out of sight: you sense it)" in describe(snap(hostiles=[z]))


def test_she_hears_feels_and_watched_you():
    s = snap(sounds=[{"what": "Zombie groans", "distance": 14, "direction": "behind", "above": -6, "new": True},
                     {"what": "Water flows", "distance": 2, "direction": "left", "above": 0}],
             feel={"temperature": -0.5, "falling": "snow"},
             youDid=["broke 3 oak log", "got 3 oak log"])
    text = describe(s)
    assert "You hear: Zombie groans (14 blocks behind you, below) new!; Water flows (right here)" in text
    assert "You feel: snow falling on you, freezing cold." in text
    assert "The player just: broke 3 oak log, got 3 oak log." in text


def test_new_things_stand_out_then_become_familiar():
    n = Novelty(familiar=8)
    first = n.annotate(snap(animals=[{"type": "minecraft:axolotl", "distance": 4, "seen": True}]), 0)
    assert first["animals"][0]["new"]
    for t in range(1, 20):
        later = n.annotate(snap(animals=[{"type": "minecraft:axolotl", "distance": 4, "seen": True}]), t)
    assert not later["animals"][0]["new"], "the same axolotl all day stops being news"
    again = n.annotate(snap(animals=[{"type": "minecraft:axolotl", "distance": 4, "seen": True}]), 6 * 3600)
    assert again["animals"][0]["new"], "after a long while away, it feels new again"
    assert "(new to you!)" in describe(first)


def test_a_new_sound_out_of_sight_catches_her_attention():
    import asyncio
    from kindred import config
    from kindred.alerts import Alerts
    from kindred.server import Brain
    b = Brain(config.merge(config.DEFAULTS, {}), "t", alerts=Alerts())
    got = []

    async def notice(event, detail=""):
        got.append((event, detail))
    b.notice = notice

    async def run():
        b.listen(snap(sounds=[{"what": "Zombie groans", "distance": 12, "direction": "behind", "above": -5,
                               "new": True}]))
        b.listen(snap(sounds=[{"what": "Footsteps", "distance": 9, "direction": "left", "new": True}]))
        b.listen(snap(sounds=[{"what": "Cow moos", "distance": 9, "direction": "left", "new": True}],
                      animals=[{"type": "minecraft:cow", "distance": 9, "seen": True}]))
        await asyncio.sleep(0)
    asyncio.run(run())
    assert got == [("heard", "Zombie groans (12 blocks behind you, below)")], \
        "footsteps aren't news, and a cow she can see isn't a mystery"
