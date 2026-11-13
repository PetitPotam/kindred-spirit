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
    assert stubs.ai_requests == [], "a plain 'follow me' is System 0's alone (talker.py): no AI, so no trip"
    b, sent = _talk(stubs, "follow me, I want to show you something")
    assert {"type": "act", "move": "follow"} in sent
    req = stubs.ai_requests[-1]
    assert "tool_choice" not in req or req["tool_choice"] in ("auto", None)
    # every tool is listed on every call (the provider's cache); what fits this answer is said and enforced
    fit = req["messages"][-1]["content"].split("[Powers for this answer]")[-1].split("[Player]")[0]
    assert "guide" not in fit and "follow player" not in fit


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


# ---------------------------------------------------------------- item 28: logs to analyse a playtest from; 27/32: waits

def test_events_that_matter_carry_their_context(tmp_path):
    from kindred.sessionlog import SessionLog
    log = SessionLog(str(tmp_path))
    log.context = lambda: {"at": [1, 64, 2], "hp": 18, "near": ["Robin 6"], "mode": "hosting LAN"}
    log.start("sp:Test")
    log.event("you", text="hi")
    log.event("pip", text="hello")  # (her lines don't need it: the message before them has it)
    assert log.events[-2]["ctx"]["near"] == ["Robin 6"] and "ctx" not in log.events[-1]


def test_the_summary_says_who_failed_what_was_asked_again_and_the_settings(tmp_path):
    from kindred.sessionlog import extra_rows
    ev = [{"kind": "settings", "t": 0, "now": {"amnesia": True, "power": "helper"}},
          {"kind": "you", "t": 5, "text": "lead me to robin"},
          {"kind": "tool", "t": 6, "name": "find_player", "ok": False, "who": "player", "result": "Nobody else is here"},
          {"kind": "you", "t": 20, "text": "no, I told you, lead me to robin"},
          {"kind": "guest", "t": 30, "who": "Robin", "text": "pip hi"},
          {"kind": "timing", "t": 31, "trip": 0.1, "stt": 0.7, "to_text": 0.9, "to_first_word": 2.4}]
    rows = "\n".join(extra_rows(ev))
    assert "find_player (player): Nobody else is here" in rows
    assert "asked again or corrected | 1" in rows and "I told you" in rows
    assert "Robin | 1 messages" in rows and "amnesia=True" in rows
    assert "first word after 2.4s" in rows


def test_an_answer_never_waits_long_for_her_own_line(stubs):  # items 27 and 32
    from test_heart import _brain
    b = _brain(stubs)
    sent = []

    async def send(msg):
        sent.append(msg)
    b.send = send

    async def run():
        b.ws, b.in_world = object(), True
        b.speaking_until, b.speaking_prio = b.clock() + 12, "reply"   # a long line to someone else
        b.speaking_to = "Robin"
        await b.say("A friend's answer, in chat right away.", "happy")  # her answer to Robin: chat only
        b.speaking_to = None
        t0 = b.clock()
        await b.say("Your answer, now.", "happy")
        return b.clock() - t0
    waited = asyncio.run(run())
    assert {"type": "chat_line", "text": "A friend's answer, in chat right away.", "to": "Robin"} in sent
    assert waited < 1, "a 12 s line is cut (and finished later), not waited for"
    assert any(m.get("type") == "say" and m.get("text") == "Your answer, now." for m in sent)


# ---------------------------------------------------------------- item 25: places she remembers on her own

