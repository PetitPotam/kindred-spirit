import asyncio
import json
import random

from fixtures import creeper, snap, zombie
from test_end_to_end import TOKEN, make_cfg, recv_until, stubs, with_brain  # noqa: F401
from websockets.asyncio.client import connect

from kindred import config
from kindred.heart import Heart, level_of


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def heart(**overrides):
    cfg = config.merge(config.DEFAULTS, {"heart": overrides})
    c = Clock()
    return Heart(cfg, clock=c, rng=random.Random(3)), c


def test_kindness_brings_her_closer_rudeness_pushes_her_away():
    h, _ = heart(start_bond=40)
    assert h.level() == "friend"
    h.on_regard("sweet")
    h.on_regard("sweet")
    assert h.bond == 48
    h.on_regard("mean")
    assert h.bond == 36 and h.angry(), "upset for a while after a mean message"
    assert h.closeness() <= 0.1, "keeps her distance while hurt"
    h.on_regard("sorry")
    assert not h.angry(), "quick to forgive"


def test_levels():
    assert [level_of(b) for b in (0, 20, 50, 70, 90)] == ["hurt", "wary", "friend", "close", "best friend"]


def test_three_hits_and_she_vanishes():
    h, c = heart(start_bond=50)
    assert h.on_hit()[2] == 0
    c.t += 5
    assert h.on_hit()[2] == 0
    c.t += 5
    delta, line, vanish = h.on_hit()
    assert vanish >= 90 and h.bond == 32
    assert not heart(start_bond=50, can_vanish=False)[0].on_hit()[2]


def test_time_heals_up_to_a_friendly_baseline_only():
    h, c = heart(start_bond=10)
    c.t += 1000
    h.drift(10)
    assert h.bond == 20
    h.drift(100)
    assert h.bond == 40
    h.drift(100)
    assert h.bond == 40, "time doesn't make her love you, only forgive"


def test_amnesia_she_only_knows_what_she_discovered():
    h, _ = heart()
    allowed = ["find_ore", "locate", "guide", "stop_guide", "protect"]
    assert h.offered_tools(allowed) == []
    assert h.offered_tools(allowed, "find_ore") == ["find_ore"], "she tries what you ask for"
    assert h.discovered("find_ore") and not h.discovered("find_ore")
    assert h.offered_tools(allowed) == ["find_ore"]
    assert "find ore" in h.discovery_note(allowed)
    assert heart(amnesia=False)[0].offered_tools(allowed) == allowed


def test_offers_only_after_youve_asked_once_and_not_too_often():
    h, c = heart(start_bond=50)
    assert h.offer("protect", c.t) is None
    h.discovered("protect")
    assert h.offer("protect", c.t) == "Want me to push them away?"
    assert h.offer("protect", c.t + 30) is None
    assert h.take_offer(c.t + 5)["what"] == "protect"
    assert h.take_offer(c.t + 5) is None


def test_standing_requests_and_auto_protect():
    h, _ = heart()
    assert not h.wants("protect")
    h.add_request("protect")
    assert h.wants("protect")
    h.drop_request("protect")
    assert not h.wants("protect")
    assert heart(auto_protect=True)[0].wants("protect")


def test_pranks_only_among_friends_or_when_angry_and_never_in_danger():
    dark = snap(where={"x": 0, "y": 20, "z": 0, "skyVisible": False, "light": 3, "dimension": "minecraft:overworld"})
    stranger, c = heart(start_bond=30)
    assert stranger.prank(dark, 60, True, False, c.t) is None
    friend, c = heart(start_bond=70)
    friend.rng = random.Random(1)
    p = None
    for i in range(20):
        p = p or friend.prank(dark, 60, True, False, c.t + i * 1000)
    assert p and p["action"] == "prank_sound"
    danger = snap(hostiles=[zombie(5)])
    assert heart(start_bond=90)[0].prank(danger, 60, True, False, 1e9) is None
    angry, c = heart(start_bond=5)
    got = [angry.prank(dark, 60, False, True, c.t + i * 300) for i in range(20)]
    assert any(g and g["action"] == "steal_block" for g in got), "spicy mischief borrows your blocks"
    mild, c = heart(start_bond=5, mischief_when_angry="mild")
    got = [mild.prank(dark, 60, False, True, c.t + i * 300) for i in range(20)]
    assert all(g is None or g["action"] == "prank_sound" for g in got)
    off, c = heart(start_bond=5, mischief_when_angry="off", pranks=False)
    assert all(off.prank(dark, 60, True, True, c.t + i * 300) is None for i in range(20))


