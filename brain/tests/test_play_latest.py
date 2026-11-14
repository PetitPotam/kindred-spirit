"""scripts/play-latest.sh (#185): playtest main or a pull request from the checkout, and go back."""
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "play-latest.sh"


def run(*args, env=None):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=30)


def test_status_says_which_version_is_in_use(tmp_path):
    app = tmp_path / "app"
    (app / "current").mkdir(parents=True)
    (app / "current" / "VERSION").write_text("0.3.0-beta.1")
    env = dict(os.environ, KINDRED_HOME=str(tmp_path / "home"), KINDRED_APP_DIR=str(app))
    (tmp_path / "home").mkdir()
    assert "the Setup installed (0.3.0-beta.1)" in run("--status", env=env).stdout
    (tmp_path / "home" / "playing-from").write_text("main abc1234 (0.3.0-beta.1-dev.abc1234)")
    assert "from the checkout: main abc1234" in run("--status", env=env).stdout


def test_help_and_unknown_arguments():
    assert "--back" in run("--help").stdout
    r = run("something-else")
    assert r.returncode != 0 and ("unknown" in r.stderr or "close Minecraft" in r.stderr)