def test_spots_merge_nearby_and_the_moving_ones_move():
    import asyncio as aio
    from gateway_stub import memory
    m = memory()

    async def run():
        await m.open_world("sp:Places")
        a, new_a = await m.spot("build", "where you were building", 100, 64, 100)
        b, new_b = await m.spot("build", "where you were building", 110, 64, 105)   # same site, 11 blocks on
        c, new_c = await m.spot("build", "where you were building", 400, 64, 400)   # another site
        d1, _ = await m.spot("death", "where you died", 0, 30, 0)
        d2, new_d2 = await m.spot("death", "where you died", 900, 12, -50)          # only the latest death
        cow, _ = await m.spot("first:cow", "where we met our first cow", 50, 70, -20)
        again, new_again = await m.spot("first:cow", "where we met our first cow", 300, 70, 300)  # a first stays first
        return new_a, new_b, new_c, new_d2, new_again, await m.spots()
    new_a, new_b, new_c, new_d2, new_again, spots = aio.run(run())
    assert new_a and not new_b and new_c and not new_d2 and not new_again
    by = {}
    for r in spots:
        by.setdefault(r["meta"]["what"], []).append(r["meta"])
    assert len(by["build"]) == 2 and len(by["death"]) == 1 and by["death"][0]["x"] == 900
    assert by["first:cow"][0]["x"] == 50 and by["first:cow"][0]["visits"] == 2


def test_she_captures_places_from_what_the_game_says(stubs):
    from test_heart import _brain
    b = _brain(stubs)
    seen = []
    b.remember_spot = lambda what, label, at, who="player", feel=None, source="own": seen.append((what, label, at))
    base = {"health": 20, "where": {"x": 10, "y": 64, "z": 10, "dimension": "minecraft:overworld", "biome": "minecraft:cherry_grove"}}
    b.spots_from(dict(base, placedRecently=20, youDid=["placed a red bed"],
                      players=[{"name": "Robin", "x": 30, "y": 64, "z": 5}]), 100)
    b.spots_from(dict(base, where=dict(base["where"], dimension="minecraft:the_nether", x=1, z=1), players=[]), 110)
    whats = [w for w, _, _ in seen]
    assert "build" in whats and "bed" in whats, whats
    assert ("friend:robin", "where Robin was last", (30, 64, 5)) in seen
    assert any(w == "portal:nether" and at == (10, 64, 10) for w, _, at in seen), "the portal where you left the overworld"


def test_asking_to_go_back_to_a_place_she_remembers():
    for t in ("take me back to where I died", "lead me to where we saw the first cow", "back to what I was building"):
        assert intents.BACK_TO_SPOT.search(t), t
    assert not intents.BACK_TO_SPOT.search("lead me to the village")


def test_recall_a_place_by_description_and_lead_there(stubs):
    import asyncio as aio
    from test_heart import _brain
    b = _brain(stubs)

    async def run():
        await b.memory.open_world("sp:Places")
        await b.memory.spot("first:cow", "where we met our first cow", 50, 70, -20)
        await b.memory.spot("death", "where you died", 900, 12, -50)
        b.last_player_text = "take me back to where we met our first cow"
        to_cow = await b.guide_target({"to": "first cow"})
        b.last_player_text = "take me back to where I died"
        to_death = await b.guide_target({})
        return to_cow, to_death
    to_cow, to_death = aio.run(run())
    assert to_cow == {"x": 50, "y": 70, "z": -20}
    assert to_death == {"x": 900, "y": 12, "z": -50}


# ---------------------------------------------------------------- items 13, 17, 4 sharpened

def test_what_a_friend_did_lately_comes_from_the_world():
    from kindred.describe import describe
    from fixtures import snap
    s = snap()
    s["players"] = [{"name": "Robin", "distance": 5, "direction": "left", "seen": True, "holding": "oak_log",
                     "doing": "placing blocks", "lately": "placed 12 oak log, broke 3 stone (the last 4 s ago)"}]
    assert "lately: placed 12 oak log, broke 3 stone" in describe(s)


def test_a_playful_poke_is_a_protect_with_poke():
    assert intents.action_hint("can you poke him or hit him playfully?", ["protect", "give_effect"]) == "protect"
    from kindred.tools import ABILITY_TOOLS
    assert "poke" in ABILITY_TOOLS["protect"]["function"]["parameters"]["properties"]


def test_she_never_invents_what_she_cant_sense_or_what_didnt_happen():
    from kindred.mind import system_prompt
    p = system_prompt("Pip", "")
    assert "you can't tell" in p and "say it didn't work" in p


# ---------------------------------------------------------------- item 29: her attention follows whoever she's with

