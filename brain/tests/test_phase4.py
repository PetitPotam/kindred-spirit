"""Phase 4 pieces on their own: activity understanding, shared goals, expert modes and speedrun splits."""
import asyncio

from kindred import activity as A
from kindred import expertise as E
from kindred import goals as G
from tests.fixtures import snap


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


# ---------------------------------------------------------------------- activity

def test_phrases_the_mod_sends_are_read():
    assert A.parse_phrase("broke 3 oak log") == ("broke", "oak log", 3)
    assert A.parse_phrase("placed a torch") == ("placed", "torch", 1)
    assert A.parse_phrase("hit an enderman") == ("hit", "enderman", 1)
    assert A.parse_phrase("waved hello") is None


def test_building_from_placed_blocks_with_a_site():
    c = Clock()
    a = A.Activity(clock=c)
    for i in range(30):
        c.t += 6
        a.add("placed", "minecraft:oak_planks", pos=(i % 7, 64 + i // 14, (i * 3) % 5))
    for i in range(6):
        a.add("placed", "glass", pos=(i, 66, 0))
    assert a.current() == "building"
    s = a.summary()
    assert s.startswith("building with oak planks and glass for 3 minutes"), s
    assert "(a 7x5 spot, 3 high)" in s, s


def test_redstone_mining_farming_wood_and_fighting():
    for actions, expected in [
        ([("placed", "repeater", 3), ("placed", "redstone wire", 6), ("placed", "stone", 2)], "redstone"),
        ([("broke", "deepslate", 20), ("broke", "iron ore", 2)], "mining"),
        ([("broke", "wheat", 10), ("placed", "wheat", 10)], "farming"),
        ([("broke", "oak log", 8), ("broke", "oak leaves", 10)], "wood"),
        ([("hit", "zombie", 4), ("hit", "skeleton", 2)], "fighting"),
    ]:
        a = A.Activity(clock=Clock())
        for verb, what, n in actions:
            a.add(verb, what, n)
        assert a.current() == expected, (actions, a.scores())


def test_too_little_is_nothing_and_eating_is_never_the_activity():
    a = A.Activity(clock=Clock())
    a.add("placed", "torch")
    a.add("ate", "bread", 3)
    assert a.current() is None
    assert a.summary() == ""


def test_snapshots_repeat_their_window_but_count_once():
    c = Clock()
    a = A.Activity(clock=c)
    a.from_snapshot(snap(youDid=["broke 3 stone"]))
    a.from_snapshot(snap(youDid=["broke 3 stone"]))   # the same 30 s window, sent again
    a.from_snapshot(snap(youDid=["broke 5 stone", "placed a torch"]))  # two more since
    assert sum(e[3] for e in a.events if e[1] == "broke") == 5
    assert sum(e[3] for e in a.events if e[1] == "placed") == 1


def test_old_activity_fades():
    c = Clock()
    a = A.Activity(clock=c)
    a.add("broke", "deepslate", 30)
    assert a.current() == "mining"
    c.t += A.WINDOW + 1
    assert a.current() is None


# ---------------------------------------------------------------------- goals

class FakeStore:
    def __init__(self):
        self.docs = {}

    async def call(self, op, **body):
        assert op == "doc"
        if "value" in body:
            self.docs[body["key"]] = body["value"]
            return {"ok": True}
        return {"value": self.docs.get(body["key"])}


class FakeMemory:
    def __init__(self, store, world_id="w1"):
        self.store = store
        self.world_id = world_id


def test_goals_survive_a_restart_and_notice_when_done():
    async def run():
        store, c = FakeStore(), Clock()
        g = G.Goals(FakeMemory(store), clock=c)
        await g.load()
        await g.add("full diamond armor", check={"have": {"item": "diamond", "count": 24}})
        await g.add("build a castle", steps=["walls", "towers", "a gate"])
        c.t += 10
        again = G.Goals(FakeMemory(store), clock=c)  # the brain restarted
        await again.load()
        assert [x["text"] for x in again.active()] == ["full diamond armor", "build a castle"]
        s = snap(inventory={"minecraft:diamond": 9})
        assert "9 of 24 diamond so far" in again.context(s)
        assert await again.check(s) == []
        await again.progress("castle", "towers")
        castle = again.find("the castle")
        assert [st["done"] for st in castle["steps"]] == [False, True, False]
        assert "1 of 3 steps done; next: walls" in again.describe(castle)
        done = await again.check(snap(inventory={"minecraft:diamond": 24}))
        assert [x["text"] for x in done] == ["full diamond armor"]
        await again.progress("castle")
        await again.progress("castle")
        assert again.active() == []
        assert store.docs["world:w1:goals"]["goals"][1]["status"] == "done"
    asyncio.run(run())


def test_the_same_goal_twice_is_one_and_dropping_works():
    async def run():
        g = G.Goals(FakeMemory(FakeStore()), clock=Clock())
        a = await g.add("Find a village")
        b = await g.add("find a  village")
        assert a is b and len(g.active()) == 1
        await g.drop("village")
        assert g.active() == []
    asyncio.run(run())


def test_nudges_are_rare_and_polite():
    async def run():
        c = Clock(10_000)
        g = G.Goals(FakeMemory(FakeStore()), clock=c)
        await g.add("find a village")
        await g.add("tame a wolf")
        assert g.nudge(idle_seconds=10) is None, "busy player"
        assert g.nudge(idle_seconds=120, quiet=True) is None
        assert g.nudge(idle_seconds=120, danger=True) is None
        first = g.nudge(idle_seconds=120)
        assert first is not None
        assert g.nudge(idle_seconds=120) is None, "not again so soon"
        c.t += G.NUDGE_MINUTES * 60 + 1
        second = g.nudge(idle_seconds=120)
        assert second is not None and second["id"] != first["id"], "not the same one twice in a row"
        c.t += G.NUDGE_MINUTES * 60 + 1
        assert g.nudge(idle_seconds=120, bond=10) is None, "a low bond waits twice as long"
    asyncio.run(run())


def test_checks():
    assert G.check_done({"dimension": "the_nether"}, snap(where={"dimension": "minecraft:the_nether"}))
    assert not G.check_done({"have": {"item": "minecraft:diamond", "count": 3}}, snap())
    assert G.check_done({"advancement": "minecraft:story/mine_diamond"}, snap(advancements=["minecraft:story/mine_diamond"]))
    assert not G.check_done(None, snap())


# ---------------------------------------------------------------------- expert modes

def test_asking_for_a_mode():
    assert E.asked_mode("Pip, speedrun mode") == "speedrun"
    assert E.asked_mode("let's speedrun!") == "speedrun"
    assert E.asked_mode("help me with redstone") == "redstone"
    assert E.asked_mode("switch to builder mode please") == "builder"
    assert E.asked_mode("back to normal mode") == "survival"
    assert E.asked_mode("creative mode is boring") is None
    assert E.asked_mode("what's for dinner") is None


def test_auto_follows_the_activity_but_never_speedruns_by_itself():
    assert E.effective("auto", "redstone") == "redstone"
    assert E.effective(None, "building") == "builder"
    assert E.effective("auto", "mining") == "survival"
    assert E.effective("speedrun", "building") == "speedrun"
    assert "redstone partner" in E.guidance("auto", "redstone")
    assert not E.allows("speedrun", "small_talk")
    assert E.allows("survival", "small_talk")


def test_speedrun_splits():
    c = Clock(0)
    s = E.Splits(clock=c)
    assert s.update(snap()) == [], "not started"
    s.begin()
    c.t = 245
    hits = s.update(snap(where={"dimension": "minecraft:the_nether"}))
    assert [(k, E.Splits.clock_text(t)) for k, _, t in hits] == [("nether", "4:05")]
    assert s.update(snap(where={"dimension": "minecraft:the_nether"})) == [], "once each"
    c.t = 600
    hits = s.update(snap(inventory={"minecraft:blaze_rod": 7, "minecraft:ender_pearl": 12}))
    assert [k for k, _, _ in hits] == ["blaze_rods", "pearls"]
    assert s.next_objective() == "eyes of ender ready"
