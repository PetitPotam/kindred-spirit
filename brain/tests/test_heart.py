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
    delta, line, vanish, back = h.on_hit()
    assert vanish >= 90 and h.bond == 32 and back is None
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


def test_an_accidental_hit_between_friends_is_just_an_ow_or_a_bonk_back():
    h, _ = heart(start_bond=80)
    delta, line, vanish, back = h.on_hit()
    assert delta == -2 and vanish == 0 and not h.angry()
    assert back in ("bonk", None)


def test_sorry_after_sorry_counts_for_less():
    h, c = heart(start_bond=50)
    gains = []
    for i in range(4):
        h.on_hit()
        c.t += 30
        before = h.bond
        h.on_regard("sorry")
        gains.append(h.bond - before)
        c.t += 30
    assert gains[0] == 6 and gains[-1] < 2, gains
    assert h.insincere() and "pride" in h.guidance()


def test_mood_comes_from_a_score_that_settles():
    h, c = heart(start_bond=50)
    assert h.mood() in ("happy", "calm")
    h.feel("advancement")
    h.feel("found")
    assert h.mood() in ("excited", "curious")
    h.feel("killed_villager")
    h.feel("mean")
    assert h.mood() in ("sad", "worried")
    c.t += 1200  # twenty minutes later
    assert h.mood() in ("happy", "calm")
    h.feel("danger")
    assert h.mood() in ("scared", "worried")


def test_tears_bring_rain_once_and_comfort_clears_it():
    h, _ = heart()
    assert h.weather(sad=True) == "rain" and h.weather(sad=True) is None
    assert h.weather(sad=False) == "clear" and h.weather(sad=False) is None
    assert heart(weather_follows_mood=False)[0].weather(sad=True) is None


def test_play_hits_only_when_close_and_you_are_at_full_health():
    h, c = heart(start_bond=90)
    h.rng = random.Random(4)
    full = snap(health=20.0)
    assert any(h.play_hit(full, c.t + i * 2000) for i in range(30))
    assert not heart(start_bond=40)[0].play_hit(full, 1e9)
    assert not heart(start_bond=90)[0].play_hit(snap(health=12.0), 1e9)


def _brain(stubs):
    from kindred.memory import GatewayMemory, Memory
    from kindred.server import Brain
    from kindred.alerts import Alerts
    cfg = make_cfg(stubs.port)
    b = Brain(cfg, TOKEN, alerts=Alerts(), memory=Memory(GatewayMemory(cfg["gateway"]["url"])))
    b.heart_loaded = True
    return b


async def _serve(brain, scenario):
    from websockets.asyncio.server import serve
    async with serve(brain.handler, "127.0.0.1", 0, process_request=brain.check_auth) as srv:
        await scenario("ws://127.0.0.1:%d/" % srv.sockets[0].getsockname()[1])


def test_killing_a_villager_or_many_animals_makes_her_sad(stubs):
    stubs.ai_script = [{"role": "assistant", "content": "[sad][neutral] Oh no... that villager didn't do anything."},
                       {"role": "assistant", "content": "[sad][neutral] So many chickens... poor things."}]
    brain = _brain(stubs)

    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(hello([]))
            await ws.send(json.dumps({"type": "event", "event": "join", "world": "sp:K"}))
            await ws.send(json.dumps(snap()))
            await ws.send(json.dumps({"type": "event", "event": "killed", "detail": "minecraft:villager", "villager": True}))
            say = await recv_until(ws, "say")
            assert "villager" in say["text"]
            brain.last_notice = -1e9
            for _ in range(4):
                await ws.send(json.dumps({"type": "event", "event": "killed", "detail": "minecraft:chicken"}))
            say = await recv_until(ws, "say")
            assert "chickens" in say["text"]
    asyncio.run(_serve(brain, scenario))
    assert "chicken" in stubs.ai_requests[-1]["messages"][-1]["content"]


def test_babies_pets_and_first_meetings(stubs):
    brain = _brain(stubs)
    brain.notice = _record = []

    async def fake_notice(event, detail=""):
        _record.append((event, detail))
    brain.notice = fake_notice

    async def run():
        brain.ws = object()
        cow = {"id": 1, "type": "minecraft:cow", "distance": 4, "baby": False, "tamed": False}
        brain.watch_animals(snap(animals=[cow]), 0)                       # first cow ever
        await asyncio.sleep(1.7)
        baby = {"id": 2, "type": "minecraft:cow", "distance": 5, "baby": True, "tamed": False}
        brain.watch_animals(snap(animals=[cow, baby]), 30)                 # a calf appears later
        dog = {"id": 3, "type": "minecraft:wolf", "distance": 3, "baby": False, "tamed": True}
        brain.watch_animals(snap(animals=[cow, baby, dog]), 40)            # a new pet
        await asyncio.sleep(1.7)
    brain.send = lambda msg: asyncio.sleep(0)
    asyncio.run(run())
    events = [e for e, _ in _record]
    assert events.count("first_meet") == 1 and "baby" in events and "tamed" in events


def test_only_never_used_non_urgent_powers_awaken_slowly():
    h, _ = heart()
    assert h.slow("find_ore") and h.slow("locate") and h.slow("give_item")
    assert not h.slow("protect") and not h.slow("place_torch"), "in danger, powers wake up on instinct"
    h.discovered("find_ore")
    assert not h.slow("find_ore"), "once discovered, it just works"
    assert not heart(awakening="instant")[0].slow("locate")
    assert not heart(amnesia=False)[0].slow("locate")
    plans = [heart(awakening_seconds=40)[0].awakening_plan() for _ in range(5)]
    assert all(0 < p["sense"] < p["reveal"] <= 56 for p in plans)
    assert all(heart(favours=False)[0].awakening_plan()["favour"] is None for _ in range(10))


