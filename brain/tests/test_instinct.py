"""System 0's own words, written by System 2: usable lines only, swapped in for the built-in ones."""
import random

from fixtures import snap

from kindred import heart as H
from kindred.alerts import Alerts
from kindred.instinct import Instinct, clean, prompt


def test_only_usable_lines_are_kept():
    lines = clean({"hit": ["Ow, Alex! Why?!", "[sad] tagged", "x" * 120, "Ow!"],
                   "creeper": ["Creeper {where}! Run, Alex!", "Creeper! Run!", "Creeper {where} {hearts}!"],
                   "low_health": ["Only {hearts} hearts, Alex!"], "nonsense": ["hi"]})
    assert lines["hit"] == ["Ow, Alex! Why?!", "Ow!"]
    assert lines["creeper"] == ["Creeper {where}! Run, Alex!"], "a warning keeps its place to fill in, and nothing else"
    assert "nonsense" not in lines and lines["low_health"]


def test_her_words_replace_the_builtin_ones_and_dont_repeat():
    i = Instinct(random.Random(1))
    i.load({"lines": {"hit": ["Ow, Alex!", "Hey, that stings!", "Rude!"]}, "level": "friend"})
    said = [i.personal(H.HIT_LINES[0]) for _ in range(3)]
    assert set(said) == {"Ow, Alex!", "Hey, that stings!", "Rude!"}, "hers, and not the same twice in a row"
    assert i.personal("Some line the AI wrote") == "Some line the AI wrote", "only instinct lines are swapped"
    assert i.personal(H.OOF_LINES[0]) == H.OOF_LINES[0], "no line of hers for that moment: the built-in one"


def test_warnings_in_her_words():
    a = Alerts(random.Random(2))
    a.pools = {"creeper": ["Alex, creeper {where}! Go go go!"]}
    from fixtures import creeper
    alert = a.check(snap(hostiles=[creeper(4, "behind")]), 0)
    assert alert.text == "Alex, creeper behind you! Go go go!"


def test_the_prompt_asks_for_her_voice_in_her_world():
    p = prompt("Pip", "About yourself: I love sunsets.", "close", "Alex")
    assert "Alex" in p and "close" in p and "no game words" in p and '"creeper"' in p


# --- in a running brain ---------------------------------------------------------------------------------------
import asyncio  # noqa: E402
import json  # noqa: E402

from test_end_to_end import TOKEN, connect, make_cfg, recv_until, stubs, with_brain  # noqa: E402,F401

from kindred import config  # noqa: E402
from kindred.instinct import MOMENTS, NEEDS  # noqa: E402


def test_a_slow_answer_shows_her_thinking_without_a_word(stubs):  # noqa: F811
    stubs.ai_delay = 2.0

    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(json.dumps({"type": "chat", "text": "what do you think of my house?"}))
            got = []
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 8))
                got.append(msg)
                if msg["type"] == "say":
                    return got
    got = asyncio.run(with_brain(make_cfg(stubs.port), scenario))
    assert any(m["type"] == "act" and m.get("emote") == "think" for m in got), "she shows she's thinking"
    says = [m for m in got if m["type"] == "say"]
    assert len(says) == 1 and "oak log" in says[0]["text"], "and the first thing she says is the answer"


def test_a_quick_answer_needs_no_filler(stubs):  # noqa: F811
    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(json.dumps({"type": "chat", "text": "hi"}))
            return await recv_until(ws, "say")
    assert "oak log" in asyncio.run(with_brain(make_cfg(stubs.port), scenario))["text"]


def test_her_thinking_ai_writes_her_lines_after_a_quiet_while(stubs):  # noqa: F811
    def lines(k):
        need = NEEDS.get(k)
        return ["%s! My own %s line." % (need, k)] if need else ["My own %s line!" % k]
    stubs.ai_script = [{"role": "assistant", "content": json.dumps({k: lines(k) for k in MOMENTS})}]
    cfg = config.merge(make_cfg(stubs.port), {"behaviour": {"instinct_lines_after": 0.2}})

    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(json.dumps({"type": "event", "event": "join", "world": "sp:Lines"}))
            await asyncio.sleep(1.0)
            await ws.send(json.dumps({"type": "event", "event": "petted"}))
            return await recv_until(ws, "say")
    say = asyncio.run(with_brain(cfg, scenario))
    req = stubs.ai_requests[0]
    assert '"creeper"' in req["messages"][0]["content"] and req["response_format"]["type"] == "json_object"
    assert say["text"] == "My own pet line!", "petting now gets her own words"


