"""The dashboard reads logs and settings: parsing, and that keys never show."""
import gateway_stub  # noqa: F401  (puts services/ on the path)
import dashboard


def test_prompt_parts_and_kinds():
    p = "[Game state right now]\nHealth 10/10\n\n[What you remember]\nHis name is Alex.\n\n[Player]\nhello"
    parts = dashboard.split_prompt(p)
    assert parts == {"Game state right now": "Health 10/10", "What you remember": "His name is Alex.", "Player": "hello"}
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


def test_kindred_mod_config_points_at_another_game(tmp_path):
    """While filming with the dev game, its settings file is the one the Settings page shows and changes."""
    dev = str(tmp_path / "run" / "config" / "kindredspirit.json")
    assert dashboard.mod_configs({"KINDRED_MOD_CONFIG": dev}) == [dev]
    usual = dashboard.mod_configs({})
    assert len(usual) >= 2 and all(p.endswith("kindredspirit.json") for p in usual) and dev not in usual


def test_the_settings_of_every_minecraft_version_are_found(tmp_path, monkeypatch):
    """#159: the Setup's 26.3 profile plays in minecraft-kindred-26.3; another launcher's instance has its own config.
    The one changed last (the game played last) is the one the Settings page shows and changes."""
    import os
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("KINDRED_MOD_CONFIG", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(dashboard.setup_steps, "load_state", lambda: {})
    assert dashboard.mod_path() is None
    support = tmp_path / "Library" / "Application Support"

    def config(folder, when):
        f = folder / "config" / "kindredspirit.json"
        f.parent.mkdir(parents=True)
        f.write_text('{"glow": true}')
        os.utime(f, (when, when))
        return str(f)

    old = config(support / "minecraft-kindred", 1_700_000_000)  # 1.21.1, played long ago
    new = config(support / "minecraft-kindred-26.3", 1_700_000_500)  # 26.3, the Setup's recommendation
    assert old in dashboard.mod_configs({}) and new in dashboard.mod_configs({})
    assert dashboard.mod_path() == new
    prism = tmp_path / "PrismLauncher" / "instances" / "Robin" / "minecraft"
    other = config(prism, 1_700_001_000)
    monkeypatch.setattr(dashboard.setup_steps, "load_state", lambda: {"mods_folder": str(prism / "mods")})
    assert dashboard.mod_path() == other
    monkeypatch.setattr(dashboard.setup_steps, "load_state", lambda: 1 / 0)  # a broken Setup state: profiles only
    assert dashboard.mod_path() == new


def test_the_blueprints_page_shows_the_game_played_last(tmp_path, monkeypatch):
    """#175: the 26.3 profile has its own blueprints folder; the page (and adding or removing files) uses the game
    played last, the same folder the mod reads."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("KINDRED_MOD_CONFIG", raising=False)
    monkeypatch.delenv("KINDRED_BLUEPRINTS", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(dashboard.setup_steps, "load_state", lambda: {})
    game = tmp_path / "Library" / "Application Support" / "minecraft-kindred-26.3"
    (game / "config").mkdir(parents=True)
    (game / "config" / "kindredspirit.json").write_text("{}")
    assert dashboard.blueprint_dirs() == [str(game / "config" / "kindredspirit" / "blueprints"), str(game / "schematics"),
                                          str(game / "config" / "kindredspirit" / "blueprints-from-minecraft")]
    monkeypatch.setenv("KINDRED_BLUEPRINTS", str(tmp_path / "mine"))  # (set by hand: it wins)
    assert dashboard.blueprint_dirs() == dashboard.blueprints.DIRS
