"""What the world remembers (the knowledge base), as Pip uses it: stand-in gateway, no network."""
import asyncio

from fixtures import snap
from test_end_to_end import stubs  # noqa: F401  (a fixture)
from test_heart import _brain

from kindred.knowledge import is_world_question

PISTON = {"title": "Piston", "section": "Obtaining > Crafting", "text": "Planks, cobblestone, an iron ingot and redstone.",
          "url": "https://minecraft.wiki/w/Piston"}
GOLEM = {"title": "Tutorials/Iron golem farming", "section": "Basics",
         "text": "Villagers that sleep and work together summon an iron golem when a zombie scares them."}


def test_which_questions_are_about_the_world():
    assert is_world_question("how do I build an iron farm?")
    assert is_world_question("do you know how to tame a wolf")
    assert not is_world_question("how are you?") and not is_world_question("what do you like?")


def test_she_answers_from_what_the_world_remembers(stubs):
    stubs.kb = [{"covered": True, "best": 0.86, "results": [PISTON]}]
    b = _brain(stubs)
    b.send = lambda msg: asyncio.sleep(0)
    b.cfg["voice"]["enabled"] = False

    async def run():
        b.ws, b.in_world, b.snapshot = object(), True, snap()
        await b.answer("how do I make a piston?")
    asyncio.run(run())
    sent = stubs.ai_requests[-1]["messages"][-1]["content"]
    assert "[What the world remembers]" in sent and "iron ingot" in sent
    assert "minecraft.wiki" not in sent, "never where it comes from: to her it's what her world remembers"


def test_she_listens_to_the_world_then_comes_back(stubs):
    stubs.kb = [{"covered": False, "best": 0.2, "results": []},            # she doesn't know
                {"added": 3, "seconds": 2.9},                               # learning (in the background)
                {"covered": True, "best": 0.8, "results": [GOLEM]}]        # now the world remembers
    stubs.ai_script = [{"role": "assistant", "content": "[curious][neutral] Hmm, the old stones remember... let me listen."},
                       {"role": "assistant", "content": "[excited][neutral] {hop} The stones told me! Villagers..."}]
    b = _brain(stubs)
    b.quiet_gap = 0
    sent = []

    async def send(msg):
        sent.append(msg)
    b.send = send
    b.cfg["voice"]["enabled"] = False

    async def run():
        b.ws, b.in_world, b.snapshot = object(), True, snap()
        b.listen_to_the_world.__func__  # (exists)
        await b.answer("how do I build an iron farm?")
        for _ in range(100):
            if not b.listening:
                break
            await asyncio.sleep(0.05)
    asyncio.run(run())
    first = stubs.ai_requests[0]["messages"][-1]["content"]
    assert "listen to what the world remembers" in first and "Don't guess" in first
    assert [op for op, _ in stubs.kb_requests] == ["search", "learn", "search"]
    back = stubs.ai_requests[-1]["messages"][-1]["content"]
    assert "zombie scares them" in back and "what the stones or the wind told you" in back
    assert any(m.get("look") == "around" for m in sent if m["type"] == "act"), "she looks around, listening"


def test_a_build_question_gets_the_whole_guide_and_she_can_listen_for_more(stubs):
    old = {"id": 7, "title": "Tutorial:Door-based iron golem farming", "section": "Tower", "text": "doors...", "outdated": True}
    new = {"id": 9, "title": "Tutorial:Iron golem farming", "section": "Simple farm", "text": "beds..."}
    stubs.kb = [{"covered": True, "best": 0.8, "results": [old, new]},
                {"title": "Tutorial:Iron golem farming", "section": "Simple farm", "text": "1. Dig a pit. 2. Add beds.",
                 "part": 1, "parts": 3, "more": True, "next_start": 2, "next_section": "Collection",
                 "outline": ["Basics", "Simple farm", "Collection"]},
                {"title": "Tutorial:Iron golem farming", "section": "Simple farm", "text": "3. Add a zombie. 4. Lava.",
                 "part": 3, "parts": 3, "more": False, "next_start": None, "next_section": "Collection",
                 "outline": ["Basics", "Simple farm", "Collection"]}]
    b = _brain(stubs)
    b.send = lambda msg: asyncio.sleep(0)
    b.cfg["voice"]["enabled"] = False

    async def run():
        b.ws, b.in_world, b.snapshot = object(), True, snap()
        await b.answer("how do I build an iron golem farm?")
        return await b.run_tool("listen_more", {"what": "next"})
    more = asyncio.run(run())
    sent = stubs.ai_requests[0]["messages"][-1]["content"]
    assert "Dig a pit" in sent and "listen more" in sent and "doors" not in sent, "the current guide, whole, in order"
    section_calls = [body for op, body in stubs.kb_requests if op == "section"]
    assert section_calls[0]["chunk_id"] == 9, "the current guide, not the outdated one"
    assert section_calls[1]["start"] == 2 and "Add a zombie" in more["world_remembers"]
