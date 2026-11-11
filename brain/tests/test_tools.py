import asyncio
import json
import tempfile

from fixtures import snap
from test_end_to_end import TOKEN, make_cfg, recv_until, stubs, with_brain  # noqa: F401  (stubs is a fixture)
from websockets.asyncio.client import connect

from kindred.memory import Memory
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
    mem = Memory(tempfile.mkdtemp())

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
    asyncio.run(with_brain(make_cfg(stubs.port), scenario, memory=mem))
    second = stubs.ai_requests[-1]["messages"]
    assert second[-2]["tool_calls"][0]["id"] == "call_1", "the call goes back to the AI with its id"
    assert second[-1]["role"] == "tool" and json.loads(second[-1]["content"])["distance"] == 9
    assert mem.world["found"][0]["what"] == "diamond ore", "and it remembers where"
    assert "find_ore" in names(stubs.ai_requests[0]["tools"])


def test_it_remembers_what_you_tell_it(stubs):
    stubs.ai_script = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c2", "type": "function", "function": {"name": "remember", "arguments": "{\"fact\": \"Favourite colour is blue\"}"}}]},
        {"role": "assistant", "content": "[happy] Blue! I'll remember."},
    ]
    mem = Memory(tempfile.mkdtemp())

    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(hello([]))
            await ws.send(json.dumps({"type": "chat", "text": "my favourite colour is blue"}))
            await recv_until(ws, "say")
    asyncio.run(with_brain(make_cfg(stubs.port), scenario, memory=mem))
    assert Memory(mem.dir).you["facts"][0]["text"] == "Favourite colour is blue"


def test_a_forbidden_tool_is_refused_without_asking_the_game(stubs):
    stubs.ai_script = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c3", "type": "function", "function": {"name": "give_item", "arguments": "{\"item\": \"diamond\"}"}}]},
        {"role": "assistant", "content": "[sad] I can't make diamonds appear in grounded style."},
    ]

    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(hello(["find_ore"]))
            await ws.send(json.dumps({"type": "chat", "text": "give me diamonds"}))
            say = await recv_until(ws, "say")  # no "do" ever arrives
            assert "grounded" in say["text"]
    asyncio.run(with_brain(make_cfg(stubs.port), scenario))
    assert "settings don't let me" in stubs.ai_requests[-1]["messages"][-1]["content"]


def test_leaving_writes_a_diary_entry(stubs):
    stubs.ai_script = [
        {"role": "assistant", "content": "[happy] Hi!"},
        {"role": "assistant", "content": "[happy] Sure!"},
        {"role": "assistant", "content": "We chatted about birch and I promised to help build a cabin."},
    ]
    mem = Memory(tempfile.mkdtemp())

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
    diary = Memory(mem.dir)
    diary.open_world("sp:Diary")
    assert "cabin" in diary.world["diary"][0]["text"]
    assert len(diary.world["history"]) == 4, "the conversation is kept for next time"
