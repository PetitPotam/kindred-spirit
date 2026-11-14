"""#179 (session 2026-11-14): "cut them off" (the trees) made her push monsters; "show me what you built" failed."""
import asyncio

from test_end_to_end import make_cfg, stubs  # noqa: F401

from kindred import intents


def test_cut_them_off_means_chop_the_trees():
    first = next(t for p, t in intents._hints if p.search("cut them off"))
    assert first == "job", "a job of chopping, not pushing monsters away"
    assert next(t for p, t in intents._hints if p.search("chop those down")) == "job"


def test_show_me_what_you_built_is_understood():
    for said in ("show me what you built", "take me to what you made", "where's the house", "where did you build it"):
        assert intents.SHOW_BUILT.search(said), said
    assert not intents.SHOW_BUILT.search("show me the way to the village")


def test_she_leads_to_her_last_build(stubs):
    from test_heart import _brain as make
    b = make(stubs)
    b.abilities = ["blueprint", "guide"]

    async def request(name, args, timeout=25):
        return {"ok": True, "building": "cozy cottage for 4", "at": "-131 74 -92"}
    b.request = request

    async def run():
        await b._run_tool("blueprint", {"what": "cottage"})
        b.last_player_text = "show me what you built"
        return await b.guide_target({"to": "last"})
    target = asyncio.run(run())
    assert target == {"x": -131, "y": 74, "z": -92}
