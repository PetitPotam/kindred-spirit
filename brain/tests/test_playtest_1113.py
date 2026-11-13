"""Fixes from the singleplayer playtest of 2026-11-13 (session log 20261113-1418); each test names its issue."""
import asyncio

from test_end_to_end import make_cfg, stubs  # noqa: F401

from kindred import intents, mind


def _brain(stubs, abilities):
    from test_heart import _brain as make
    b = make(stubs)
    b.abilities = list(abilities)
    b.offered = None
    return b


def _record(b, results=None):
    asked = []

    async def request(name, args, timeout=25):
        asked.append((name, dict(args)))
        return dict((results or {}).get(name, {"ok": True}))
    b.request = request
    return asked


SHIPS = {"ok": True, "matches": [
    {"name": "shipwreck_with_mast", "size": "9 x 28, 21 high", "big": True},
    {"name": "shipwreck_rightsideup_full", "size": "9 x 28, 9 high", "big": True},
    {"name": "shipwreck_sideways_full", "size": "9 x 28, 9 high", "big": True}],
    "say": "Several fit: ask which one. A big one: confirm before building it."}


def test_a_blueprint_is_confirmed_once_then_built(stubs):  # #60
    b = _brain(stubs, ["blueprint"])
    b.last_player_text = "I want a big shipwreck."
    first = b.blueprint_found({**SHIPS, "matches": list(SHIPS["matches"])})
    assert "confirm" in first["say"], "the first time she asks"
    b.last_player_text = "upright."
    upright = {**SHIPS, "matches": [SHIPS["matches"][1], SHIPS["matches"][0]]}
    second = b.blueprint_found(upright)
    assert "build shipwreck_rightsideup_full now" in second["say"] and "confirm" not in second["say"]
    b.last_player_text = "no, wait"
    third = b.blueprint_found({**SHIPS, "matches": list(SHIPS["matches"])})
    assert "build" not in third["say"].split(":")[0], "a no is never taken as a yes"


def test_yes_to_an_offered_blueprint_builds_it(stubs):  # #59, #60
    stubs.ai_script = [{"role": "assistant", "content": "[happy] Here it comes!"}]
    b = _brain(stubs, ["blueprint", "build", "guide"])
    b.blueprint_offer = ("shipwreck_rightsideup_full", b.clock())
    sent = []

    async def send(msg):
        sent.append(msg)
    b.send = send

    async def run():
        b.ws, b.in_world = object(), True
        await b.answer("build it please")
    before = len(stubs.ai_requests)
    asyncio.run(run())
    req = stubs.ai_requests[before]  # (the next one is the "answer honestly" retry: "Here it comes!" with no build)
    text = str(req.get("tool_choice")) + str(req["messages"])
    assert req.get("tool_choice") == {"type": "function", "function": {"name": "blueprint"}}
    assert "shipwreck_rightsideup_full" in text, "she's told which one they said yes to"


def test_coming_up_is_a_claim():  # #59
    for t in ("One village square, coming up!", "It's going up! Tall and dark", "The ship is on its way!"):
        assert mind.claims_action(t), t
    assert not mind.claims_action("Upright it is!")


def test_praise_gets_words_not_tools(stubs):  # #61
    for t in ("Amazing.", "Thank you.", "wow, pip!", "thanks so much"):
        assert intents.PRAISE.match(t), t
    for t in ("thanks, can you build a wall?", "amazing, now a tower"):
        assert not intents.PRAISE.match(t), t
    stubs.ai_script = [{"role": "assistant", "content": "[happy] Hehe, thank you!"}]
    b = _brain(stubs, ["blueprint", "build", "guide", "find_flat"])

    async def send(msg):
        pass
    b.send = send

    async def run():
        b.ws, b.in_world = object(), True
        await b.answer("Amazing.")
    asyncio.run(run())
    assert b.offered == [], "no powers offered for a thank-you"


def test_the_same_blueprint_isnt_built_twice_unasked(stubs):  # #61
    b = _brain(stubs, ["blueprint"])
    asked = _record(b)

    async def run():
        b.last_player_text = "a long one"
        first = await b._run_tool("blueprint", {"what": "village_savanna_medium_house_1"})
        b.last_player_text = "Amazing."
        again = await b._run_tool("blueprint", {"what": "village_savanna_medium_house_1"})
        b.last_player_text = "build another one"
        third = await b._run_tool("blueprint", {"what": "village_savanna_medium_house_1"})
        return first, again, third
    first, again, third = asyncio.run(run())
    assert first["ok"] and again["ok"] is False and third["ok"]
    assert len(asked) == 2


