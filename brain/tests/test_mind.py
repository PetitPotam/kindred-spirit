from fixtures import snap

from kindred.mind import Mind, parse_reply, system_prompt


def cfg():
    return {"name": "Pip", "personality": "Loves redstone.", "ai": {"model": "m", "url": "http://x", "history_turns": 2}}


def test_mood_tag_is_split_off():
    assert parse_reply("[curious] Ooh, a cave!") == ("Ooh, a cave!", "curious")
    assert parse_reply("No tag here.") == ("No tag here.", None)
    assert parse_reply("[grumpy] Hmph.") == ("Hmph.", None)
    assert parse_reply("[happy] **Yay** [excited] twice") == ("Yay twice", "happy")


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
