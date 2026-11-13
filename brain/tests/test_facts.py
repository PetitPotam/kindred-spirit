"""Facts about people (kindred/facts.py): the latest of each slot, one line, per person."""
import asyncio

from gateway_stub import memory as make_memory

from kindred import facts


def test_the_playtest_memories_become_one_line_per_person():
    rows = [{"text": "waterwalid (Walid) is the player's brother; he plays with us on LAN.", "created": 0},
            {"text": "The player's nickname is Dumb and waterwalid's nickname is Dumber.", "created": 1},
            {"text": "The player's nickname is Damb.", "created": 2},
            {"text": "Walid's (waterwalid) nickname is Dumber.", "created": 3},
            {"text": "TamBoudX's pronouns are he/him (they said so).", "created": 4},
            {"text": "Likes playful teasing and pranks on Walid.", "created": 5}]
    line = facts.people(rows, ["waterwalid"], "TamBoudX")
    assert line.startswith("People")
    assert "the player (TamBoudX): nickname Damb, he/him" in line, line
    assert "waterwalid: the player's brother, nickname Dumber" in line, line
    assert "Dumb," not in line, "an older nickname is gone"
    assert facts.consumed(rows[1]["text"]) and not facts.consumed(rows[5]["text"])


def test_her_context_says_the_latest_nickname_once():
    m = make_memory()

    async def run():
        await m.open_world("sp:Facts")
        await m.add("player", "The player's nickname is Dumb.", 7)
        await m.add("player", "Loves cherry wood.", 7)
        await m.add("player", "The player's nickname is Twinkle Dee.", 7)
        return await m.context({"playerName": "Tam"}, "what do you call me")
    text = asyncio.run(run())
    assert "nickname Twinkle Dee" in text and "Dumb" not in text
    assert "Loves cherry wood" in text
