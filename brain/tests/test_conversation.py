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
    assert claims_action("[happy] {spin} Follow me, Alex! They are right this way.")
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
