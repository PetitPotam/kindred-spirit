"""Fixes from the play session of 2026-11-14 (session log 20261114-0303, Minecraft 26.3); each test names its issue."""
import asyncio

from test_end_to_end import make_cfg, stubs  # noqa: F401

from kindred import server


def _brain(stubs, abilities=("blueprint", "build", "job", "guide", "protect")):
    from test_heart import _brain as make
    b = make(stubs)
    b.abilities = list(abilities)
    b.offered = None
    sent = []

    async def send(msg):
        sent.append(msg)
    b.send = send
    b.sent = sent
    return b


def test_she_searches_the_blueprints_of_the_game_she_is_in(stubs, tmp_path, monkeypatch):  # #175
    """The 26.3 profile's folder came empty while her catalogue read the 1.21.1 profile's: she offered houses the
    game couldn't build. The game's hello now names its folders, and she searches those."""
    b = _brain(stubs)
    seen = []
    monkeypatch.setattr(server, "find_blueprints", lambda query, dirs=None, limit=6: (seen.append(dirs), {"ok": True, "matches": []})[1])
    game = [str(tmp_path / "minecraft-kindred-26.3" / "config" / "kindredspirit" / "blueprints")]

    async def run():
        await b.on_message({"type": "hello", "mod": "0.3.0", "minecraft": "26.3", "blueprints": game})
        await b._run_tool("find_blueprint", {"query": "a taiga house"})
    asyncio.run(run())
    assert b.blueprint_dirs == game and seen and seen[-1] == game


def test_an_old_mod_without_folders_keeps_the_usual_ones(stubs):  # #175
    b = _brain(stubs)
    asyncio.run(b.on_message({"type": "hello", "mod": "0.2.0", "minecraft": "1.21.1"}))
    assert b.blueprint_dirs is None  # (find_blueprints then uses BLUEPRINT_DIRS)
    asyncio.run(b.on_message({"type": "hello", "blueprints": "not a list"}))
    assert b.blueprint_dirs is None