def test_the_bed_and_spawn_point_are_places_to_go(stubs):  # #62, #63
    t = "No, that's not my spawn point. The spawn point is the bed that I last slept into."
    assert intents.SPAWN.search(t) and intents.ASKS_TO_GO.search(t.lower())
    assert intents.ASKS_TO_GO.search("it's not here!!")
    b = _brain(stubs, ["guide"])

    async def target(to, said):
        b.last_player_text = said
        return await b.guide_target({"to": to})
    assert asyncio.run(target("where you died", "Can you lead me to my spawn point?")) == {"spawn": True}
    assert asyncio.run(target("bed", "take me to my bed")) == {"spawn": True}
    assert asyncio.run(target("", "take me back to where I died")) != {"spawn": True}


def test_corrections_during_a_lead_are_allowed(stubs):  # #63
    b = _brain(stubs, ["guide"])
    asked = _record(b, {"guide": {"ok": True, "guiding": True}})

    async def run():
        b.last_player_text = b.asking_text = "I'm hurt"
        unasked = await b._run_tool("guide", {"x": 1, "z": 2})
        b.led_at = b.clock()  # a lead they asked for, a moment ago
        b.last_player_text = b.asking_text = "No, you are mistaken."
        corrected = await b._run_tool("guide", {"x": 1, "z": 2})
        return unasked, corrected
    unasked, corrected = asyncio.run(run())
    assert unasked["ok"] is False and corrected["ok"]


def test_getting_your_things_back_is_the_job_not_copies(stubs):  # #64
    assert intents.action_hint("Give me back all my stuff.", ["job", "give_item"]) == "job"
    assert intents.action_hint("give me a stack of bread", ["job", "give_item"]) == "give_item"
    b = _brain(stubs, ["give_item", "job"])
    asked = _record(b)

    async def run():
        b.last_player_text = b.asking_text = "Give me back all my stuff."
        return await b._run_tool("give_item", {"item": "egg", "count": 1})
    r = asyncio.run(run())
    assert r["ok"] is False and "return_items" in r["error"] and not asked


def test_room_for_a_big_build_is_looked_for_nearby_and_big_enough(stubs):  # #66
    assert intents.action_hint("yes or find a better place wherever it can be possible", ["find_flat", "locate"]) \
        == "find_flat"
    b = _brain(stubs, ["find_flat", "blueprint"])
    b.last_player_text = "I want a big shipwreck."
    b.blueprint_found({**SHIPS, "matches": list(SHIPS["matches"])})
    asked = _record(b, {"find_flat": {"ok": True, "x": 1, "y": 64, "z": 2, "found": True}})

    async def run():
        b.last_player_text = b.asking_text = "find a better place"
        return await b._run_tool("find_flat", {"size": 10})
    asyncio.run(run())
    assert asked[0][1]["size"] >= 30, "room for the 28-long ship"


def test_poof_after_a_search_and_failed_builds_is_a_claim():  # #59
    assert mind.claims_action("Poof! A whole ship, just for you.")
    assert mind.claims_action("Done! It's right in the middle now.")
    assert "find_blueprint" in mind.LOOKUPS and "blueprint" not in mind.LOOKUPS
    assert not mind.claims_action("Are you done yet?")


def test_a_short_answer_to_her_blueprint_question_picks_and_builds(stubs):  # #60
    stubs.ai_script = [{"role": "assistant", "content": "[happy] Upright it is."}]
    b = _brain(stubs, ["blueprint", "build", "guide"])

    async def send(msg):
        pass
    b.send = send

    def first_request(text):
        b.blueprint_offer = ("shipwreck_with_mast", b.clock())
        before = len(stubs.ai_requests)

        async def run():
            b.ws, b.in_world = object(), True
            await b.answer(text)
        asyncio.run(run())
        return stubs.ai_requests[before]
    assert first_request("upright").get("tool_choice") == {"type": "function", "function": {"name": "blueprint"}}
    assert first_request("which one is bigger?").get("tool_choice") is None
    assert first_request("no, wait").get("tool_choice") is None


