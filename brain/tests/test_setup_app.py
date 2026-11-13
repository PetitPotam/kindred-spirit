"""Kindred Spirit Setup (#93): its steps, the help prompt, installing from the app's payload, the page's API and
the build's pieces. Everything happens in throwaway folders: no real home, no real install, no network."""
import http.client
import json
import os
import stat
import subprocess
import sys
import threading

import pytest

import gateway_stub  # noqa: F401  (puts services/ on the path)
import kindred_gateway as gw
import setup_steps
from kindred import hardware

REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(REPO, "setup"))
import build  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    kh = tmp_path / "riverrobin" / ".kindred-spirit"
    kh.mkdir(parents=True)
    monkeypatch.setattr(gw, "DIR", str(kh))
    monkeypatch.setenv("HOME", str(tmp_path / "riverrobin"))
    monkeypatch.setenv("KINDRED_HOME", str(kh))
    monkeypatch.setenv("KINDRED_APP_DIR", str(tmp_path / "app"))
    monkeypatch.setenv("KINDRED_LAUNCH_AGENTS_DIR", str(tmp_path / "LaunchAgents"))
    monkeypatch.delenv("KINDRED_PROFILE", raising=False)
    monkeypatch.setattr(setup_steps, "PAYLOAD", "")
    return kh


def fake_payload(where, version="9.9.9"):
    """What setup/build.py puts in the app: python/, kindred/, VERSION (with a stand-in Python)."""
    (where / "python" / "bin").mkdir(parents=True)
    py = where / "python" / "bin" / "python3"
    py.write_text("#!/bin/sh\nexit 0\n")
    py.chmod(0o755)
    (where / "kindred" / "scripts").mkdir(parents=True)
    (where / "VERSION").write_text(version + "\n")
    return str(where)


# ---------------------------------------------------------------------- the steps

def test_every_step_has_what_the_page_draws(home):
    out = setup_steps.overview()
    assert out["mode"] == "dashboard" and out["installed"] is None and out["home"].startswith("~")
    assert [s["id"] for s in out["steps"]] == ["computer", "install", "start", "login"]
    for s in out["steps"]:
        assert s["title"] and len(s["why"]) > 40 and s["default"] and s["status"] in ("todo", "done", "problem")
        assert isinstance(s["actions"], list) and isinstance(s["facts"], list)


def test_the_computer_step_recommends_and_remembers(home):
    s = setup_steps.step_computer()
    assert s["choices"][0]["value"] == "auto" and s["choices"][0]["recommended"] and s["status"] == "todo"
    assert setup_steps.run("computer", "choose", {"choice": "low"})["ok"]
    assert json.loads((home / "setup.json").read_text())["profile"] == "low"
    assert setup_steps.step_computer()["chosen"] == "low" and setup_steps.step_computer()["status"] == "done"
    bad = setup_steps.run("computer", "choose", {"choice": "ultra"})
    assert not bad["ok"] and "Choose" in bad["message"]
    assert setup_steps.run("computer", "test")["message"]


def test_hardware_uses_the_setups_choice_unless_overridden(home, monkeypatch):
    hw = {"ram_gb": 32, "cores": 10, "fast_cores": 8, "apple_silicon": True, "gpu": "metal"}
    assert hardware.profile(hw)["level"] == "high"
    (home / "setup.json").write_text('{"profile": "low"}')
    assert hardware.profile(hw)["level"] == "low" and hardware.profile(hw, choice="auto")["level"] == "high"
    monkeypatch.setenv("KINDRED_PROFILE", "medium")
    assert hardware.profile(hw)["level"] == "medium"
    (home / "setup.json").write_text("not json")
    monkeypatch.delenv("KINDRED_PROFILE")
    assert hardware.profile(hw)["level"] == "high"