def test_curious_about_new_things_but_not_twice():
    h, _ = heart()
    h.rng = random.Random(0)
    first = [h.notice("new_item", "minecraft:spyglass", snap()) for _ in range(1)]
    assert h.notice("new_item", "minecraft:spyglass", snap()) is None, "not twice"
    assert "Advancement" not in (h.notice("advancement", "Stone Age", snap()) or "")
    assert "Stone Age" in h.notice("advancement", "Stone Age", snap())
    assert heart(curiosity=False)[0].notice("advancement", "x", snap()) is None
    assert first is not None


def hello(abilities):
    return json.dumps({"type": "hello", "mod": "test", "minecraft": "1.21.1", "power": "helper", "style": "grounded",
                       "singleplayer": True, "abilities": abilities})


def test_hitting_her_hurts_the_bond_and_she_says_so(stubs):
    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(hello(["find_ore"]))
            await ws.send(json.dumps({"type": "event", "event": "join", "world": "sp:H"}))
            await ws.send(json.dumps({"type": "event", "event": "hit"}))
            bond = await recv_until(ws, "bond")
            while bond["change"] == 0:
                bond = await recv_until(ws, "bond")
            assert bond["change"] < 0
            act = await recv_until(ws, "act")
            assert act["closeness"] <= 0.1
            say = await recv_until(ws, "say")
            assert say["mood"] == "sad"
    asyncio.run(with_brain(make_cfg(stubs.port), scenario))


def test_she_offers_help_and_yes_makes_her_do_it(stubs):
    stubs.ai_script = [{"role": "assistant", "content": "", "tool_calls": [
        {"id": "p1", "type": "function", "function": {"name": "protect", "arguments": "{}"}}]},
        {"role": "assistant", "content": "[scared][kind] Shoo, go away zombies!"}]

    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(hello(["protect"]))
            await ws.send(json.dumps({"type": "event", "event": "join", "world": "sp:O"}))
            # she has protected you once before
            from kindred import server  # noqa: F401
            await ws.send(json.dumps(snap(health=14.0, hostiles=[zombie(4)])))
            await asyncio.sleep(0.3)
            await ws.send(json.dumps({"type": "chat", "text": "yes please"}))
            await asyncio.sleep(0.1)
            do = await recv_until(ws, "do")
            assert do["action"] == "protect"
            await ws.send(json.dumps({"type": "done", "id": do["id"], "ok": True, "pushedAway": 1}))
            await recv_until(ws, "say")

    async def run():
        cfg = make_cfg(stubs.port)
        # a brain whose heart remembers protecting you once
        from kindred.memory import GatewayMemory, Memory
        from kindred.server import Brain
        from kindred.alerts import Alerts
        from websockets.asyncio.server import serve
        brain = Brain(cfg, TOKEN, alerts=Alerts(), memory=Memory(GatewayMemory(cfg["gateway"]["url"])))
        brain.heart_loaded = True
        brain.heart.state["asked"]["protect"] = 1
        brain.heart.state["discovered"].append("protect")
        brain.heart.state["bond"] = 50
        async with serve(brain.handler, "127.0.0.1", 0, process_request=brain.check_auth) as srv:
            await scenario("ws://127.0.0.1:%d/" % srv.sockets[0].getsockname()[1])
        return brain
    brain = asyncio.run(run())
    assert stubs.ai_requests[0]["tool_choice"]["function"]["name"] == "protect", "'yes' means: do what you offered"


def test_auto_protect_never_blocks_the_conversation(stubs):
    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(hello(["protect"]))
            await ws.send(json.dumps({"type": "event", "event": "join", "world": "sp:P"}))
            await ws.send(json.dumps(snap(hostiles=[zombie(4)])))
            do = await recv_until(ws, "do")
            assert do["action"] == "protect"
            # before answering the game's action, the player talks: it must still be heard
            await ws.send(json.dumps({"type": "chat", "text": "hello"}))
            await ws.send(json.dumps({"type": "done", "id": do["id"], "ok": True, "pushedAway": 1}))
            say = await recv_until(ws, "say", timeout=5)
            assert say["text"]

    async def run():
        cfg = make_cfg(stubs.port)
        from kindred.memory import GatewayMemory, Memory
        from kindred.server import Brain
        from kindred.alerts import Alerts
        from websockets.asyncio.server import serve
        brain = Brain(cfg, TOKEN, alerts=Alerts(), memory=Memory(GatewayMemory(cfg["gateway"]["url"])))
        brain.heart_loaded = True
        brain.heart.add_request("protect")
        async with serve(brain.handler, "127.0.0.1", 0, process_request=brain.check_auth) as srv:
            await scenario("ws://127.0.0.1:%d/" % srv.sockets[0].getsockname()[1])
    asyncio.run(run())