def test_a_power_thats_not_for_this_moment_isnt_called_forgotten(stubs):  # #61
    b = _brain(stubs, ["build", "blueprint"])
    b.offered, b.discovered = [], ["build", "blueprint"]  # ("Amazing.": no powers for this answer)
    r = asyncio.run(b._run_tool("build", {"shape": "pillar"}))
    assert r["ok"] is False and "Not for this" in r["error"]
    b.discovered = []  # (amnesia: a power she hasn't discovered yet)
    r = asyncio.run(b._run_tool("build", {"shape": "pillar"}))
    assert "don't know how" in r["error"]


def test_hush_words():  # #73
    for t in ("shh", "Shhh!", "stop talking", "be quiet", "shut up pip", "zip it"):
        assert intents.HUSH_ALWAYS.match(t), t
    for t in ("stop", "enough", "okay okay", "not now"):
        assert intents.HUSH.match(t) and not intents.HUSH_ALWAYS.match(t), t  # (only while she talks)
    for t in ("stop building", "can you stop", "be quiet when monsters come"):
        assert not intents.HUSH.match(t), t


def test_hushing_her_stops_her_at_once_and_drops_the_rest(stubs):  # #73
    b = _brain(stubs, ["build"])
    sent = []

    async def send(msg):
        sent.append(msg)
    b.send = send

    async def run():
        b.ws, b.in_world = object(), True
        b.speaking_until = b.clock() + 5          # she's talking
        b.unfinished = ("and then the sheep said...", b.clock())
        b.hear_player("shh")
        await asyncio.sleep(0)
        assert {"type": "hush"} in sent and b.unfinished is None and not b.inbox, "cut off, nothing queued"
        b.speaking_until = b.clock() - 10         # quiet now: "stop" keeps its old meaning
        b.hear_player("stop")
        assert b.inbox, "a plain 'stop' while she's quiet goes on as a request"
        b.inbox.clear()
        if b.inbox_task:
            b.inbox_task.cancel()
        b.hear_player("shh")
        await asyncio.sleep(0)
        assert b.clock() < b.short_until, "hushed twice: short answers for a while"
    asyncio.run(run())


def test_a_hushed_answer_isnt_said(stubs):  # #73
    from kindred.server import SpokenStream
    b = _brain(stubs, [])
    said = []

    async def say(text, *a, **k):
        said.append(text)
        return 1
    b.say = say

    async def run():
        speech = SpokenStream(b)
        b.hush_at = b.clock()
        speech.add("A very long story begins.", "happy", None, False)
        await speech.close()
    asyncio.run(run())
    assert said == []


SHIP_TASK = {"what": "building shipwreck rightsideup full", "done": 230, "total": 659}


def test_busy_hands_keep_a_new_task_for_after(stubs):  # #72
    b = _brain(stubs, ["build", "blueprint"])
    b.snapshot = {"task": dict(SHIP_TASK)}
    asked = _record(b)

    async def run():
        b.last_player_text = b.asking_text = "place a bell over there"
        busy = await b._run_tool("build", {"shape": "place", "block": "bell"})
        b.last_player_text = b.asking_text = "stop that and build a wall first"
        first = await b._run_tool("build", {"shape": "wall", "block": "stone"})
        return busy, first
    busy, first = asyncio.run(run())
    assert busy["ok"] is False and busy["kept"] and "busy" in busy["error"]
    assert b.task_queue[0][0] == "place a bell over there"
    assert first["ok"] and [n for n, a in asked] == ["build", "build"] and asked[0][1] == {"shape": "stop"}


def test_when_her_hands_are_free_she_does_what_was_kept(stubs):  # #72
    b = _brain(stubs, ["build"])
    done = []

    async def answer(text, *a, **k):
        done.append(text)
    b.answer = answer
    b.task_queue = [("place a bell over there", b.clock())]

    async def run():
        await b.next_task("building a farm")
    asyncio.run(run())
    assert done == ["place a bell over there"] and b.task_queue == []


def test_what_are_you_doing_has_a_true_answer():  # #72
    from kindred.describe import describe
    text = describe({"health": 20, "maxHealth": 20, "food": 20, "task": dict(SHIP_TASK)})
    assert "busy: building shipwreck rightsideup full (230 of 659" in text


def test_after_a_hush_she_doesnt_pick_the_topic_back_up(stubs):  # #73
    b = _brain(stubs, [])

    async def send(msg):
        pass
    b.send = send
    asyncio.run(b.hush("shh"))
    assert any("hushed you" in x for _, x in b.recent)
