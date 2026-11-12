from fixtures import snap

from kindred.mind import Mind, parse_reply, system_prompt


def cfg():
    return {"name": "Pip", "personality": "Loves redstone.", "ai": {"model": "m", "url": "http://x", "history_turns": 2}}


def test_mood_tag_is_split_off():
    assert parse_reply("[curious] Ooh, a cave!") == ("Ooh, a cave!", "curious", None)
    assert parse_reply("No tag here.") == ("No tag here.", None, None)
    assert parse_reply("[curious] Let me listen. (what='iron farm')")[0] == "Let me listen."
    assert parse_reply("[happy] Okay! listen_more(what='next') Here we go.")[0] == "Okay! Here we go."
    assert parse_reply("[happy] I love sunsets (and sunrises).")[0] == "I love sunsets (and sunrises).", "not real words"
    assert parse_reply("[grumpy] Hmph.") == ("Hmph.", None, None)
    assert parse_reply("[happy] **Yay** [excited] twice") == ("Yay twice", "happy", None)


def test_gesture_tag_is_split_off():
    assert parse_reply("[excited] {hop} Diamonds!") == ("Diamonds!", "excited", "hop")
    assert parse_reply("[happy] {moonwalk} Hi") == ("Hi", "happy", None)
    assert parse_reply("[happy] Hi {spin} there") == ("Hi there", "happy", None)


def test_prompt_has_name_rules_and_personality():
    p = system_prompt("Pip", "Loves redstone.")
    assert "You are Pip" in p and "[scared]" in p and "Loves redstone." in p


def test_messages_carry_game_state_and_merge_roles():
    m = Mind(cfg())
    m.note_said("Creeper behind you!", "scared")
    msgs = m.build_messages(snap(), "what's around me?")
    assert msgs[0]["role"] == "system" and "biome plains" not in msgs[0]["content"]
    assert [x["role"] for x in msgs] == ["system", "user", "assistant", "user"]
    # the current game state travels with the newest message, so it wins over older lines
    assert "biome plains" in msgs[-1]["content"] and msgs[-1]["content"].endswith("what's around me?")
    assert "biome plains" not in msgs[2]["content"]


def test_history_is_capped():
    m = Mind(cfg())
    for i in range(10):
        m.remember("user", "q%d" % i)
        m.remember("assistant", "a%d" % i)
    assert len(m.history) == 4 and m.history[-1]["content"] == "a9"


def test_streamed_tool_calls_and_short_sentences():
    from kindred.mind import Streamer, fix_calls, join_part
    # Gemini may repeat the whole name in a later piece: "rememberremember" broke a call
    assert join_part(join_part("", "remember"), "remember") == "remember"
    assert join_part(join_part("", '{"fact": "a'), '"}') == '{"fact": "a"}'
    tools = [{"function": {"name": "remember"}}, {"function": {"name": "guide"}}]
    assert fix_calls([{"function": {"name": "rememberremember"}}], tools)[0]["function"]["name"] == "remember"
    assert fix_calls([{"function": {"name": "nonsense"}}], tools) == []
    got = []
    st = Streamer(lambda text, *a: got.append(text))
    st.feed("[happy][kind] Our base! I like the sound of that. It's very... official. Right here in the flowers.", final=True)
    assert got[0] == "Our base! I like the sound of that.", got
    assert "It's very... official." in got[1], "'...' before a small letter isn't the end of a sentence"


def test_two_tools_at_once_stay_two_calls():
    import json as _json
    from kindred import mind as M
    chunks = [{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "a", "function": {"name": "remember", "arguments": '{"fact": "Name is Alex."}'}}]}}]},
              {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "b", "function": {"name": "guide", "arguments": "{}"}}]}}]}]

    def fake_stream(url, body, key, timeout, kind, emit):
        for c in chunks:
            emit(c)
        return {}
    import asyncio
    old = M.stream_json
    M.stream_json = fake_stream
    try:
        m = M.Mind({"name": "Pip", "ai": {"model": ""}, "gateway": {"url": "http://x/v1", "key": ""}})
        msg = asyncio.run(m._stream({"messages": []}, "reply", M.Streamer(lambda *a: None)))
    finally:
        M.stream_json = old
    names = [c["function"]["name"] for c in msg["tool_calls"]]
    assert names == ["remember", "guide"], names
    assert _json.loads(msg["tool_calls"][0]["function"]["arguments"])["fact"] == "Name is Alex."
