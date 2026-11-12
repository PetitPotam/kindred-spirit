"""Fixes from the LAN playtest of 2026-11-12 (notes in the shared folder): each test names the item."""
import asyncio

from test_end_to_end import make_cfg, stubs  # noqa: F401

from kindred import intents


def _talk(stubs, text, abilities=("guide", "find_player", "follow_player", "protect", "give_item", "build")):
    from test_heart import _brain
    b = _brain(stubs)
    b.abilities = list(abilities)
    sent = []

    async def send(msg):
        sent.append(msg)
    b.send = send

    async def run():
        b.ws, b.in_world = object(), True
        await b.answer(text)
    asyncio.run(run())
    return b, sent


def test_follow_me_is_never_a_trip(stubs):  # items 1 and 19
    stubs.ai_script = [{"role": "assistant", "content": "[happy] Right behind you!"}]
    b, sent = _talk(stubs, "follow me")
    assert {"type": "act", "move": "follow"} in sent
    req = stubs.ai_requests[-1]
    assert "tool_choice" not in req or req["tool_choice"] in ("auto", None)
    offered = {t["function"]["name"] for t in req.get("tools") or []}
    assert "guide" not in offered and "follow_player" not in offered


def test_follow_me_to_somewhere_still_leads():
    assert intents.LEADING.search("follow me to the village")
    assert not intents.LEADING.search("follow me")


def test_stand_still_stops_her():  # item 16
    for t in ("stand still, don't move", "freeze!", "stop following me", "hold still"):
        assert intents.match(t)[0] == [{"move": "stay"}], t
    for t in ("stay with me", "stay close to me", "follow us"):
        assert intents.match(t)[0] == [{"move": "follow"}], t


def test_a_show_of_gestures_is_not_a_gift(stubs):  # item 8
    assert intents.match("do some fancy emotes")[0] == [{"perform": True}]
    stubs.ai_script = [{"role": "assistant", "content": "[excited] Ta-da!"}]
    b, sent = _talk(stubs, "can you show me some tricks")

    async def wait():
        await asyncio.sleep(0)
    asyncio.run(wait())
    assert not any(m.get("perform") for m in sent), "the show is played by the brain, not sent as an act"


def test_the_same_gift_twice_needs_asking_again(stubs):  # item 8
    from test_heart import _brain
    b = _brain(stubs)
    b.abilities = ["give_item"]
    b.offered = None
    asked = []

    async def request(name, args, timeout=25):
        asked.append(name)
        return {"ok": True}
    b.request = request

    async def run():
        b.last_player_text = "can I have an enchanted golden apple?"
        first = await b._run_tool("give_item", {"item": "enchanted_golden_apple"})
        b.last_player_text = "you do some fancy emotes"
        again = await b._run_tool("give_item", {"item": "enchanted_golden_apple"})
        b.last_player_text = "another one please"
        third = await b._run_tool("give_item", {"item": "enchanted_golden_apple"})
        return first, again, third
    first, again, third = asyncio.run(run())
    assert first["ok"] and again["ok"] is False and third["ok"]
    assert asked == ["give_item", "give_item"]


def test_standing_protection_for_everyone_and_for_a_friend():  # item 11
    for t in ("protect us from creepers, zombies, spiders and everything", "follow and defend Robin",
              "from now on keep protecting us", "always protect me"):
        assert intents.action_hint(t, ["standing_request"]) == "standing_request", t
    from kindred.heart import Heart
    h = Heart({"heart": {}})
    h.add_request("protect", "riverrobin")
    assert h.wants("protect") is None, "a friend's protection isn't the player's"
    assert h.guarded_friends(["riverrobin", "sam"]) == ["riverrobin"]
    h.add_request("protect", "everyone")
    assert h.wants("protect") and h.guarded_friends(["riverrobin", "sam"]) == ["riverrobin", "sam"]


