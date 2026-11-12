import asyncio
import json

from fixtures import snap
from test_end_to_end import TOKEN, make_cfg, recv_until, stubs, with_brain  # noqa: F401  (stubs is a fixture)
from websockets.asyncio.client import connect

from gateway_stub import memory
from kindred.tools import for_abilities


def names(tools):
    return [t["function"]["name"] for t in tools]


def test_the_ai_only_sees_allowed_tools():
    assert "give_item" not in names(for_abilities(["find_ore", "locate", "guide"]))
    assert "remember" in names(for_abilities([])), "memory tools are always there"
    for t in for_abilities(["protect", "give_item"]):
        assert t["function"]["parameters"]["properties"] is not None


def hello(abilities):
    return json.dumps({"type": "hello", "mod": "test", "minecraft": "1.21.1", "power": "helper",
                       "style": "grounded", "singleplayer": True, "abilities": abilities})


def test_find_diamonds_goes_to_the_game_and_back(stubs):
    stubs.ai_script = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "find_ore", "arguments": "{\"ore\": \"diamond\"}"}}]},
        {"role": "assistant", "content": "[excited] {hop} Diamonds, 9 blocks ahead and 12 below!"},
    ]
    mem = memory()

    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(hello(["find_ore", "locate", "guide"]))
            await ws.send(json.dumps({"type": "event", "event": "join", "world": "sp:Test"}))
            await ws.send(json.dumps(snap()))
            await ws.send(json.dumps({"type": "chat", "text": "where are diamonds?"}))
            do = await recv_until(ws, "do")
            assert do["action"] == "find_ore" and do["args"] == {"ore": "diamond"}
            await ws.send(json.dumps({"type": "done", "id": do["id"], "ok": True, "found": True, "ore": "diamond",
                                      "x": 21, "y": 58, "z": -21, "distance": 9, "direction": "ahead"}))
            say = await recv_until(ws, "say")
            assert "Diamonds" in say["text"] and say.get("emote") == "hop"
    cfg = make_cfg(stubs.port)
    cfg["heart"]["awakening"] = "instant"  # (the slow first time is tested in test_heart)
    asyncio.run(with_brain(cfg, scenario, memory=mem))
    second = next(r for r in stubs.ai_requests if any(m.get("role") == "tool" for m in r["messages"]))["messages"]
    assert second[-2]["tool_calls"][0]["id"] == "call_1", "the call goes back to the AI with its id"
    assert second[-1]["role"] == "tool" and json.loads(second[-1]["content"])["distance"] == 9
    found = asyncio.run(mem.store.call("list", kinds=["found"], world="sp:Test"))["results"]
    assert found[0]["meta"]["what"] == "diamond ore", "and it remembers where"
    assert "find_ore" in names(stubs.ai_requests[0]["tools"])


def test_it_remembers_what_you_tell_it(stubs):
    stubs.ai_script = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c2", "type": "function", "function": {"name": "remember", "arguments": "{\"fact\": \"Favourite colour is blue\"}"}}]},
        {"role": "assistant", "content": "[happy] Blue! I'll remember."},
    ]
    mem = memory()

    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(hello([]))
            await ws.send(json.dumps({"type": "event", "event": "join", "world": "sp:T"}))
            await ws.send(json.dumps({"type": "chat", "text": "my favourite colour is blue"}))
            await recv_until(ws, "say")
    asyncio.run(with_brain(make_cfg(stubs.port), scenario, memory=mem))
    facts = asyncio.run(mem.store.call("list", kinds=["player"], all_worlds=True))["results"]
    assert facts[0]["text"] == "Favourite colour is blue"


def test_a_forbidden_tool_is_refused_without_asking_the_game(stubs):
    stubs.ai_script = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c3", "type": "function", "function": {"name": "give_item", "arguments": "{\"item\": \"diamond\"}"}}]},
        {"role": "assistant", "content": "[sad] I can't make diamonds appear out of nothing."},
    ]

    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(hello(["find_ore"]))
            await ws.send(json.dumps({"type": "chat", "text": "give me diamonds"}))
            tip = await recv_until(ws, "notice")  # the way to allow it: a hint for the player, not her words
            assert "/kindred style magic" in tip["text"]
            say = await recv_until(ws, "say")  # no "do" ever arrives
            assert "out of nothing" in say["text"]
    asyncio.run(with_brain(make_cfg(stubs.port), scenario))
    assert "beyond what you can do" in stubs.ai_requests[-1]["messages"][-1]["content"]


def test_leaving_writes_a_diary_entry(stubs):
    stubs.ai_script = [
        {"role": "assistant", "content": "[happy] Hi!"},
        {"role": "assistant", "content": "[happy] Sure!"},
        {"role": "assistant", "content": json.dumps({
            "player": [{"text": "Wants to build a birch cabin.", "importance": 7}], "self": [], "habit": [], "world": [],
            "diary": "We chatted about birch and I promised to help build a cabin."})},
    ]
    mem = memory()

    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(hello([]))
            await ws.send(json.dumps({"type": "event", "event": "join", "world": "sp:Diary"}))
            for text in ("hi", "help me build a cabin?"):
                await ws.send(json.dumps({"type": "chat", "text": text}))
                await recv_until(ws, "say")
            await ws.send(json.dumps({"type": "event", "event": "leave"}))
            await asyncio.sleep(0.5)
    asyncio.run(with_brain(make_cfg(stubs.port), scenario, memory=mem))
    rows = lambda kind: asyncio.run(mem.store.call("list", kinds=[kind], world="sp:Diary"))["results"]  # noqa: E731
    assert "cabin" in rows("diary")[0]["text"]
    assert rows("player")[0]["text"] == "Wants to build a birch cabin.", "it learned something about you"
    assert len(asyncio.run(mem.history())) == 4, "the conversation is kept for next time"
    assert stubs.ai_requests[-1].get("response_format") == {"type": "json_object"}
