"""Talker first (kindred/talker.py): a plain command is answered by System 0 alone, at once, no AI."""
import asyncio
import json

from fixtures import snap
from test_end_to_end import make_cfg, recv_until, stubs, TOKEN  # noqa: F401
from websockets.asyncio.client import connect

from kindred import intents, talker


def kind_of(text):
    acts, _ = intents.match(text)
    moving = next((a["move"] for a in acts if a.get("move") in ("follow", "stay", "come")), None)
    return talker.plain_command(text, moving)


def test_only_plain_commands_skip_the_ai():
    assert kind_of("Follow me please.") == "follow"
    assert kind_of("Pip, can you follow me?") == "follow"
    assert kind_of("Don't lead. Stop leading. Follow me.") == "follow"
    assert kind_of("Stand still. Don't move.") == "stay"
    assert kind_of("Wait here for me, ok?") == "stay"
    assert kind_of("Come here!") == "come"
    for more in ("follow me and tell me what you see", "follow walid", "Can you please follow and defend Waleed?",
                 "Stay here and look at me", "No, no. Can you please follow me? You're not understanding.",
                 "where are you? follow me", "follow me to the cherry house"):
        assert kind_of(more) is None, more


def test_follow_me_is_answered_at_once_without_the_ai(stubs):
    from test_heart import _brain
    brain = _brain(stubs)

    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(json.dumps({"type": "hello", "mod": "test", "minecraft": "1.21.1",
                                      "abilities": ["guide", "follow_player"]}))
            await ws.send(json.dumps({"type": "event", "event": "join", "world": "sp:T"}))
            await ws.send(json.dumps(snap()))
            await ws.send(json.dumps({"type": "chat", "text": "Follow me please."}))
            act = await recv_until(ws, "act")
            while act.get("move") is None:
                act = await recv_until(ws, "act")
            assert act["move"] == "follow"
            say = await recv_until(ws, "say")
            assert say["text"] in talker.LINES["follow_ok"]
    from test_heart import _serve
    asyncio.run(_serve(brain, scenario))
    assert [r for r in stubs.ai_requests if "Follow me" in json.dumps(r)] == [], "no AI call for a plain command"
    assert brain.mind.history[-2] == {"role": "user", "content": "Follow me please."}, "the AI hears it afterwards"


def test_her_own_words_for_it_once_system_2_wrote_them():
    from kindred import instinct
    assert "follow_ok" in instinct.MOMENTS and "stay_ok" in instinct.MOMENTS
    got = instinct.clean({"follow_ok": ["Glued to you!", "Right here, right here!"]})
    assert got["follow_ok"] == ["Glued to you!", "Right here, right here!"]
