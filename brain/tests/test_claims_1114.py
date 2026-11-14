"""#176 (session 2026-11-14): a build that failed is never said done."""
import asyncio

from test_end_to_end import make_cfg, stubs  # noqa: F401


def test_a_build_that_failed_is_never_said_done(stubs):  # #176
    """The builds failed, a lookup worked, and on her last try she said "Done! A dry ship": now a lookup proves
    nothing, and a claim on the last try becomes an honest sentence instead."""
    import json
    from kindred import mind as mind_mod, tools
    from kindred.mind import Mind
    from fixtures import snap

    def call(i, name, args):
        return {"role": "assistant", "content": "", "tool_calls": [
            {"id": "t%d" % i, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}
    stubs.ai_script = [
        call(1, "blueprint", {"what": "shipwreck_rightsideup_full"}),
        call(2, "find_blueprint", {"query": "shipwreck"}),
        call(3, "blueprint", {"what": "shipwreck_rightsideup_full"}),
        {"role": "assistant", "content": "[happy] Done! A dry ship for a dry forest."},
        {"role": "assistant", "content": "[calm] I couldn't build that one: I don't have it here."}]

    async def run_tool(name, args):
        if name == "blueprint":
            return {"ok": False, "error": "I don't have a blueprint for shipwreck_rightsideup_full."}
        return {"ok": True, "matches": [{"name": "shipwreck_rightsideup_full"}]}
    m = Mind(make_cfg(stubs.port))
    text, _, _ = asyncio.run(m.reply(snap(), "build it please", (),
                                     tools.for_abilities(["blueprint", "find_blueprint"]), run_tool))
    assert "done" not in text.lower() and "couldn't" in text
    assert "find_blueprint" in mind_mod.LOOKUPS