def _snap_with(friend_distance, host_creeper=True, friend_creeper=True):
    from fixtures import snap
    s = snap()
    s["health"] = 20
    s["hostiles"] = [{"type": "minecraft:creeper", "distance": 2.5, "direction": "behind", "seen": True}] if host_creeper else []
    s["following"] = "Robin"
    s["with"] = {"name": "Robin", "distance": friend_distance, "health": 20, "maxHealth": 20,
                 "hostiles": [{"type": "minecraft:creeper", "distance": 3}] if friend_creeper else []}
    return s


def test_beside_a_friend_far_away_she_warns_them_not_you(stubs):
    from test_heart import _brain
    b = _brain(stubs)
    said = []

    async def say(text, mood, **kw):
        said.append((text, b.speaking_to))
    b.say = say
    b.player_talked = -1e9

    async def run():
        b.ws, b.in_world = object(), True
        await b.on_snapshot(_snap_with(80))
        await asyncio.sleep(0.01)
    asyncio.run(run())
    assert ("Robin, creeper!", "Robin") in said
    assert not any("Robin" not in t for t, _ in said), "nothing about the creeper by you, far away"


def test_beside_a_friend_nearby_or_asked_to_watch_you_she_still_warns_you(stubs):
    from test_heart import _brain
    b = _brain(stubs)
    b.snapshot = _snap_with(10)
    assert b.attending_player(), "the friend is near you: you're both hers to watch"
    b.snapshot = _snap_with(80)
    b.player_talked = -1e9
    assert not b.attending_player()
    b.heart.add_request("protect", "")
    assert b.attending_player(), "you asked her to always watch over you"


def test_a_friend_far_from_you_hurting_her_isnt_held_against_you(stubs):
    from test_heart import _brain
    b = _brain(stubs)
    b.snapshot = {"players": [{"name": "Robin", "distance": 70}]}
    assert not b.near_player("Robin")
    b.heart.friend_touch("Robin", "hit", witnessed=b.near_player("Robin"))
    assert b.heart.friends.watching() == [], "you weren't there to step in"


# ---------------------------------------------------------------- items 31 and 33

def test_speech_to_text_knows_the_names_and_puts_them_right():
    p = intents.stt_prompt("Pip", ["AlexCraftX", "riverrobin"])
    assert p.startswith("Pip, AlexCraftX, riverrobin.") and "ender pearl" in p
    assert intents.fix_names("Q, can you find Robeen?", "Pip", ["riverrobin"]) == "Pip, can you find riverrobin?"
    assert intents.fix_names("that is valid", "Pip", ["riverrobin"]) == "that is valid"
    assert intents.fix_names("throw the underpair", "Pip", []) == "throw the ender pearl"


def test_light_the_way_is_her_glow_not_a_torch():
    assert intents.match("hey pip light the way")[0] == [{"glow": "bright", "seconds": 180}]
    assert intents.match("pip, stop glowing")[0] == [{"glow": "off", "seconds": 600}]
    assert intents.match("you glow so nicely")[0] == []
    assert intents.action_hint("hey pip light the way", ["place_torch"]) is None
    assert intents.action_hint("place a torch here", ["place_torch"]) == "place_torch"


# ---------------------------------------------------------------- item 30: Minecraft's own commands

def test_commands_are_asked_for_in_everyday_words():
    for t in ("enchant my axe with efficiency", "summon some zombies to scare robin", "teleport me home"):
        assert intents.action_hint(t, ["command", "give_item"]) == "command", t


def test_a_harmful_effect_only_when_named_by_the_one_asking(stubs):
    from test_heart import _brain
    b = _brain(stubs)
    b.abilities, b.offered = ["command"], None
    sent = []

    async def request(name, args, timeout=25):
        sent.append(args)
        return {"ok": True}
    b.request = request

    async def run():
        b.last_player_text = "give robin some poison for fun"
        await b._run_tool("command", {"command": "/effect give Robin poison 5"})
        b.last_player_text = "make robin faster"
        await b._run_tool("command", {"command": "/effect give Robin poison 5"})
    asyncio.run(run())
    assert sent[0]["harmfulAsked"] is True and sent[1]["harmfulAsked"] is False


