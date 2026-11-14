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


def _menu(tmp_path, keys, then=None):
    """Runs the shortcut in a pseudo-terminal (so it asks), types `keys`, never opens the launcher."""
    import pty
    import select
    which(tmp_path)  # (an installed copy whose start.sh does nothing)
    env = dict(os.environ, KINDRED_HOME=str(tmp_path / "home"), KINDRED_APP_DIR=str(tmp_path / "app"),
               KINDRED_NO_LAUNCHER="1", KINDRED_MINECRAFT_DIR=str(tmp_path / "mc" / "minecraft"))
    pid, fd = pty.fork()
    if pid == 0:
        os.execve("/bin/bash", ["bash", str(SCRIPT)], env)
    out, sent, sent2 = b"", False, False
    while True:
        r, _, _ = select.select([fd], [], [], 15)
        if not r:
            break
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
        if not sent and b"to keep" in out:
            os.write(fd, keys)
            sent = True
        if then and not sent2 and then[0] in out:
            os.write(fd, then[1])
            sent2 = True
    os.waitpid(pid, 0)
    return out.decode(errors="replace")


def test_it_asks_and_enter_keeps_the_installed_release(tmp_path):
    out = _menu(tmp_path, b"\n")
    assert "Which Pip do you want to play?" in out and "The installed release (0.3.0-beta.1)" in out
    assert "Playing the version the Setup installed" in out and "Building" not in out


def test_a_wrong_answer_keeps_what_you_are_on(tmp_path):
    out = _menu(tmp_path, b"x\n")
    assert "Keeping what you're on" in out and "Playing the version the Setup installed" in out


def test_a_branch_can_be_picked(tmp_path):
    # (a name that doesn't exist: it says so and plays what you're on, without building anything)
    out = _menu(tmp_path, b"4\n", then=(b"Number or name", b"no-such-branch-for-tests\n"))
    assert "4) A branch on this computer" in out and "Branches on this computer" in out
    assert "no local branch named no-such-branch-for-tests" in out and "playing what you're on" in out
