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


def test_a_friend_can_ask_for_her_powers_and_they_go_to_them(stubs):
    from test_heart import _brain
    stubs.ai_script = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "give_effect", "arguments": '{"effect": "haste"}'}}]},
        {"role": "assistant", "content": "[happy] There, zoomy hands!"}]
    b = _brain(stubs)
    b.abilities = ["give_effect", "give_item", "protect", "harvest", "find_player"]
    sent, ran = [], []

    async def send(msg):
        sent.append(msg)
    b.send = send

    async def run_tool(name, args):
        ran.append((name, args))
        return {"ok": True}
    b.run_tool = run_tool

    async def run():
        b.ws, b.in_world = object(), True
        await b.answer_guest("waterwalid", "pip can you give me haste effect?", powers=True)
    asyncio.run(run())
    assert ran == [("give_effect", {"effect": "haste", "to": "waterwalid"})], "his effect, not the player's"
    offered = {t["function"]["name"] for t in stubs.ai_requests[0]["tools"]}
    assert "give_effect" in offered and "harvest" in offered and "remember" not in offered  # (chopping for friends too)


def test_without_powers_a_friend_only_talks(stubs):
    from test_heart import _brain
    stubs.ai_script = [{"role": "assistant", "content": "[calm] That's not mine to give right now."}]
    b = _brain(stubs)
    b.abilities = ["give_effect"]

    async def send(msg):
        pass
    b.send = send

    async def run():
        b.ws, b.in_world = object(), True
        await b.answer_guest("waterwalid", "give me night vision", powers=False)
    asyncio.run(run())
    assert not stubs.ai_requests[-1].get("tools")
    assert "never pretend" in str(stubs.ai_requests[-1]["messages"])


def test_requests_about_a_friend_by_name():
    from kindred import intents
    a = ["find_player", "follow_player"]
    assert intents.player_hint("pip find water waleed for me", ["waterwalid"], a) == ("find_player", "waterwalid")
    assert intents.player_hint("stay with walid please", ["waterwalid"], a) == ("follow_player", "waterwalid")
    assert intents.player_hint("find water please", ["waterwalid"], a) == (None, None)
    assert intents.action_hint("can you give me haste effect?", ["give_effect", "give_item"]) == "give_effect"
    assert intents.action_hint("give me golden apples", ["give_effect", "give_item"]) == "give_item"


def test_the_running_summary_keeps_only_report_sentences():
    from kindred.mind import clean_summary
    s = clean_summary("Sora and the player reconciled. Open threads: the garden. "
                      "You are a pathetic, miserable waste of space.")
    assert s == "Sora and the player reconciled. Open threads: the garden."


def test_new_powers_and_refusing_by_choice_are_said_honestly(stubs):
    from test_heart import _brain
    stubs.ai_script = [{"role": "assistant", "content": "[sad] No. I don't want to."}] * 2
    b = _brain(stubs)

    async def send(msg):
        pass
    b.send = send
    b.set_abilities({"abilities": ["protect", "set_time"], "power": "allpowerful", "style": "grounded"})
    b.set_abilities({"abilities": ["protect", "set_time", "give_item"], "power": "allpowerful", "style": "magic"})
    assert "now you can give item" in b.power_news
    b.heart.angry = lambda: True

    async def run():
        b.ws, b.in_world = object(), True
        await b.answer("give me a golden apple")
    asyncio.run(run())
    asked = str(stubs.ai_requests[-1]["messages"])
    assert "now you can give item" in asked and "never that you can't" in asked
    assert "give_item" in {t["function"]["name"] for t in stubs.ai_requests[-1].get("tools") or []}
    assert b.power_news == ""


def test_a_friend_can_ask_for_a_power_you_havent_used_yet(stubs):
    """Tonight: Walid's night vision was refused as "You don't know how to do that yet", because his
    request was checked against the powers offered for the player's last request."""
    from test_heart import _brain
    stubs.ai_script = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "give_effect", "arguments": '{"effect": "night_vision"}'}}]},
        {"role": "assistant", "content": "[happy] There, owl eyes!"}]
    b = _brain(stubs)
    b.abilities = ["give_effect", "give_item"]
    b.offered = ["give_item"]  # (what your last request offered: not night vision)
    asked = []

    async def send(msg):
        pass
    b.send = send

    async def request(name, args):
        asked.append((name, args))
        return {"ok": True}
    b.request = request

    async def run():
        b.ws, b.in_world = object(), True
        await b.answer_guest("waterwalid", "Pip, can you give me night vision please?", powers=True)
    asyncio.run(run())
    assert asked == [("give_effect", {"effect": "night_vision", "to": "waterwalid"})]