def test_installing_copies_the_payload_and_keeps_settings(home, tmp_path, monkeypatch):
    (home / "brain.toml").write_text("# hers\n")
    monkeypatch.setattr(setup_steps, "PAYLOAD", fake_payload(tmp_path / "payload"))
    assert setup_steps.step_install()["status"] == "todo" and setup_steps.step_install()["actions"]
    r = setup_steps.run("install", "install")
    assert r["ok"] and "9.9.9" in r["message"]
    cur = tmp_path / "app" / "current"
    assert cur.is_symlink() and os.readlink(cur) == os.path.join("versions", "9.9.9")
    assert (cur / "python" / "bin" / "python3").exists()
    assert setup_steps.installed()["version"] == "9.9.9" and setup_steps.step_install()["status"] == "done"
    assert (home / "brain.toml").read_text() == "# hers\n"  # her settings are never touched
    assert stat.S_IMODE(os.stat(home / "secrets.env").st_mode) == 0o600
    assert "GEMINI_API_KEY=" in (home / "secrets.env").read_text()
    again = setup_steps.run("install", "install")
    assert again["ok"] and "already installed" in again["message"]


def test_a_broken_copy_of_the_same_version_is_replaced(home, tmp_path, monkeypatch):
    monkeypatch.setattr(setup_steps, "PAYLOAD", fake_payload(tmp_path / "payload"))
    broken = tmp_path / "app" / "versions" / "9.9.9"
    broken.mkdir(parents=True)
    (broken / "VERSION").write_text("9.9.9\n")  # no python/ inside
    assert setup_steps.run("install", "install")["ok"]
    assert (broken / "python" / "bin" / "python3").exists()
    assert not [p for p in os.listdir(tmp_path / "app" / "versions") if p != "9.9.9"]


def test_without_a_payload_there_is_nothing_to_install(home):
    r = setup_steps.run("install", "install")
    assert not r["ok"] and "Setup app" in r["message"]
    assert setup_steps.step_install()["actions"] == []
    assert not setup_steps.run("install", "test")["ok"]
    assert not setup_steps.run("start", "start")["ok"]


def test_unknown_steps_and_failures_are_reported_not_raised(home, monkeypatch):
    with pytest.raises(setup_steps.SetupError):
        setup_steps.run("nope", "test")

    def boom():
        raise RuntimeError("disk on fire")
    monkeypatch.setitem(setup_steps.STEPS, "computer", (setup_steps.step_computer, setup_steps.act_computer, boom))
    r = setup_steps.run("computer", "test")
    assert not r["ok"] and "disk on fire" in r["message"]
    assert json.loads((home / "setup.json").read_text())["results"]["computer"]["action"] == "test"


def test_brain_port_is_read_without_creating_her_settings(home):
    assert setup_steps.brain_port() == 47811 and not (home / "brain.toml").exists()
    (home / "brain.toml").write_text("[server]\nport = 47911\n")
    assert setup_steps.brain_port() == 47911


# ---------------------------------------------------------------------- her dashboard, reopening the app, login

def test_waking_her_at_login_is_opt_in_and_reversible(home, tmp_path, monkeypatch):
    import plistlib
    monkeypatch.setattr(setup_steps.sys, "platform", "darwin")
    s = setup_steps.step_login()
    assert s["chosen"] == "app" and s["choices"][0]["recommended"] and s["actions"] == []  # not installed yet
    assert not setup_steps.run("login", "choose", {"choice": "login"})["ok"]
    monkeypatch.setattr(setup_steps, "PAYLOAD", fake_payload(tmp_path / "payload"))
    setup_steps.install_runtime()
    (tmp_path / "app" / "versions" / "9.9.9" / "kindred" / "scripts" / "start.sh").write_text("#!/bin/bash\n")
    assert setup_steps.run("login", "choose", {"choice": "login"})["ok"]
    item = tmp_path / "LaunchAgents" / (setup_steps.LOGIN_LABEL + ".plist")
    plist = plistlib.loads(item.read_bytes())
    assert plist["RunAtLoad"] and plist["AbandonProcessGroup"]
    assert plist["ProgramArguments"][1].endswith(os.path.join("current", "kindred", "scripts", "start.sh"))  # follows updates
    assert plist["EnvironmentVariables"]["KINDRED_HOME"] == str(home)
    assert setup_steps.step_login()["chosen"] == "login" and setup_steps.run("login", "test")["ok"]
    assert setup_steps.run("login", "choose", {"choice": "app"})["ok"] and not item.exists()
    assert setup_steps.step_login()["status"] == "done"