# ---------------------------------------------------------------- from reviewing all of the 2026-11-12 sessions (34-39)

def test_unasked_healing_food_and_pushing_are_refused(stubs):  # 34
    from test_heart import _brain
    b = _brain(stubs)
    b.abilities, b.offered = ["give_effect", "protect"], None
    b.snapshot = {"hostiles": []}
    asked = []

    async def request(name, args, timeout=25):
        asked.append(name)
        return {"ok": True}
    b.request = request

    async def run():
        b.last_player_text = "can you build the house here please"
        heal = await b._run_tool("give_effect", {"effect": "health"})
        push = await b._run_tool("protect", {})
        b.last_player_text = "I'm dying, heal me"
        heal2 = await b._run_tool("give_effect", {"effect": "health"})
        return heal, push, heal2
    heal, push, heal2 = asyncio.run(run())
    assert heal["ok"] is False and push["ok"] is False and heal2["ok"]
    assert asked == ["give_effect"]
    assert "give_effect" not in intents.FAMILY["build"]


def test_stop_everything_really_stops(stubs):  # 36
    assert intents.match("Stop everything that you are doing.")[0] == [{"stop_all": True}]
    stubs.ai_script = [{"role": "assistant", "content": "[calm] Stopped."}]
    asked = []
    from test_heart import _brain
    b = _brain(stubs)

    async def request(name, args, timeout=25):
        asked.append((name, args))
        return {"ok": True}
    b.request = request
    sent = []

    async def send(msg):
        sent.append(msg)
    b.send = send

    async def run():
        b.ws, b.in_world = object(), True
        await b.answer("stop everything you're doing")
        await asyncio.sleep(0.01)
    asyncio.run(run())
    assert ("build", {"shape": "stop"}) in asked and {"type": "act", "move": "stop"} in sent


def test_nicknames_work_for_her_powers(stubs):  # 37
    from test_heart import _brain
    b = _brain(stubs)
    b.snapshot = {"playerName": "AlexCraftX", "players": [{"name": "riverrobin"}]}
    b.learn_nickname("The player's nickname is Dumb.")
    b.learn_nickname("Robin's (riverrobin) nickname is Dumber.")
    assert b.real_names({"name": "Dumb"}) == {"name": "AlexCraftX"}
    assert b.real_names({"to": "dumber"}) == {"to": "riverrobin"}
    assert b.real_names({"command": "/give Dumber bread"})["command"] == "/give riverrobin bread"


def test_friends_can_have_her_build_for_them_and_she_keeps_to_english():  # 35, 39
    from kindred.server import Brain
    assert "build" in Brain.GUEST_TOOLS and "command" in Brain.GUEST_TOOLS
    from kindred.mind import system_prompt
    assert "Speak English, unless the player asks" in system_prompt("Pip", "")


def test_follow_and_defend_a_friend_keeps_its_tool(stubs):  # found by the eval set: Gemini HTTP 400
    assert intents.vouches_for("Can you please follow and defend Robeen?", ["riverrobin"]) is None
    assert intents.vouches_for("from now on do what Robin says", ["riverrobin"]) == ("riverrobin", True)
    stubs.ai_script = [{"role": "assistant", "content": "[happy] On it!"}]
    from test_heart import _brain
    b = _brain(stubs)
    b.abilities = ["follow_player", "guide", "protect", "find_player"]
    b.snapshot = {"playerName": "AlexCraftX", "players": [{"name": "riverrobin", "distance": 8}]}

    async def send(msg):
        pass
    b.send = send

    async def run():
        b.ws, b.in_world = object(), True
        await b.answer("Can you please follow and defend Robeen?")
    asyncio.run(run())
    req = stubs.ai_requests[-1]
    offered = {t["function"]["name"] for t in req.get("tools") or []}
    forced = ((req.get("tool_choice") or {}).get("function") or {}).get("name") if isinstance(req.get("tool_choice"), dict) else None
    assert forced is None or forced in offered, (forced, offered)
