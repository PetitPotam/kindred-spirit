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


def test_a_slow_answer_gets_a_thinking_sound_first(stubs):  # noqa: F811
    stubs.ai_delay = 2.0

    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(json.dumps({"type": "chat", "text": "what do you think of my house?"}))
            first = await recv_until(ws, "say")
            second = await recv_until(ws, "say", timeout=8)
            return first, second
    first, second = asyncio.run(with_brain(make_cfg(stubs.port), scenario))
    assert first["text"] in ("Hmm...", "Ooh, let me think...", "Hmm, good question...")
    assert "oak log" in second["text"], "then the real answer"
    history = json.dumps(stubs.ai_requests[-1]["messages"])
    assert "let me think" not in history and "Hmm..." not in history, "a thinking sound isn't something she said"


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
