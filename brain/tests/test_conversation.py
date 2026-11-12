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