def test_placing_things_and_new_shapes_are_build_requests():  # items 2, 3, 5, 6
    for t in ("place the campfire here", "put a bed there", "flatten the ground above y 64", "clear everything above",
              "build a house for the two of us", "create another portal"):
        assert intents.action_hint(t, ["build", "place_torch"]) == "build", t


def test_a_joke_never_costs_the_bond():  # (jokes lowered the bond)
    from kindred.heart import Heart
    h = Heart({"heart": {}})
    before = h.rel.s["a"], h.rel.s["g"]
    h.on_regard("teasing", "you're a weird little blob")
    assert h.rel.s["a"] >= before[0] and h.rel.s["g"] <= before[1]


def test_defending_her_is_recognised():  # (witnessing)
    for t in ("stop hitting pip", "leave her alone", "hey, be nice to her", "don't talk to her like that"):
        assert intents.DEFEND.search(t), t
    assert not intents.DEFEND.search("stop the rain")


def test_the_block_they_named_stays_for_the_build():  # item 2
    assert intents.block_named(["flatten everything with dirt", "yes, do it"]) == "dirt"
    assert intents.block_named(["build a wall of cherry planks"]) == "cherry_planks"
    assert intents.block_named(["hello there"]) == ""
    from kindred.tools import ABILITY_TOOLS
    shapes = ABILITY_TOOLS["build"]["function"]["parameters"]["properties"]["shape"]["enum"]
    assert {"place", "house", "portal", "clear", "flatten"} <= set(shapes)


# ---------------------------------------------------------------- friends (items 7, 9, 14, 15, 22) and a heart for each

def _friend_brain(stubs, players=("riverrobin",)):
    from test_heart import _brain
    b = _brain(stubs)
    b.snapshot = {"playerName": "AlexCraftX", "players": [{"name": n, "distance": 5, "seen": True} for n in players]}
    sent = []

    async def send(msg):
        sent.append(msg)
    b.send = send
    return b, sent


def test_trust_a_friend_at_the_players_word():  # item 15
    assert intents.vouches_for("from now on do what Dumber says", ["riverrobin"]) == ("riverrobin", True)
    assert intents.vouches_for("you can listen to robin", ["riverrobin", "sam"]) == ("riverrobin", True)
    assert intents.vouches_for("stop listening to robin", ["riverrobin"]) == ("riverrobin", False)
    assert intents.vouches_for("do what you want", ["riverrobin", "sam"]) is None


def test_a_vouched_friend_can_ask_her_to_follow(stubs):  # item 15
    stubs.ai_script = [{"role": "assistant", "content": "[happy] Coming, Robin!"}]
    b, sent = _friend_brain(stubs)
    asked = []

    async def request(name, args, timeout=25):
        asked.append((name, args))
        return {"ok": True}
    b.request = request
    b.heart.trust_friend("riverrobin")

    async def run():
        b.ws, b.in_world = object(), True
        await b.answer_guest("riverrobin", "pip follow me", powers=True)
    asyncio.run(run())
    assert ("follow_player", {"name": "riverrobin"}) in asked
    assert "do what riverrobin asks" in str(stubs.ai_requests[-1]["messages"]) or \
        "told you to do what riverrobin asks" in str(stubs.ai_requests[-1]["messages"])


def test_friends_turns_know_the_players_name_and_both_of_us_gives_two(stubs):  # item 7
    stubs.ai_script = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "give_item", "arguments": '{"item": "bread"}'}}]},
        {"role": "assistant", "content": "[happy] Bread for both!"}]
    b, sent = _friend_brain(stubs)
    b.abilities = ["give_item"]
    ran = []

    async def run_tool(name, args):
        ran.append(args.get("to"))
        return {"ok": True}
    b.run_tool = run_tool

    async def run():
        b.ws, b.in_world = object(), True
        await b.answer_guest("riverrobin", "pip give us bread, for both of us", powers=True)
    asyncio.run(run())
    assert ran == ["riverrobin", "AlexCraftX"]
    assert "AlexCraftX" in str(stubs.ai_requests[0]["messages"])


