"""#187: putting her to sleep and waking her up from the dashboard (and from the game, which asks the dashboard)."""
import os
import subprocess
import types

import gateway_stub  # noqa: F401  (puts services/ on the path)
import dashboard

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def fake_scripts(monkeypatch, tmp_path, brain_up):
    ran = []
    monkeypatch.setattr(dashboard, "ASLEEP", str(tmp_path / "asleep"))
    monkeypatch.setattr(dashboard.setup_steps, "port_open", lambda port, timeout=1: brain_up[0])
    monkeypatch.setattr(dashboard, "_script", lambda name, *a: ran.append((name,) + a) or types.SimpleNamespace(
        returncode=0, stdout="", stderr=""))
    return ran


def test_asleep_awake_and_stopped(monkeypatch, tmp_path):
    up = [True]
    ran = fake_scripts(monkeypatch, tmp_path, up)
    assert dashboard.her_state() == {"state": "awake"}
    up[0] = False
    assert dashboard.her_state() == {"state": "stopped"}, "not running, and nobody put her to sleep"
    assert dashboard.sleep_her()["state"] == "asleep"
    assert ran == [("stop.sh", "--keep", "dashboard")], "the dashboard stays, to wake her again"
    assert dashboard.her_state() == {"state": "asleep"} and os.path.exists(dashboard.ASLEEP)
    up[0] = True
    assert dashboard.wake_her()["state"] == "awake"
    assert ran[-1] == ("start.sh", "--background") and not os.path.exists(dashboard.ASLEEP)


def test_stopping_everything_answers_first(monkeypatch, tmp_path):
    ran = fake_scripts(monkeypatch, tmp_path, [True])
    timers = []
    monkeypatch.setattr(dashboard.threading, "Timer", lambda s, f: types.SimpleNamespace(start=lambda: timers.append(f)))
    assert dashboard.stop_everything()["ok"] and ran == [], "nothing stops before the page has its answer"
    timers[0]()
    assert ran == [("stop.sh",)]
    assert not os.path.exists(dashboard.ASLEEP), "with the dashboard gone the game can't wake her: not 'asleep'"


def test_the_page_can_ask_for_it():
    with open(os.path.join(ROOT, "services", "dashboard.py"), encoding="utf-8") as fh:
        src = fh.read()
    for path in ("/api/her/sleep", "/api/her/wake", "/api/her/stop-all"):
        assert src.count('"%s"' % path) >= 2, path + ": allowed, and answered"


def run_stop(tmp_path, *args):
    run = tmp_path / "run"
    run.mkdir(exist_ok=True)
    procs = {}
    for name in ("brain", "gateway", "dashboard"):
        p = subprocess.Popen(["sleep", "30"])
        procs[name] = p
        (run / (name + ".pid")).write_text(str(p.pid))
    out = subprocess.run(["bash", os.path.join(ROOT, "scripts", "stop.sh"), *args], capture_output=True, text=True,
                         env=dict(os.environ, KINDRED_HOME=str(tmp_path)), timeout=30).stdout
    for p in procs.values():
        p.poll()
    return out, procs


def test_stop_keeps_the_dashboard_when_asked(tmp_path):
    out, procs = run_stop(tmp_path, "--keep", "dashboard")
    try:
        assert "stopped brain" in out and "stopped gateway" in out and "dashboard" not in out
        assert procs["brain"].wait(5) is not None and procs["dashboard"].poll() is None
        assert (tmp_path / "run" / "dashboard.pid").exists(), "still known, so a later stop.sh stops it"
    finally:
        procs["dashboard"].kill()


def test_stop_stops_everything_by_default(tmp_path):
    out, procs = run_stop(tmp_path)
    assert all(p.wait(5) is not None for p in procs.values()) and "stopped dashboard" in out


def test_starting_her_again_any_way_wakes_her():
    with open(os.path.join(ROOT, "scripts", "start.sh"), encoding="utf-8") as fh:
        assert 'rm -f "$KH/asleep"' in fh.read()
