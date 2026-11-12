"""The dashboard reads logs and settings: parsing, and that keys never show."""
import gateway_stub  # noqa: F401  (puts services/ on the path)
import dashboard


def test_prompt_parts_and_kinds():
    p = "[Game state right now]\nHealth 10/10\n\n[What you remember]\nHis name is Tam.\n\n[Player]\nhello"
    parts = dashboard.split_prompt(p)
    assert parts == {"Game state right now": "Health 10/10", "What you remember": "His name is Tam.", "Player": "hello"}
    assert dashboard.kind_of(p, parts) == "reply"
    own = "[Player]\n(The player just joined; greet them.)"
    assert dashboard.kind_of(own, dashboard.split_prompt(own)) == "own"
    assert dashboard.kind_of("Already known: ...", {}) == "reflect"
    assert dashboard.kind_of("Summary so far: ...", {}) == "fold"


def test_brain_log_lines_become_events():
    for line, kind in [
        ("you: hi | Pip: [happy] {hop} Hello!", "chat"),
        ('tool find_animal({"animal": "sheep"}) -> {"ok": true}', "tool"),
        ("noticed baby (minecraft:cow): A calf!", "notice"),
        ("awakening find_ore: {'sense': 1}", "awakening"),
        ("bond +4.0 (sweet) -> 34 wary", "bond"),
    ]:
        rx = dict(dashboard.EVENTS)[kind]
        assert rx.match(line), line


def test_keys_are_never_shown():
    out = dashboard.redact({"key": "AIza-secret", "upstreams": {"gemini": {"key": "env:GEMINI_API_KEY"}},
                            "access_key": "hunter2", "voice": "af_sky"})
    assert out["key"] == "(hidden)" and out["access_key"] == "(hidden)"
    assert out["upstreams"]["gemini"]["key"] == "env:GEMINI_API_KEY" and out["voice"] == "af_sky"
