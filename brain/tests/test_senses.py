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
        b.listen(snap(sounds=[{"what": "Zombie groans", "distance": 12, "direction": "behind", "new": True}]))
        b.listen(snap(sounds=[{"what": "Wolf howls", "distance": 12, "direction": "behind", "above": -5,
                               "new": True}]))
        b.listen(snap(sounds=[{"what": "Footsteps", "distance": 9, "direction": "left", "new": True}]))
        b.listen(snap(sounds=[{"what": "Cow moos", "distance": 9, "direction": "left", "new": True}],
                      animals=[{"type": "minecraft:cow", "distance": 9, "seen": True}]))
        await asyncio.sleep(0)
    asyncio.run(run())
    assert got == [("heard", "Wolf howls (12 blocks behind you, below)")], \
        "monsters are for her warnings, footsteps aren't news, and a cow she can see isn't a mystery"


def test_a_session_leaves_a_record_to_read_afterwards(tmp_path):
    from kindred.sessionlog import SessionLog
    t = [0.0]
    s = SessionLog(str(tmp_path), clock=lambda: t[0])
    s.start("sp:New World")
    s.event("you", text="lead the way", spoken=True)
    t[0] += 2
    s.event("pip", text="This way!", source="reply")
    for i in range(5):
        t[0] += 3
        s.event("pip", text="Ooh, look at that %d!" % i, source="own")
    s.event("cut", by_player=False, rest="and then the stones...")
    s.event("tool", name="guide", ok=False, result="Guide where?")
    md = s.finish()
    text = open(md).read()
    assert "she spoke | 6 lines" in text and "on her own | 5" in text
    assert "She talked on her own more than she answered you." in text and "Failed tools: guide" in text
    assert "**you** (voice): lead the way" in text
    rows = [__import__("json").loads(x) for x in open(md[:-3] + ".jsonl").read().splitlines()]
    assert len(rows) == 11 and rows[2]["t"] == 2.0, "start, you, 6 lines, a cut, a tool, the end; real times"