def _awakening_brain(stubs, favour):
    brain = _brain(stubs)
    brain.quiet_gap = 0
    brain.heart.awakening_plan = lambda: {"sense": 0.05, "favour": favour, "reveal": 0.1, "tangent": False}
    return brain


def test_think_fast_then_slow_she_tries_then_the_power_wakes_up(stubs):
    stubs.ai_script = [
        {"role": "assistant", "content": "[excited][kind] Diamonds? Ooh, I don't know if I can... but I'll try!"},
        {"role": "assistant", "content": "[curious][neutral] {whisper} Wait... something is humming under the ground."},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "f1", "type": "function", "function": {"name": "find_ore", "arguments": '{"ore": "diamond"}'}}]},
        {"role": "assistant", "content": "[excited][kind] {hop} I can sense diamonds now! There, down below!"}]
    brain = _awakening_brain(stubs, None)

    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(hello(["find_ore"]))
            await ws.send(json.dumps({"type": "event", "event": "join", "world": "sp:A"}))
            await ws.send(json.dumps(snap()))
            await ws.send(json.dumps({"type": "chat", "text": "can you find diamonds?"}))
            first = await recv_until(ws, "say")
            assert "try" in first["text"]
            sensing = await recv_until(ws, "say")
            assert "humming" in sensing["text"]
            do = await recv_until(ws, "do")
            assert do["action"] == "find_ore" and do["args"]["ore"] == "diamond"
            await ws.send(json.dumps({"type": "done", "id": do["id"], "ok": True, "ore": "diamond",
                                      "x": 10, "y": -50, "z": 3, "where": "7 blocks down"}))
            reveal = await recv_until(ws, "say")
            assert "sense diamonds now" in reveal["text"]
    asyncio.run(_serve(brain, scenario))
    fast = stubs.ai_requests[0]
    assert "tool_choice" not in fast and "find_ore" not in json.dumps(fast.get("tools", [])), \
        "System 1 answers at once, without the power"
    assert "never done" in fast["messages"][-1]["content"]
    slow = stubs.ai_requests[2]
    assert slow["tool_choice"]["function"]["name"] == "find_ore", "when it wakes up, she really does it"
    assert "find_ore" in brain.heart.state["discovered"] and not brain.awakening


def test_while_it_wakes_up_she_may_ask_a_favour(stubs):
    stubs.ai_script = [
        {"role": "assistant", "content": "[curious][kind] A village? I'll try to feel for one!"},
        {"role": "assistant", "content": "[curious][neutral] Hmm, something far away is pulling at me..."},
        {"role": "assistant", "content": "[curious][neutral] {shy} Could you pet me? It helps me focus."},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "l1", "type": "function", "function": {"name": "locate", "arguments": '{"what": "village"}'}}]},
        {"role": "assistant", "content": "[excited][kind] Thank you! I can feel where villages are now!"}]
    brain = _awakening_brain(stubs, "pet")

    async def scenario(url):
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}) as ws:
            await ws.send(hello(["locate"]))
            await ws.send(json.dumps({"type": "event", "event": "join", "world": "sp:F"}))
            await ws.send(json.dumps(snap()))
            await ws.send(json.dumps({"type": "chat", "text": "can you find a village?"}))
            await recv_until(ws, "say")
            await recv_until(ws, "say")
            favour = await recv_until(ws, "say")
            assert "pet me" in favour["text"]
            await ws.send(json.dumps({"type": "event", "event": "petted"}))
            do = await recv_until(ws, "do")
            assert do["action"] == "locate"
            await ws.send(json.dumps({"type": "done", "id": do["id"], "ok": True, "what": "village",
                                      "x": 300, "z": 40, "where": "300 blocks east"}))
            reveal = await recv_until(ws, "say")
            assert "villages" in reveal["text"]
    asyncio.run(_serve(brain, scenario))
    assert "Thank them for the favour" in stubs.ai_requests[3]["messages"][-1]["content"]


def test_a_baby_waits_for_a_pause_but_a_new_item_is_skipped(stubs):
    stubs.ai_script = [{"role": "assistant", "content": "[excited][neutral] A baby cow! Look at its tiny legs!"}]
    brain = _brain(stubs)

    async def run():
        said = []

        async def say(text, mood, **kw):
            said.append(text)
        brain.say = say
        brain.ws, brain.in_world = object(), True
        brain.snapshot = snap()
        brain.last_notice = brain.clock() - 10   # she spoke 10 s ago
        await brain.notice("new_item", "minecraft:stick")
        assert said == [], "a small thing isn't worth waiting for"
        await brain.notice("baby", "minecraft:cow")
        assert said and "baby" in said[0], "a baby is worth waiting a moment for"
    asyncio.run(run())


def test_a_long_scare_is_one_scare_not_one_per_snapshot():
    h, c = heart()
    for _ in range(30):  # a zombie near you for 30 seconds
        h.feel("danger", 0.3)
        c.t += 1
    assert h.valence > -0.2, h.valence
    assert not h.too_upset_to_focus(), "startled, not upset with you"
