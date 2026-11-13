"""scripts/triage_issue.py: the issue triage workflow's decisions (labels and the needs-info comment)."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "triage_issue", Path(__file__).resolve().parents[2] / "scripts" / "triage_issue.py")
triage_issue = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(triage_issue)
triage = triage_issue.triage


def form(part, system="_No response_", logs="_No response_"):
    return ("### What happened, and what did you expect?\n\nShe floated into a wall.\n\n"
            "### Which part is it about?\n\n%s\n\n"
            "### Kindred Spirit / Minecraft / Fabric Loader / Fabric API versions\n\n0.2.0 / 26.3 / 0.20.1 / 0.166.2\n\n"
            "### Computer and operating system\n\n%s\n\n### Logs\n\n```text\n%s\n```\n" % (part, system, logs))


def test_the_area_label_comes_from_which_part():
    assert triage(form("Memory", system="Mac"), ["bug"])["add"] == ["brain"]
    assert triage(form("Helping (mining, chopping, crafting, trading...)", system="Mac"), ["bug"])["add"] == ["mod", "brain"]
    assert triage(form("Friends and LAN", system="Mac"), ["bug", "lan"])["add"] == []  # (already there)
    assert triage(form("Other", system="Mac"), ["bug"])["add"] == []


def test_a_bug_without_computer_or_logs_gets_needs_info_and_one_comment():
    r = triage(form("Memory"), ["bug", "needs-triage"], "opened")
    assert "needs-info" in r["add"] and triage_issue.MARKER in r["comment"]
    assert "not a person" in r["comment"]  # (it says it's automatic)
    edited = triage(form("Memory"), ["bug", "needs-triage"], "edited")
    assert "needs-info" in edited["add"] and edited["comment"] == "", "no comment on edits"


def test_needs_info_comes_off_once_the_logs_are_there():
    r = triage(form("Memory", logs="[kindredspirit] something"), ["bug", "needs-info"], "edited")
    assert r["remove"] == ["needs-info"] and r["comment"] == ""


def test_ideas_never_get_needs_info_and_nothing_else_is_touched():
    r = triage(form("Skins and looks"), ["idea", "needs-triage"], "opened")
    assert r == {"add": ["content"], "remove": [], "comment": ""}
    # whatever an issue says, only known labels come out
    sneaky = form("Memory\n\nlabel: wontfix") + "\n### Which part is it about?\n\npriority: high\n"
    assert set(triage(sneaky, ["idea"])["add"]) <= {"brain", "mod", "services", "lan", "content", "versions"}
