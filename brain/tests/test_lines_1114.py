"""#177 (session 2026-11-14): her "I'm starting" line became "Leave it!", which sounds like a refusal."""
from kindred import instinct, talker


def test_a_yes_line_never_sounds_like_no():
    lines = instinct.clean({"on_it": ["Leave it!", "Leave it to me!", "On it!", "No problem!", "Nope!", "Not now.",
                                      "Got it!", "Stop right there!"],
                            "follow_ok": ["Never!", "Right behind you!"]})
    assert lines["on_it"] == ["Leave it to me!", "On it!", "No problem!", "Got it!"]
    assert lines["follow_ok"] == ["Right behind you!"]


def test_other_moments_keep_their_lines():
    lines = instinct.clean({"thanks_ok": ["Hehe!"]})
    assert lines["thanks_ok"] == ["Hehe!"]


def test_her_saved_leave_it_is_dropped_when_loaded():
    i = instinct.Instinct()
    i.load({"lines": {"on_it": ["Leave it!"]}})
    assert not i.lines.get("on_it")


def test_the_builtin_yes_lines_all_pass():
    assert instinct.clean({"on_it": talker.LINES["on_it"]})["on_it"] == talker.LINES["on_it"]