def test_login_is_macos_only_for_now(home, monkeypatch):
    monkeypatch.setattr(setup_steps.sys, "platform", "linux")
    monkeypatch.setattr(setup_steps, "installed", lambda: {"version": "1", "path": "/x"})
    r = setup_steps.run("login", "choose", {"choice": "login"})
    assert not r["ok"] and "macOS" in r["message"]


def test_reopening_the_app_opens_her_dashboard_once_set_up(home, tmp_path, monkeypatch):
    monkeypatch.setattr(setup_steps, "PAYLOAD", fake_payload(tmp_path / "payload"))
    assert setup_steps.open_target() == "/setup"  # nothing installed: the steps
    setup_steps.install_runtime()
    assert setup_steps.open_target() == "/setup"  # installed but never woken
    setup_steps.save_state(woken=True)
    monkeypatch.setattr(setup_steps, "running", lambda: {"gateway": True, "brain": True, "dashboard": True})
    assert setup_steps.open_target() == setup_steps.dashboard_url()
    started = []
    monkeypatch.setattr(setup_steps, "running", lambda: {"gateway": False, "brain": False, "dashboard": False})
    monkeypatch.setitem(setup_steps.STEPS, "start", (setup_steps.step_start,
                                                     lambda a, b: started.append(a) or setup_steps._result(True, "ok"),
                                                     setup_steps.test_start))
    assert setup_steps.open_target() == setup_steps.dashboard_url() and started == ["start"]  # woken first
    monkeypatch.setitem(setup_steps.STEPS, "start", (setup_steps.step_start, lambda a, b: setup_steps._result(False, "no"),
                                                     setup_steps.test_start))
    assert setup_steps.open_target() == "/setup"  # couldn't wake her: the steps say why
    monkeypatch.setattr(setup_steps, "PAYLOAD", fake_payload(tmp_path / "newer", "10.0.0"))
    assert setup_steps.open_target() == "/setup"  # a newer Setup: install it first


# ---------------------------------------------------------------------- help prompts give nothing private away

def test_redact_takes_out_keys_tokens_emails_and_the_home_folder(home):
    (home / "secrets.env").write_text("GEMINI_API_KEY=my-own-very-private-value\n# OPENAI_API_KEY=\n")
    (home / "token").write_text("0123456789abcdef0123456789abcdef0123456789abcdef\n")
    text = ("open %s/.kindred-spirit/logs failed\nGEMINI_API_KEY=AIzaSyA-fake-0000000000000000000000\n"
            "key my-own-very-private-value and sk-proj-abcdefghijklmnopqrstuvwx\n"
            "token 0123456789abcdef0123456789abcdef0123456789abcdef by robin@example.com\n"
            "Authorization: Bearer gsk_abcdefghijklmnopqrstuvwxyz\nriverrobin's Mac, max_tokens: 300"
            % os.environ["HOME"])
    out = setup_steps.redact(text)
    for secret in ("AIzaSy", "my-own-very-private-value", "sk-proj", "0123456789abcdef", "robin@example.com",
                   "gsk_", os.environ["HOME"], "riverrobin"):
        assert secret not in out, (secret, out)
    assert "~/.kindred-spirit/logs" in out and "(me)'s Mac" in out and "max_tokens: 300" in out


def test_the_help_prompt_has_the_step_the_system_and_the_error(home):
    (home / "logs").mkdir()
    (home / "logs" / "brain.out").write_text("starting\nOSError: [Errno 48] Address already in use\n")
    p = setup_steps.help_prompt("start", "Not answering: brain. Press Start.\nfrom %s/x" % os.environ["HOME"])
    assert "Kindred Spirit" in p and "Wake her up" in p and "Not answering: brain" in p
    assert "Address already in use" in p and "GB memory" in p and setup_steps.own_version() in p
    assert os.environ["HOME"] not in p and "~/x" in p


def test_the_help_prompt_uses_the_last_failure_when_no_error_is_given(home):
    setup_steps.run("install", "install")  # fails: nothing to install
    p = setup_steps.help_prompt("install")
    assert "nothing to install" in p and "pressed \"install\"" in p