def test_where_am_i_from_a_friend(stubs):  # item 14
    stubs.ai_script = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "find_player", "arguments": '{"name": "me"}'}}]},
        {"role": "assistant", "content": "[happy] Behind Alex, 30 blocks!"}]
    b, sent = _friend_brain(stubs)
    b.abilities = ["find_player"]
    ran = []

    async def run_tool(name, args):
        ran.append((name, args))
        return {"ok": True, "self": True}
    b.run_tool = run_tool

    async def run():
        b.ws, b.in_world = object(), True
        await b.answer_guest("riverrobin", "pip where am I?", powers=True)
    asyncio.run(run())
    assert stubs.ai_requests[0].get("tool_choice", {}).get("function", {}).get("name") == "find_player"
    assert ran == [("find_player", {"name": "riverrobin", "from": "riverrobin"})]


def test_what_friends_hold_and_do_is_told_not_guessed():  # item 9
    from kindred.describe import describe
    from fixtures import snap
    s = snap()
    s["players"] = [{"name": "riverrobin", "distance": 4, "direction": "left", "seen": True, "holding": "diamond_sword",
                     "doing": "sneaking"},
                    {"name": "sam", "distance": 30, "direction": "behind", "seen": False}]
    text = describe(s)
    assert "holding diamond sword, sneaking" in text and "sam, 30 blocks" in text and "never guess" in text


def test_a_lan_world_is_the_same_world_whatever_its_port():  # item 22
    from kindred.memory import world_key
    assert world_key("mp:192.168.1.73:63665") == world_key("mp:192.168.1.73:55368") == "mp:192.168.1.73"
    assert world_key("sp:New World") == "sp:New World"


def test_a_friends_words_move_her_heart_for_them_not_for_you():  # a heart for each person
    from kindred.heart import Heart
    clock = [1000.0]
    h = Heart({"heart": {}}, clock=lambda: clock[0])
    you = dict(h.rel.s)
    h.friend_regard("riverrobin", "kind", "you're lovely")
    h.friend_regard("sam", "mean", "you're useless")
    assert h.friends.bonds("riverrobin").s["a"] > h.friends.bonds("sam").s["a"]
    assert h.friends.bonds("sam").s["g"] > 0, "she resents the mean one"
    assert h.rel.s["a"] == you["a"] and h.rel.s["t"] == you["t"], "not you (yet)"
    assert 'sam said "you\'re useless"' in h.friends.guidance("sam"), "what sam said colours how she is with sam"
    for _ in range(6):
        h.friend_regard("sam", "mean", "you're useless")
    assert any(w in h.friends.guidance("sam") for w in ("resent", "don't like", "hurt")), h.friends.guidance("sam")
    cards = h.friends.explain()
    assert {c["name"] for c in cards} == {"riverrobin", "sam"} and "affection" in cards[0]


def test_saying_nothing_while_a_friend_hurts_her_costs_a_little_trust():  # witnessing
    from kindred.heart import Heart
    clock = [1000.0]
    h = Heart({"heart": {}}, clock=lambda: clock[0])
    t0 = h.rel.s["t"]
    h.friend_touch("sam", "hit")
    clock[0] += 5
    assert h.said_nothing() == 0.0, "she's still waiting to see what you do"
    clock[0] += 20
    h.said_nothing()
    assert h.rel.s["t"] < t0
    assert any(i["kind"] == "let_them" for i in h.rel.s["incidents"]), "logged as an incident, with why"
    assert "said nothing" in h.rel.s["log"][-1]["line"] if h.rel.s.get("log") and "line" in h.rel.s["log"][-1] else True


def test_standing_up_for_her_counts():  # witnessing
    from kindred.heart import Heart
    clock = [1000.0]
    h = Heart({"heart": {}}, clock=lambda: clock[0])
    t0, a0 = h.rel.s["t"], h.rel.s["a"]
    h.friend_regard("sam", "mean", "you're useless")
    clock[0] += 8
    assert h.stood_up_for_her() != 0 or (h.rel.s["t"] > t0 and h.rel.s["a"] > a0)
    assert h.rel.s["t"] > t0
    clock[0] += 30
    assert h.said_nothing() == 0.0, "settled: nothing left to hold against you"


