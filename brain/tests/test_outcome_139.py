"""#139: she speaks from how a build or job really ended, never just from having started it."""
import asyncio

from test_end_to_end import make_cfg, stubs  # noqa: F401
from test_playtest_1113 import _brain

from kindred import outcome


def test_the_line_says_what_really_happened():
    done = outcome.line({"kind": "blueprint", "what": "village plains small house 1", "done": 120, "skipped": 0, "total": 120})
    assert done == ("All done: the village plains small house is finished!", "happy")
    half = outcome.line({"kind": "build", "what": "building a wall", "done": 60, "skipped": 12, "total": 72})
    assert "60 of 72" in half[0] and "12 wouldn't fit" in half[0] and half[0].startswith("The wall")
    short = outcome.line({"kind": "build", "what": "building a floor", "done": 40, "skipped": 0, "total": 400,
                          "stopped": "ran out of stone bricks"})
    assert "ran out of stone bricks" in short[0] and "40 of 400" in short[0] and "undo that" in short[0]
    job = outcome.line({"kind": "job", "what": "chop oak", "done": 9, "total": 30, "stopped": "your pockets are full"})
    assert job[0] == "I had to stop: your pockets are full. I did 9 of 30."


def test_quiet_when_you_stopped_it_or_it_was_tiny():
    assert outcome.line({"kind": "build", "what": "building a wall", "done": 10, "total": 72, "stopped": "asked"}) is None
    assert outcome.line({"kind": "build", "what": "building a pillar", "done": 3, "total": 3}) is None
    assert outcome.line({"kind": "build", "what": "building a pillar", "done": 2, "skipped": 1, "total": 3}), \
        "a small thing that half-failed still gets a word"
    assert outcome.line(None) is None


def test_she_says_it_when_the_game_reports_it_once(stubs):
    b = _brain(stubs, ["build"])
    said = []

    async def say(text, mood="calm", **kw):
        said.append(text)
    b.say = say

    async def run():
        b.ws, b.in_world = object(), True
        old = {"seq": 4, "kind": "build", "what": "building a wall", "done": 72, "skipped": 0, "total": 72}
        await b.on_snapshot({"ended": old})  # (from before she connected: old news)
        await b.on_snapshot({"ended": old})
        await asyncio.sleep(0)
        assert not said
        new = {"seq": 5, "kind": "build", "what": "building a floor", "done": 380, "skipped": 21, "total": 401}
        await b.on_snapshot({"ended": new})
        await b.on_snapshot({"ended": new})
        await asyncio.sleep(0)
    asyncio.run(run())
    assert len(said) == 1 and "21 wouldn't fit" in said[0]


def test_the_first_build_of_a_session_is_reported(stubs):
    b = _brain(stubs, ["build"])
    said = []

    async def say(text, mood="calm", **kw):
        said.append(text)
    b.say = say

    async def run():
        b.ws, b.in_world = object(), True
        await b.on_snapshot({})  # nothing has ended yet
        await b.on_snapshot({"ended": {"seq": 1, "kind": "blueprint", "what": "igloo", "done": 90, "total": 90}})
        await asyncio.sleep(0)
    asyncio.run(run())
    assert said == ["All done: the igloo is finished!"]


def test_a_started_build_is_marked_as_not_finished(stubs):
    b = _brain(stubs, ["build"])

    async def inner(name, args):
        return {"ok": True, "building": "wall", "blocks": 72}
    b._run_tool_inner = inner
    r = asyncio.run(b._run_tool("build", {"shape": "wall"}))
    assert "never that it's done" in r["note"]
