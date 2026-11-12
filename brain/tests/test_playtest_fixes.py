"""Fixes from the LAN playtest of 2026-11-12 (notes in the shared folder): each test names the item."""
import asyncio

from test_end_to_end import make_cfg, stubs  # noqa: F401

from kindred import intents


def _talk(stubs, text, abilities=("guide", "find_player", "follow_player", "protect", "give_item", "build")):
    from test_heart import _brain
    b = _brain(stubs)
    b.abilities = list(abilities)
    sent = []

    async def send(msg):
        sent.append(msg)
    b.send = send

    async def run():
        b.ws, b.in_world = object(), True
        await b.answer(text)
    asyncio.run(run())
    return b, sent


def test_follow_me_is_never_a_trip(stubs):  # items 1 and 19
    stubs.ai_script = [{"role": "assistant", "content": "[happy] Right behind you!"}]
    b, sent = _talk(stubs, "follow me")
    assert {"type": "act", "move": "follow"} in sent
    req = stubs.ai_requests[-1]
    assert "tool_choice" not in req or req["tool_choice"] in ("auto", None)
    offered = {t["function"]["name"] for t in req.get("tools") or []}
    assert "guide" not in offered and "follow_player" not in offered


def test_follow_me_to_somewhere_still_leads():
    assert intents.LEADING.search("follow me to the village")
    assert not intents.LEADING.search("follow me")


def test_stand_still_stops_her():  # item 16
    for t in ("stand still, don't move", "freeze!", "stop following me", "hold still"):
        assert intents.match(t)[0] == [{"move": "stay"}], t
    for t in ("stay with me", "stay close to me", "follow us"):
        assert intents.match(t)[0] == [{"move": "follow"}], t


def test_a_show_of_gestures_is_not_a_gift(stubs):  # item 8
    assert intents.match("do some fancy emotes")[0] == [{"perform": True}]
    stubs.ai_script = [{"role": "assistant", "content": "[excited] Ta-da!"}]
    b, sent = _talk(stubs, "can you show me some tricks")

    async def wait():
        await asyncio.sleep(0)
    asyncio.run(wait())
    assert not any(m.get("perform") for m in sent), "the show is played by the brain, not sent as an act"


def test_the_same_gift_twice_needs_asking_again(stubs):  # item 8
    from test_heart import _brain
    b = _brain(stubs)
    b.abilities = ["give_item"]
    b.offered = None
    asked = []

    async def request(name, args, timeout=25):
        asked.append(name)
        return {"ok": True}
    b.request = request

    async def run():
        b.last_player_text = "can I have an enchanted golden apple?"
        first = await b._run_tool("give_item", {"item": "enchanted_golden_apple"})
        b.last_player_text = "you do some fancy emotes"
        again = await b._run_tool("give_item", {"item": "enchanted_golden_apple"})
        b.last_player_text = "another one please"
        third = await b._run_tool("give_item", {"item": "enchanted_golden_apple"})
        return first, again, third
    first, again, third = asyncio.run(run())
    assert first["ok"] and again["ok"] is False and third["ok"]
    assert asked == ["give_item", "give_item"]


def test_standing_protection_for_everyone_and_for_a_friend():  # item 11
    for t in ("protect us from creepers, zombies, spiders and everything", "follow and defend Walid",
              "from now on keep protecting us", "always protect me"):
        assert intents.action_hint(t, ["standing_request"]) == "standing_request", t
    from kindred.heart import Heart
    h = Heart({"heart": {}})
    h.add_request("protect", "waterwalid")
    assert h.wants("protect") is None, "a friend's protection isn't the player's"
    assert h.guarded_friends(["waterwalid", "sam"]) == ["waterwalid"]
    h.add_request("protect", "everyone")
    assert h.wants("protect") and h.guarded_friends(["waterwalid", "sam"]) == ["waterwalid", "sam"]


def test_placing_things_and_new_shapes_are_build_requests():  # items 2, 3, 5, 6
    for t in ("place the campfire here", "put a bed there", "flatten the ground above y 64", "clear everything above",
              "build a house for the two of us", "create another portal"):
        assert intents.action_hint(t, ["build", "place_torch"]) == "build", t


def test_a_joke_never_costs_the_bond():  # (jokes lowered the bond)
    from kindred.heart import Heart
    h = Heart({"heart": {}})
    before = h.rel.s["a"], h.rel.s["g"]
    h.on_regard("teasing", "you're a weird little blob")
    assert h.rel.s["a"] >= before[0] and h.rel.s["g"] <= before[1]


def test_defending_her_is_recognised():  # (witnessing)
    for t in ("stop hitting pip", "leave her alone", "hey, be nice to her", "don't talk to her like that"):
        assert intents.DEFEND.search(t), t
    assert not intents.DEFEND.search("stop the rain")