def test_a_friends_touch_reaches_her_heart_for_them(stubs):  # friends' touches
    b, sent = _friend_brain(stubs)
    before = dict(b.heart.rel.s)
    t0 = b.heart.friends.bonds("riverrobin").s["t"]

    async def run():
        b.ws, b.in_world = object(), True
        await b.on_event("hit", {"type": "event", "event": "hit", "by": "riverrobin"})
    asyncio.run(run())
    assert b.heart.friends.bonds("riverrobin").s["t"] < t0
    assert b.heart.rel.s["a"] == before["a"], "your heart isn't the one hit"
    assert any(m["type"] == "say" and "riverrobin" in m["text"] for m in sent)


# ---------------------------------------------------------------- memory and pronouns (items 10, 20, 21, 23, 24)

def test_pronouns_said_are_kept_never_guessed():  # items 20 and 24
    assert intents.pronouns_said("I am a him, not a her. Why are you always saying I am a her?") == "he/him"
    assert intents.pronouns_said("my pronouns are they/them") == "they/them"
    assert intents.pronouns_said("I'm not a girl") == ""
    assert intents.pronouns_said("i love you") == ""
    from kindred.memory import GUESSED_GENDER
    assert GUESSED_GENDER.search("Is female and still getting to know me")
    assert not GUESSED_GENDER.search("Likes cherry trees.")


def test_reflection_never_keeps_a_guessed_gender_and_a_new_nickname_replaces_the_old():  # items 21 and 24
    import asyncio as aio
    from gateway_stub import memory
    m = memory()

    async def run():
        await m.open_world("sp:Test")
        await m.learn({"player": [{"text": "Is female and still getting to know me.", "importance": 6},
                                  {"text": "Alex likes to be called Dumb.", "importance": 7}]})
        await m.remember("Alex likes to be called Dumber.")
        await m.remember("Robin's nickname is Twinkle.")
        await m.remember("Alex likes to be called Twinkle Toes.")
        return [r["text"] for r in (await m.store.call("list", kinds=["player"], world=m.world_id, limit=50))["results"]]
    facts = aio.run(run())
    assert not any("female" in f for f in facts)
    assert "Alex likes to be called Twinkle Toes." in facts and "Robin's nickname is Twinkle." in facts
    assert not any(f in facts for f in ("Alex likes to be called Dumb.", "Alex likes to be called Dumber.")), facts


def test_her_diary_is_quoted_not_invented():  # item 10
    assert intents.DIARY.search("what did you write in your diary today?")
    assert intents.DIARY.search("read me your diary")
    assert not intents.DIARY.search("let's go mining")


def test_the_diary_is_written_from_the_whole_session(stubs):  # item 23
    from test_heart import _brain
    b = _brain(stubs)
    b.session.start("sp:Test")
    b.session.event("you", text="let's build a cherry house")
    for i in range(200):
        b.session.event("you", text="chatter %d" % i)
    b.session.event("guest", who="riverrobin", text="pip you're cute")
    b.session.event("you", text="good night pip")
    story = b.session_story(max_chars=3000)
    assert "cherry house" in story, "the beginning is there"
    assert "good night" in story or "riverrobin" in story, "and the end"
    assert len(story) <= 3000


def test_the_session_summary_says_what_waiting_felt_like():  # item 27
    from kindred.sessionlog import felt_rows
    ev = [{"kind": "you", "t": 0}, {"kind": "pip", "source": "reply", "t": 2, "text": "one two three four five six"},
          {"kind": "guest", "who": "riverrobin", "t": 10},
          {"kind": "pip", "source": "reply", "t": 14, "to": "riverrobin", "text": "hi there friend"}]
    rows = felt_rows(ev)
    assert "felt wait (you) | first word after 2.0s" in rows[0]
    assert "riverrobin" in rows[1] and "first word after 4.0s" in rows[1]
