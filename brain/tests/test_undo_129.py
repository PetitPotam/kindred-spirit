"""#129: "undo that" puts her newest build or flattening back as it was."""
from kindred import intents, tools


def _first(text):
    return next((t for p, t in intents._hints if p.search(text)), None)


def test_undo_phrases_ask_for_the_build_tool():
    for said in ("undo that", "pip undo", "take it down please", "remove what you built",
                 "put the ground back the way it was"):
        assert _first(said.lower()) == "build", said


def test_other_phrases_are_not_undo():
    undo = next(p for p, t in intents._hints if "un-?do" in p.pattern)
    for said in ("put my block back", "give me back my stuff", "do a spin", "build a house"):
        assert not undo.search(said), said


def test_the_build_tool_knows_undo():
    build = next(t for t in tools.for_abilities(["build"]) if t["function"]["name"] == "build")
    assert "undo" in build["function"]["parameters"]["properties"]["shape"]["enum"]
    assert "undo" in build["function"]["description"]
