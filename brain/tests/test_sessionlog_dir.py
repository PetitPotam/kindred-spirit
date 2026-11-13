"""Session logs go where the brain's home is, so a filming or test home never writes into the real logs."""
import os

from kindred import sessionlog


def test_session_logs_follow_kindred_home(tmp_path, monkeypatch):
    monkeypatch.delenv("KINDRED_SESSION_DIR", raising=False)
    monkeypatch.setenv("KINDRED_HOME", str(tmp_path / "kindred-film"))
    assert sessionlog.default_dir() == str(tmp_path / "kindred-film" / "logs" / "sessions")
    log = sessionlog.SessionLog(clock=lambda: 1_700_000_000.0)
    log.start("local:Meadow")
    log.event("you", text="hi")
    assert log.path.startswith(str(tmp_path / "kindred-film" / "logs" / "sessions" / ""))
    assert os.listdir(tmp_path / "kindred-film" / "logs" / "sessions")


def test_kindred_session_dir_still_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("KINDRED_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("KINDRED_SESSION_DIR", str(tmp_path / "sessions"))
    assert sessionlog.default_dir() == str(tmp_path / "sessions")
