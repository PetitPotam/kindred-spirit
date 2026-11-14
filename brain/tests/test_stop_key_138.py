"""#138: the stop key. The game stops her builds, jobs and leading itself; her brain hears it, hushes, and remembers."""
import asyncio

from test_end_to_end import make_cfg, stubs  # noqa: F401
from test_playtest_1113 import _brain


def test_the_stop_key_hushes_her_and_drops_what_she_was_saying(stubs):
    b = _brain(stubs, ["build"])
    sent, events = [], []

    async def send(msg):
        sent.append(msg)
    b.send = send
    b.session.event = lambda name, **kw: events.append(name)

    async def run():
        b.ws, b.in_world = object(), True
        b.speaking_until = b.clock() + 5
        b.unfinished = ("and the next block goes...", b.clock())
        await b.on_message({"type": "event", "event": "stop_all"})
    asyncio.run(run())
    assert {"type": "hush"} in sent and b.unfinished is None
    assert b.hush_at and "stopped_all" in events
    assert not [m for m in sent if m.get("type") == "say"], "an emergency stop: she doesn't chat about it"
