"""Friends on your LAN world, without the mod, talk to her in chat (mod: guest/GuestBridge.java)."""
import asyncio

from fixtures import snap
from test_end_to_end import make_cfg, stubs  # noqa: F401

from kindred.describe import describe


def test_a_friend_in_chat_gets_an_answer_and_the_bond_stays_yours(stubs):
    from test_heart import _brain
    stubs.ai_script = [{"role": "assistant", "content": "[happy][mean] Ha! Nice try, Sam."}]
    b = _brain(stubs)
    sent = []

    async def send(msg):
        sent.append(msg)
    b.send = send
    before = (b.heart.bond, dict(b.heart.rel.s))

    async def run():
        b.ws, b.in_world = object(), True
        await b.on_message({"type": "chat", "text": "Pip, you're useless", "from": "Sam"})
        for _ in range(40):
            if any(m["type"] == "say" for m in sent):
                break
            await asyncio.sleep(0.05)
    asyncio.run(run())
    asked = stubs.ai_requests[-1]["messages"][-1]["content"]
    assert "Sam, another player here" in asked and "you're useless" in asked
    assert "your bond is with the player, not with Sam" in str(stubs.ai_requests[-1]["messages"])
    assert [m["text"] for m in sent if m["type"] == "say"] == ["Ha! Nice try, Sam."]
    assert b.heart.bond == before[0], "a friend's words don't move her heart"
    assert b.inbox == [], "and they aren't taken as yours"


def test_she_knows_who_else_is_here():
    s = snap()
    s["players"] = [{"name": "Sam", "distance": 6.2, "direction": "left", "seen": True},
                    {"name": "Alex", "distance": 30, "direction": "behind", "seen": False}]
    text = describe(s)
    assert "Sam, 6 blocks" in text and "Alex, 30 blocks" in text and "(out of sight)" in text
    assert "Other players" not in describe(snap())
