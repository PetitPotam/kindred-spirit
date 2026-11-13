"""In-game commands: /kindred memory, worlds, import, forget, reset (answered by the brain in chat)."""
import asyncio

from fixtures import snap
from test_heart import _brain
from test_end_to_end import stubs  # noqa: F401  (a fixture)


def test_memory_import_forget_and_reset_in_game(stubs):
    b = _brain(stubs)
    sent = []

    async def send(msg):
        sent.append(msg)
    b.send = send

    async def run():
        m = b.memory
        m.store.strict = m.per_world = True
        await m.open_world("sp:Old")
        await m.remember("The player's name is Alex.")
        await m.store.call("doc", key="world:sp:Old:heart", value={"bond": 70, "discovered": ["guide"], "asked": {}})
        await m.open_world("sp:New")
        await b.heart.load()
        assert "Old (1 memories)" in await b.admin_text("worlds", "")
        out = await b.admin_text("import", "old")
        assert "remembers 1 things from Old" in out and "Bond now 70" in out and "guide" in out
        assert "Alex" in await m.context(snap(), "what's my name?")
        assert "Forgot 1" in await b.admin_text("forget", "Alex")
        await m.remember("Likes cherry wood.")
        await m.spot("bed", "your bed", 10, 64, -3)  # a place she noticed herself (#121)
        assert await m.spots()
        assert "confirm" in await b.admin_text("reset", "")
        assert "brand-new" in await b.admin_text("reset", "confirm")
        assert b.heart.bond == 30 and "cherry" not in await m.context(snap(), "cherry")
        assert not await m.spots(), "a brand-new companion doesn't know your bed, builds or deaths (#121)"
        assert "Alex" in (await m.store.call("list", kinds=["player"], world="sp:Old"))["results"][0]["text"], \
            "only this world's companion was reset"
    asyncio.run(run())
