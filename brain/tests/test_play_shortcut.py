"""scripts/play-mac.command (#188): the Play shortcut starts the version in use."""
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "play-mac.command"


def which(tmp_path, installed=True, checkout=False):
    home, app = tmp_path / "home", tmp_path / "app" / "current"
    home.mkdir(exist_ok=True)
    if installed:
        (app / "python" / "bin").mkdir(parents=True, exist_ok=True)
        (app / "python" / "bin" / "python3").write_text("#!/bin/sh\n")
        (app / "python" / "bin" / "python3").chmod(0o755)
        (app / "kindred" / "scripts").mkdir(parents=True, exist_ok=True)
        (app / "kindred" / "scripts" / "start.sh").write_text("")
        (app / "VERSION").write_text("0.3.0-beta.1")
    if checkout:
        (home / "playing-from").write_text("main abc1234 (0.3.0-beta.1-dev.abc1234)")
    env = dict(os.environ, KINDRED_HOME=str(home), KINDRED_APP_DIR=str(tmp_path / "app"))
    return subprocess.run(["bash", str(SCRIPT), "--dry-run"], capture_output=True, text=True, env=env, timeout=20).stdout


def test_the_installed_version_by_default(tmp_path):
    assert "the version the Setup installed (0.3.0-beta.1)" in which(tmp_path)


def test_the_checkout_after_play_latest(tmp_path):
    assert "the checkout: main abc1234" in which(tmp_path, checkout=True)


def test_the_checkout_without_a_setup(tmp_path):
    assert "this checkout (no Setup installed)" in which(tmp_path, installed=False)
