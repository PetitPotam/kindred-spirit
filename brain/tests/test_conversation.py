import asyncio
import json

from fixtures import snap
from test_end_to_end import make_cfg, stubs  # noqa: F401

from kindred.mind import Mind, parse_reply, regard_of


def test_old_turns_are_folded_not_forgotten(stubs):
    stubs.ai_script = [{"role": "assistant", "content": "They talked about a treehouse roof (open: which wood), "
                                                         "then a creeper. Promised to help with the roof."}]
    cfg = make_cfg(stubs.port)
    cfg["ai"]["history_turns"] = 2
    m = Mind(cfg)
    for i in range(5):
        m.remember("user", "player line %d" % i)
        m.remember("assistant", "[happy] pip line %d" % i)
    assert len(m.history) == 4 and len(m.to_fold) == 6
    assert asyncio.run(m.fold(every=6))
    assert "treehouse roof" in m.summary and m.to_fold == []
    sent = stubs.ai_requests[-1]["messages"][-1]["content"]
    assert "player line 0" in sent, "the turns that left the window are what gets folded"
    system = m.build_messages(snap(), "where were we?")[0]["content"]
    assert "Earlier in this conversation" in system and "treehouse roof" in system


def test_frustration_and_whisper_tags():
    assert regard_of("[sad][frustrated] Oh no, I got it wrong again!") == "frustrated"
    assert parse_reply("[curious][kind] {whisper} {hop} Psst!") == ("Psst!", "curious", "hop")


def test_she_cant_claim_an_action_she_didnt_do(stubs):
    from kindred.mind import claims_action
    assert claims_action("[worried][kind] I am trying to place a torch to keep it away from us.")
    assert claims_action("[happy] {spin} Follow me, Tam! They are right this way.")
    assert not claims_action("[curious] I wonder where the sheep went. Should we look over there?")
    stubs.ai_script = [
        {"role": "assistant", "content": "[worried][kind] I'm placing a torch right now!"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "place_torch", "arguments": "{}"}}]},
        {"role": "assistant", "content": "[happy][kind] There, a torch! Better?"}]
    did = []

    async def run_tool(name, args):
        did.append(name)
        return {"ok": True}
    from kindred import tools
    m = Mind(make_cfg(stubs.port))
    text, mood, _ = asyncio.run(m.reply(snap(), "light it up please", (), tools.for_abilities(["place_torch"]), run_tool))
    assert did == ["place_torch"], "asked to really do it"
    assert "torch" in text and "Check:" in json.dumps(stubs.ai_requests[1]["messages"][-1])


def test_fibs_only_as_a_prank_among_friends_or_when_cross():
    import random
    from kindred import config
    from kindred.heart import Heart
    cfg = config.merge(config.DEFAULTS, {"heart": {"start_bond": 30}})
    h = Heart(cfg, rng=random.Random(1))
    assert not any(h.fib(i * 1000) for i in range(200)), "strangers: never"
    h.state["bond"] = 80
    fibs = [h.fib(i * 1000) for i in range(200)]
    assert any(fibs) and all("admit" in f for f in fibs if f)
    off = Heart(config.merge(config.DEFAULTS, {"heart": {"start_bond": 80, "fibs": False}}), rng=random.Random(1))
    assert not any(off.fib(i * 1000) for i in range(200))


def test_messages_that_pile_up_get_one_answer():
    from kindred.server import merge_messages
    assert merge_messages(["hi"]) == "hi"
    assert merge_messages(["i love you"] * 9) == "i love you (said 9 times in a row)"
    m = merge_messages(["i love you", "I love you!", "protect me"])
    assert "i love you (said 2 times in a row)" in m and m.endswith("protect me")


def test_a_burst_of_messages_while_she_thinks_becomes_one_reply(stubs):
    from test_heart import _brain
    stubs.ai_script = [{"role": "assistant", "content": "[happy][sweet] Hi Tam!"},
                       {"role": "assistant", "content": "[sad][neutral] Okay, okay, I heard you. Please stop."}]
    b = _brain(stubs)
    sent = []

    async def send(msg):
        sent.append(msg)
    b.send = send

    async def run():
        b.ws, b.in_world = object(), True
        b.hear_player("hi")
        await asyncio.sleep(0.05)  # she's thinking about "hi"...
        for _ in range(9):  # ...when these arrive
            b.hear_player("i love you")
        while b.inbox_task and not b.inbox_task.done():
            await asyncio.sleep(0.05)
    asyncio.run(run())
    says = [m for m in sent if m["type"] == "say"]
    assert len(says) == 2, "two answers, not ten"
    assert "said 9 times in a row" in stubs.ai_requests[-1]["messages"][-1]["content"]
    assert b.heart.bond < 30, "nine times the same words is spam, not love (%.1f)" % b.heart.bond