# ---------------------------------------------------------------------- the page's API, through the dashboard

@pytest.fixture
def server(home, monkeypatch):
    import dashboard
    srv = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
    monkeypatch.setattr(dashboard, "PORT", srv.server_address[1])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield dashboard, srv.server_address[1]
    srv.shutdown()


def request(port, method, path, body=None, origin=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    c.request(method, path, json.dumps(body) if body is not None else None, headers)
    r = c.getresponse()
    data = r.read()
    return r.status, (json.loads(data) if "json" in r.getheader("Content-Type", "") else data.decode())


def test_the_dashboard_serves_the_setup_page_and_its_api(server):
    dashboard, port = server
    code, page = request(port, "GET", "/setup")
    assert code == 200 and "Copy a help prompt" in page and "Test it" in page
    assert request(port, "GET", "/api/setup/hello")[1] == {"kindred": True, "setup": False, "version": setup_steps.own_version()}
    code, state = request(port, "GET", "/api/setup/state")
    assert code == 200 and [s["id"] for s in state["steps"]] == ["computer", "install", "start", "login"]
    code, r = request(port, "POST", "/api/setup/run", {"step": "computer", "action": "choose", "choice": "medium"},
                      origin="http://127.0.0.1:%d" % port)
    assert code == 200 and r["ok"]
    code, r = request(port, "POST", "/api/setup/help", {"step": "computer", "error": "oops"})
    assert code == 200 and "oops" in r["prompt"]


def test_open_goes_to_the_steps_or_her_dashboard(server, monkeypatch):
    _, port = server
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", "/open")
    r = c.getresponse()
    assert r.status == 302 and r.getheader("Location") == "/setup"
    monkeypatch.setattr(setup_steps, "open_target", lambda: "http://127.0.0.1:11440/")
    c.request("GET", "/open")
    r2 = c.getresponse()
    assert r2.status == 302 and r2.getheader("Location") == "http://127.0.0.1:11440/"
    code, state = request(port, "GET", "/api/setup/state")
    assert state["dashboard"]["url"].endswith(":%d/" % setup_steps.DASHBOARD_PORT) and "running" in state["dashboard"]


def test_other_web_pages_cannot_press_the_buttons(server):
    _, port = server
    code, _ = request(port, "POST", "/api/setup/run", {"step": "install", "action": "install"}, origin="https://evil.example")
    assert code == 403


def test_only_the_setup_app_quits(server, monkeypatch):
    dashboard, port = server
    assert request(port, "POST", "/api/setup/quit", {})[0] == 400  # the dashboard keeps running
    code, page = request(port, "GET", "/")
    assert "Kindred Dashboard" in page
    monkeypatch.setattr(dashboard, "SETUP_MODE", True)
    code, page = request(port, "GET", "/")
    assert "Kindred Spirit Setup" in page  # in the app, the Setup is the front page


def test_setup_mode_quits_when_nobody_looks(monkeypatch):
    import dashboard

    class Server:
        stopped = False

        def shutdown(self):
            self.stopped = True
    s = Server()
    monkeypatch.setattr(dashboard, "last_request", 0)
    dashboard.quit_when_idle(s, idle=1, every=0)
    assert s.stopped


# ---------------------------------------------------------------------- the build's pieces (no download, no app)

def test_the_build_ships_what_runs_and_pins_python():
    for rel in build.CODE:
        assert os.path.exists(os.path.join(build.ROOT, rel)), rel
    for target, (name, digest, tag) in build.PYTHONS.items():
        assert build.PY_VERSION in name and build.PBS_RELEASE in name and len(digest) == 64 and tag.startswith("macosx_")
    assert build.version() and "-" not in build.APP_NAME


def test_the_launcher_and_scripts_are_valid_shell():
    for rel in ("setup/macos/launcher.sh", "scripts/start.sh", "scripts/stop.sh"):
        subprocess.run(["bash", "-n", os.path.join(REPO, rel)], check=True)
    text = open(os.path.join(REPO, "setup", "macos", "If macOS won't open it.txt"), encoding="utf-8").read()
    assert "Open Anyway" in text and "Privacy & Security" in text