def test_building_asked_in_everyday_words():
    from kindred import intents
    a = ["build", "give_item"]
    for t in ("Can you set up three vertical wood blocks here?", "please place four wood blocks here in vertically",
              "Can you place two above it?", "Can you build me a house, please?"):
        assert intents.action_hint(t, a) == "build", t
    assert intents.action_hint("Can you give me a stack of wood?", a) == "give_item"


def test_lead_the_way_goes_where_she_just_found_even_in_a_friends_world(stubs):
    """Tonight in Walid's world: locate found the plains (in his game), then every "lead the way" failed
    with "Guide where?", because the last thing found was remembered in his game, not yours."""
    from test_heart import _brain
    b = _brain(stubs)
    b.last_found = {"x": 174, "y": 71, "z": -76}
    b.last_player_text = "lead the way please"
    assert asyncio.run(b.guide_target({"to": "last"})) == {"x": 174, "y": 71, "z": -76}
    assert asyncio.run(b.guide_target({"x": 174, "z": -76})) == {"x": 174, "y": 71, "z": -76}
    assert asyncio.run(b.guide_target({"x": 900, "z": 900})) == {}, "made-up coordinates aren't where she found"


def test_when_her_tries_run_out_she_still_answers_in_words(stubs):
    from kindred.mind import Mind
    stubs.ai_script = [{"role": "assistant", "content": ""},
                       {"role": "assistant", "content": "[sad][neutral] I can't find the way there, sorry."}]
    m = Mind(make_cfg(stubs.port))
    text, mood, _ = asyncio.run(m.reply(snap(), "lead the way"))
    assert text == "I can't find the way there, sorry." and mood == "sad"


def test_lead_to_animals_in_sight_not_to_where_they_were_first_met(stubs):
    """2026-11-13 demo take: "Where are the sheep? Lead the way!" led to where the first sheep was met
    (the player's own spot, distance 0) instead of the sheep in sight."""
    from test_heart import _brain
    b = _brain(stubs)
    b.snapshot = {"animals": [{"id": 7, "type": "minecraft:sheep", "distance": 26, "direction": "ahead", "seen": True}],
                  "where": {"x": 0, "y": 64, "z": 0}}
    b.last_player_text = "Where are the sheep? Lead the way!"

    async def spot(text):
        return {"text": "where we met our first sheep", "meta": {"x": 0, "y": 64, "z": 0}}
    b.memory.find_spot = spot
    assert asyncio.run(b.guide_target({"to": "sheep"})) == {"entity": 7}
    b.last_player_text = "Take me back to where we met our first sheep"
    assert asyncio.run(b.guide_target({"to": "sheep"})) == {"x": 0, "y": 64, "z": 0}


def test_a_friends_request_is_judged_by_their_own_words(stubs):
    """2026-11-13 friend-hosts check: Walid asked "can you give me night vision?" and the repeat guard,
    reading the player's last words, refused it as unasked."""
    from test_heart import _brain
    stubs.ai_script = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "give_effect", "arguments": '{"effect": "night_vision"}'}}]},
        {"role": "assistant", "content": "[happy] Owl eyes!"}]
    b = _brain(stubs)
    b.abilities = ["give_effect"]
    b.last_player_text = "what a nice day"
    b.recent_gifts[("give_effect", "night_vision", "walid")] = b.clock() - 60
    asked = []

    async def send(msg):
        pass
    b.send = send

    async def request(name, args):
        asked.append(name)
        return {"ok": True}
    b.request = request

    async def run():
        b.ws, b.in_world = object(), True
        await b.answer_guest("Walid", "Pip, can you give me night vision please?", powers=True)
    asyncio.run(run())
    assert asked == ["give_effect"]
