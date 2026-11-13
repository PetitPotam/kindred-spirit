"""Her jobs, blueprints, crafting help and trading help, wired: the tools, System 0's hints, the dispatch."""
import asyncio

from test_end_to_end import stubs  # noqa: F401

from kindred import intents, tools
from kindred.server import did_something

ALL = list(tools.ABILITY_TOOLS) + ["standing_request"]


def test_clear_requests_ask_for_the_right_power():
    cases = {
        "Pip, build us a cozy cottage for three": "blueprint",
        "can you make me a little house": "blueprint",
        "what am I missing for a piston?": "craft_help",
        "can I make a bed?": "craft_help",
        "what do I need for a crafting table": "craft_help",
        "do I have enough to make a bed": "craft_help",
        "mine the iron here": "job",
        "get me some coal": "job",
        "chop that tree and bring me logs": "job",
        "get my things back": "job",
        "can you get my stuff back from where i died": "job",
        "can you pick up the items": "job",
        "craft me a furnace": "job",
        "what does the villager sell": "trades",
        "any good trades?": "trades",
        # unchanged: questions stay questions, single blocks stay harvest
        "where can i mine coal": "find_ore",
        "find iron ore": "find_ore",
        "mine this block": "harvest",
        "chop this tree": "harvest",
        "push them away": "protect",
        "build a pillar here": "build",
    }
    for text, tool in cases.items():
        assert intents.action_hint(text, ALL) == tool, (text, intents.action_hint(text, ALL))


def test_how_to_questions_stay_questions_for_the_knowledge_base():
    # an action hint would skip what the world remembers: "how do I make..." must not be one
    for t in ("how do I make a piston?", "how do I craft a furnace", "how to craft a bed"):
        assert intents.action_hint(t, ALL) is None, t


def test_talking_about_plans_isnt_asking():
    assert intents.action_hint("I'm going to build a house", ALL) is None
    assert intents.action_hint("we're going to make a house later", ALL) is None
    assert intents.action_hint("nice house", ALL) is None


def test_without_the_new_powers_the_old_ones_still_answer():
    # (an older mod, or advisor: no blueprint offered) a house is still the box house
    assert intents.action_hint("build a house for the two of us", ["build", "place_torch"]) == "build"


def test_the_tools_are_offered_with_their_abilities():
    names = [t["function"]["name"] for t in tools.for_abilities(["job", "blueprint", "craft_help", "trades"])]
    for n in ("job", "blueprint", "craft_help", "trades"):
        assert n in names
    job = tools.ABILITY_TOOLS["job"]["function"]["parameters"]
    assert set(job["properties"]["kind"]["enum"]) >= {"mine", "chop", "collect", "craft", "return_items", "stop", "status"}
    assert intents.FAMILY["blueprint"] == intents.FAMILY["build"], "a house request keeps the building powers"


def test_what_counts_as_having_done_something():
    assert did_something("blueprint", {"ok": True, "blocks": 250})
    assert not did_something("blueprint", {"ok": False, "error": "Not enough"})
    assert did_something("job", {"ok": True, "job": "mine", "total": 4})
    assert not did_something("job", {"ok": False, "error": "There's no iron within 12 blocks."})


def test_getting_your_things_back_goes_to_where_you_died(stubs):
    from test_heart import _brain
    b = _brain(stubs)
    b.abilities, b.offered = ["job"], None
    sent = []

    async def request(name, args, timeout=25):
        sent.append((name, dict(args)))
        return {"ok": True, "job": "return_items", "total": 5}
    b.request = request

    async def spots(limit=200):
        return [{"text": "where we saw our first cow", "meta": {"what": "first:cow", "x": 1, "y": 70, "z": 2, "last": 5}},
                {"text": "where you died", "meta": {"what": "death", "x": 120, "y": 12, "z": -40, "last": 9}}]
    b.memory.spots = spots

    async def run():
        b.last_player_text = "get my things back please"
        await b._run_tool("job", {"kind": "return_items"})
        await b._run_tool("job", {"kind": "return_items", "x": 5, "z": 6})  # (coordinates given: kept)
        await b._run_tool("job", {"kind": "mine", "what": "iron"})
    asyncio.run(run())
    assert sent[0] == ("job", {"kind": "return_items", "x": 120, "y": 12, "z": -40})
    assert sent[1][1]["x"] == 5 and "y" not in sent[1][1]
    assert sent[2] == ("job", {"kind": "mine", "what": "iron"})
