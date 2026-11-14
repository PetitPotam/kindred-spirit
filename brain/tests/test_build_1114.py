"""#178 (session 2026-11-14): asked for a shipwreck, a build with no shape became a 3-block pillar."""
import asyncio

from test_end_to_end import make_cfg, stubs  # noqa: F401


def _brain(stubs, abilities):
    from test_heart import _brain as make
    b = make(stubs)
    b.abilities = list(abilities)
    asked = []

    async def request(name, args, timeout=25):
        asked.append((name, dict(args)))
        return {"ok": True}
    b.request = request
    return b, asked


def test_a_build_with_a_blueprint_name_goes_to_the_blueprint_tool(stubs):
    b, asked = _brain(stubs, ["build", "blueprint"])
    asyncio.run(b._run_tool("build", {"what": "shipwreck_rightsideup_full"}))
    assert asked and asked[0][0] == "blueprint" and asked[0][1]["what"] == "shipwreck_rightsideup_full"


def test_a_build_with_nothing_asks_which_shape_and_builds_nothing(stubs):
    b, asked = _brain(stubs, ["build"])
    r = asyncio.run(b._run_tool("build", {}))
    assert r["ok"] is False and "which shape" in r["error"].lower() and not asked


def test_a_real_shape_still_builds(stubs):
    b, asked = _brain(stubs, ["build"])
    asyncio.run(b._run_tool("build", {"shape": "circle", "radius": 5, "block": "stone"}))
    assert asked and asked[0][0] == "build" and asked[0][1]["shape"] == "circle"
