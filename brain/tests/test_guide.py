"""Finding animals and leading the way: what the player says, what she knows, where she leads."""
import asyncio

from fixtures import snap

from test_end_to_end import stubs  # noqa: F401  (a fixture)

from kindred import intents
from kindred.describe import describe

ALL = ["find_ore", "find_animal", "locate", "guide", "stop_guide"]


def test_lead_the_way_and_follow_you_mean_guide():
    for said in ("lead the way", "lead the way i will follow you", "ok I'll follow you", "show me the way",
                 "take me there", "which way?"):
        assert intents.action_hint(said, ALL) == "guide", said


def test_looking_for_animals():
    for said in ("i need to find sheeps", "where is the sheeps ??", "any cows around?", "find me a horse",
                 "where's the nearest villager"):
        assert intents.action_hint(said, ALL) == "find_animal", said
    assert intents.action_hint("where's the nearest village", ALL) == "locate"


def test_find_them_means_what_was_named_before():
    earlier = ["i need to find sheeps", "can you ? that would be amazing"]
    assert intents.hint_in_context("can you find them please?", earlier, ALL) == "find_animal"
    assert intents.hint_in_context("did you find them?", ["any diamonds here?"], ALL) == "find_ore"
    assert intents.hint_in_context("you are funny", earlier, ALL) is None


def test_she_knows_where_animals_are_with_directions():
    s = snap(animals=[{"id": 5, "type": "minecraft:sheep", "distance": 21.4, "direction": "ahead-left", "baby": False},
                      {"id": 6, "type": "minecraft:sheep", "distance": 24, "direction": "left", "baby": True},
                      {"id": 7, "type": "minecraft:cat", "distance": 3, "direction": "behind", "tamed": True,
                       "name": "Mochi"}])
    text = describe(s)
    assert "2 sheep (1 babies), nearest 21 blocks ahead on your left" in text
    assert "1 cat, nearest 3 blocks behind you (your pet: Mochi)" in text
    assert "No animals within 32 blocks." in describe(snap(animals=[]))


def test_lead_me_to_the_sheep_she_can_see(stubs):
    from test_heart import _brain
    brain = _brain(stubs)
    brain.snapshot = snap(animals=[{"id": 9, "type": "minecraft:sheep", "distance": 30, "direction": "right"},
                                   {"id": 8, "type": "minecraft:sheep", "distance": 12, "direction": "left"}])
    brain.last_player_text = "lead me to the sheeps"
    assert asyncio.run(brain.guide_target({})) == {"entity": 8}, "the nearest one, followed as it walks"
    brain.last_player_text = "lead the way"
    assert asyncio.run(brain.guide_target({})) == {}, "otherwise: what she found last"


def test_she_cant_use_a_power_she_hasnt_discovered_even_if_the_ai_tries(stubs):
    from test_heart import _brain
    brain = _brain(stubs)
    brain.abilities = ["find_animal", "guide"]
    brain.offered = []  # amnesia: nothing discovered, nothing offered this turn
    res = asyncio.run(brain.run_tool("find_animal", {"animal": "sheep"}))
    assert not res["ok"] and "don't know how" in res["error"]
    brain.last_player_text = "i need to find sheeps"
    res = asyncio.run(brain.run_tool("standing_request", {"what": "notify_ore"}))
    assert not res["ok"], "'find sheep' is not 'always tell me about ores'"
    brain.last_player_text = "tell me whenever we're near diamonds"
    assert asyncio.run(brain.run_tool("standing_request", {"what": "notify_ore", "detail": "diamond"}))["ok"]


def test_asking_for_light_means_a_torch():
    for said in ("can you give me light or something to help me see", "i can't see anything", "light it up please",
                 "it's too dark", "place a torch"):
        assert intents.action_hint(said, ["place_torch"]) == "place_torch", said


def test_yes_to_what_she_offered_in_her_own_words():
    allowed = ["place_torch", "protect", "guide", "find_animal"]
    assert intents.offered_in("Should I try to light it up for you so you can see better?", allowed) == "place_torch"
    assert intents.offered_in("Should I push them back so we can find a place to hide?", allowed) == "protect"
    assert intents.offered_in("The sun is setting, how lovely.", allowed) is None


def test_she_knows_you_just_died_and_came_back(stubs):
    from test_heart import _brain
    b = _brain(stubs)
    b.send = lambda msg: asyncio.sleep(0)

    async def run():
        b.ws, b.in_world = object(), True
        b.notice = lambda *a, **k: asyncio.sleep(0)
        far = dict(snap(health=4.0)["where"], x=500, z=500)
        await b.on_snapshot(snap(health=4.0))                 # badly hurt, a skeleton shooting
        await b.on_snapshot(snap(health=20.0, where=far))      # full health, far away: respawned
    asyncio.run(run())
    text = describe(b.snapshot)
    assert "Just happened: The player died" in text and "came back to life" in text


def test_lead_the_way_to_the_animal_we_just_talked_about(stubs):
    from test_heart import _brain
    b = _brain(stubs)
    b.snapshot = snap(animals=[{"id": 4, "type": "minecraft:cow", "distance": 24, "direction": "ahead-right"}])
    b.recent_player = ["where are the cows?", "lead the way"]
    b.last_player_text = "lead the way"
    assert asyncio.run(b.guide_target({})) == {"entity": 4}
    b.recent_player, b.last_player_text = ["lead the way"], "lead the way"
    b.mind.history = [{"role": "assistant", "content": "[happy] There's a cow 24 blocks ahead on your right!"}]
    assert asyncio.run(b.guide_target({})) == {"entity": 4}, "or the animal she just told you about"


def test_being_attacked_means_protect_me():
    for said in ("i am being attacked", "im getting shot", "save me", "the skeleton is shooting me",
                 "theyre attacking us", "protect me"):
        assert intents.action_hint(said, ["protect"]) == "protect", said
    assert intents.action_hint("i shot the zombie", ["protect"]) is None