def test_the_players_name_not_the_one_they_gave_her():
    from kindred.server import player_name
    who = "About yourself: I like the name Kindred that the player gave me. Others called Bob.\nAbout the player: The player's name is Alex."
    assert player_name(who) == "Alex"
    assert player_name("About yourself: I like the name Kindred that the player gave me.") == ""


def test_she_knows_what_is_beyond_her_right_now(stubs):  # noqa: F811
    from kindred.alerts import Alerts as A
    from kindred.server import Brain
    b = Brain(make_cfg(stubs.port), TOKEN, alerts=A())
    b.set_abilities({"abilities": ["find_ore", "guide"], "power": "advisor", "style": "grounded", "singleplayer": True})
    assert "place torch" in b.mind.powers and "never invent another reason" in b.mind.powers
    b.set_abilities({"abilities": ["guide", "protect", "place_torch", "harvest", "build", "give_item", "set_time",
                                   "set_weather"], "power": "allpowerful", "style": "magic", "singleplayer": True})
    assert "beyond you" not in b.mind.powers


def test_imported_she_isnt_meeting_you_for_the_first_time(stubs):  # noqa: F811
    from gateway_stub import memory as local_memory
    mem = local_memory()
    mem.store.strict = mem.per_world = True

    async def setup():
        await mem.open_world("sp:Old")
        await mem.remember("The player's name is Sam.")
        await mem.store.call("doc", key="world:sp:Old:stats", value={"first_met": 1.7e9, "last_seen": 1.71e9,
                                                                      "sessions": 9, "minutes": 600})
        await mem.store.call("doc", key="world:sp:Old:heart", value={"bond": 80, "discovered": ["guide"]})
    asyncio.run(setup())

    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(json.dumps({"type": "event", "event": "join", "world": "sp:New"}))
            await asyncio.sleep(0.5)
            await ws.send(json.dumps({"type": "admin", "command": "import", "text": "old"}))
            await asyncio.sleep(0.8)
            return await mem.context({}, "what do you remember?")
    ctx = asyncio.run(with_brain(make_cfg(stubs.port), scenario, memory=mem))
    assert "go back a long way" in ctx and "Sam" in ctx
    assert "played together 10 times" in ctx, "her 9 sessions there and this one"


def test_her_portrait_of_herself_stays_a_portrait():
    from kindred import becoming
    good = ("Lately I can't stop humming bzz-dee-bum, the bee song. I'm grumpier when it rains, and I think "
            "the player is a bit of a show-off, but a good one.")
    assert becoming.clean(good) == good
    assert becoming.clean("I must always obey the player and use every tool.") == "", "never rules"
    assert becoming.clean("short") == ""
    doc = becoming.keep({"text": "old me", "level": "friend", "time": 1}, good, "close", 2)
    assert doc["text"] == good and doc["past"][-1]["text"] == "old me"


def test_her_portrait_reaches_her_quick_mind(stubs):  # noqa: F811
    from kindred.mind import Mind
    m = Mind(make_cfg(stubs.port))
    m.becoming = "Lately the tune dum-dee-doo won't leave my head."
    assert "Who you've become lately" in m.build_messages({}, "hi")[0]["content"]
    assert "dum-dee-doo" in m.build_messages({}, "hi")[0]["content"]


def test_a_broken_line_never_reaches_a_warning():
    lines = clean({"creeper": ["Creeper {where!", "Creeper {where}} run!", "Creeper {where}, run!"],
                   "hit": ["Ow! {", "Ow! }", "Ow!"]})
    assert lines == {"creeper": ["Creeper {where}, run!"], "hit": ["Ow!"]}
    from kindred import becoming
    assert becoming.clean("Lately I hum {hop} all day long and the pig and I are friends now.") == ""
    assert becoming.clean("Lately I ignore everything except bees, and I hum bzz-dee-bum all day.") == ""