def test_what_she_says_without_the_ai_is_in_its_memory_with_why(stubs):
    from test_heart import _brain
    b = _brain(stubs)
    b.send = lambda msg: asyncio.sleep(0)
    b.cfg["voice"]["enabled"] = False

    async def run():
        b.ws, b.in_world = object(), True
        await b.on_event("hit")
    asyncio.run(run())
    last = b.mind.history[-1]
    assert last["role"] == "assistant" and "the player hit you" in last["content"]
    msgs = b.mind.build_messages(snap(), "sorry, that was an accident")
    assert any("the player hit you" in m["content"] for m in msgs), "so 'sorry' makes sense to the AI"


def _speaker(stubs):
    from test_heart import _brain
    b = _brain(stubs)
    b.seconds_to_say = lambda text: len(text) / 100.0  # fast, but lines still take time
    b.cfg["voice"]["enabled"] = True
    said = []

    async def send(msg):
        if msg["type"] == "say":
            said.append(msg["text"])
    b.send = send
    b._voice = lambda text, style="": asyncio.sleep(0, result="UklGRg==")
    return b, said


def test_one_voice_asides_wait_their_turn_warnings_interrupt_and_she_finishes(stubs):
    b, said = _speaker(stubs)

    async def run():
        b.ws, b.in_world = object(), True
        answer = ("Iron golems appear when villagers feel scared, so you need beds and work stations for them. "
                  "Then you add a zombie they can see, and a pit with lava under the spawning area.")
        talking = asyncio.create_task(b.say(answer, "happy"))            # her answer (a reply)
        await asyncio.sleep(0.05)
        await b.say("The birch bark looks like paper.", "curious", prio="aside")   # a musing: not now
        await asyncio.sleep(0.2)
        await b.say("Creeper behind you! Run!", "scared", instant=True, why="a warning: creeper")
        await talking
        for _ in range(50):
            if b.resume_task and b.resume_task.done():
                break
            await asyncio.sleep(0.05)
    asyncio.run(run())
    assert "The birch bark looks like paper." not in said, "an aside never talks over her"
    assert said[1] == "Creeper behind you! Run!", "a warning interrupts at once"
    assert said[-1].startswith(("Anyway", "So, where", "As I was saying")) and "lava" in said[-1], \
        "she finishes what the warning interrupted"


def test_when_you_start_talking_she_stops_and_remembers_what_she_didnt_say(stubs):
    b, said = _speaker(stubs)

    async def run():
        b.ws, b.in_world = object(), True
        await b.say("First, gather lots of cobblestone. Then build a tall tower with water at the top.", "happy")
        await b.on_event("listening")
    asyncio.run(run())
    assert b.player_listening
    assert "interrupted before finishing" in b.mind.history[-1]["content"], "so she can come back to it"


def test_her_answer_is_spoken_sentence_by_sentence_as_it_is_written():
    from kindred.mind import Streamer
    got = []
    st = Streamer(lambda text, mood, gesture, whisper: got.append((text, mood, gesture)))
    answer = "[excited][kind] {hop} Iron golems! You need beds for villagers. Then a zombie they can see."
    for i in range(1, len(answer) + 1):  # it arrives a few characters at a time
        st.feed(answer[:i])
    assert [g[0] for g in got] == ["Iron golems!", "You need beds for villagers."], "each sentence once it ends"
    assert got[0][1:] == ("excited", "hop")
    st.finish(answer)
    assert got[-1][0] == "Then a zombie they can see."


def test_a_claimed_action_is_held_until_a_tool_really_ran():
    from kindred.mind import Streamer
    got = []
    st = Streamer(lambda text, *a: got.append(text))
    st.hold = True
    st.feed("[happy][kind] I'm placing a torch right now! It will be bright.")
    assert got == [], "not said before the check"
    st.new_round()
    st.hold = False
    st.finish("[happy][kind] There, a torch! Better?")
    assert got == ["There, a torch!", "Better?"]
