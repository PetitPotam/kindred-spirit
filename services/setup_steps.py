"""Kindred Spirit Setup: the guided steps (issue #82), served by the dashboard at /setup.

The Setup app (setup/build.py makes it) carries its own Python, her brain, the gateway and the dashboard
(its "payload"). Opening it runs the dashboard in setup mode from that payload and shows this guide in the
browser. Once installed, the normal dashboard serves the same guide, so the player can come back to any step.

Every step has the same shape, so the page draws them all the same way:
  title, why (plain words), default (what we recommend), facts (what we found), choices (optional),
  actions (buttons that do something), a test, and a help prompt to paste into an AI assistant.

Where things go:
  her settings, keys, memories and logs   ~/.kindred-spirit (KINDRED_HOME), as always
  the program (Python, brain, gateway)    ~/Library/Application Support/Kindred Spirit/versions/<version>,
                                          with "current" pointing at the one in use (KINDRED_APP_DIR)
Nothing outside those two folders is touched, except the login item the player may choose (step "login":
~/Library/LaunchAgents/io.github.petitpotam.kindredspirit.plist, removed when they choose otherwise).

Standard library only, like the dashboard.
"""
import json
import os
import platform
import plistlib
import re
import shutil
import socket
import subprocess
import sys
import time
import tomllib
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # the repository, or the payload's kindred/ folder
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "brain"))
import kindred_gateway as gw  # noqa: E402  (KINDRED_HOME, the gateway's port)
import setup_ai  # noqa: E402  (choosing her AI, #94)
import setup_models  # noqa: E402  (her local models, #95)
import setup_minecraft  # noqa: E402  (Minecraft, Fabric and the mod, then saying hi, #96)
from kindred import hardware  # noqa: E402

PAYLOAD = os.environ.get("KINDRED_SETUP_PAYLOAD") or ""  # the app's own copy: python/, kindred/, VERSION
DASHBOARD_PORT = int(os.environ.get("KINDRED_DASHBOARD_PORT", "11440"))
GUIDE_URL = "https://github.com/PetitPotam/kindred-spirit/blob/main/docs/SETUP.md"
LOGIN_LABEL = "io.github.petitpotam.kindredspirit"  # the login item that wakes her (macOS LaunchAgent)
NEEDS_GB = 3  # the program (~0.13 GB) and, later, her voice, hearing and memory models with room to spare
PROFILES = {"low": "Light", "medium": "Balanced", "high": "Best"}


def app_dir():
    """Where the program is installed (per user, no admin password)."""
    if os.environ.get("KINDRED_APP_DIR"):
        return os.environ["KINDRED_APP_DIR"]
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "Kindred Spirit")
    if sys.platform.startswith("win"):  # for later (#40)
        return os.path.join(os.environ.get("LOCALAPPDATA") or home, "Kindred Spirit")
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share"), "kindred-spirit")


def read_version(folder):
    """A payload's or an installed copy's VERSION file; None if there isn't one."""
    try:
        with open(os.path.join(folder, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def own_version():
    """This copy's version: the payload's, an installed copy's, or the repository's mod_version."""
    v = read_version(os.path.dirname(ROOT))
    if v:
        return v
    try:
        with open(os.path.join(ROOT, "mod", "gradle.properties"), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("mod_version="):
                    return line.split("=", 1)[1].strip() + "-dev"
    except OSError:
        pass
    return "dev"


# ---------------------------------------------------------------------- what's been chosen and done

def state_path():
    return os.path.join(gw.DIR, "setup.json")


def load_state():
    try:
        with open(state_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(**changes):
    s = load_state()
    s.update(changes)
    os.makedirs(gw.DIR, exist_ok=True)
    tmp = state_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(s, fh, indent=2)
    os.replace(tmp, state_path())
    return s


# ---------------------------------------------------------------------- the computer

def computer():
    hw = hardware.detect()
    home = os.path.expanduser("~")
    try:
        free_gb = round(shutil.disk_usage(home).free / 2 ** 30, 1)
    except OSError:
        free_gb = 0
    mac = platform.mac_ver()[0]
    if mac:
        os_name = "macOS %s" % mac
    elif sys.platform.startswith("win"):
        os_name = "Windows %s" % platform.release()
    else:
        os_name = "%s %s" % (platform.system(), platform.release())
    chip = "Apple silicon" if hw["apple_silicon"] else platform.machine() or "unknown"
    return dict(hw, free_gb=free_gb, os=os_name, chip=chip)


def recommended_profile(hw):
    """What this computer suits, whatever was chosen."""
    return hardware.profile(hw, choice="auto")["level"]


# ---------------------------------------------------------------------- installing the program

def installed():
    """The installed copy in use: {"version", "path"}, or None."""
    cur = os.path.join(app_dir(), "current")
    if not os.path.isdir(cur):
        return None
    path = os.path.realpath(cur)
    return {"version": read_version(path) or "unknown", "path": path}


def runtime_python(path):
    for rel in (("python", "bin", "python3"), ("python", "python.exe")):
        p = os.path.join(path, *rel)
        if os.path.exists(p):
            return p
    return None


def prepare_home():
    """~/.kindred-spirit with its logs folder and an empty keys file only you can read (as scripts/setup.sh does)."""
    os.makedirs(os.path.join(gw.DIR, "logs"), exist_ok=True)
    try:
        os.chmod(gw.DIR, 0o700)
    except OSError:
        pass
    secrets = os.path.join(gw.DIR, "secrets.env")
    if not os.path.exists(secrets):
        fd = os.open(secrets, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("# API keys for the Kindred gateway. Only you can read this file; never share it.\n"
                     "# The Setup fills it in when you choose her AI. Free Gemini key: https://aistudio.google.com/apikey\n"
                     "GEMINI_API_KEY=\n")


def install_runtime(payload=None):
    """Copies the app's payload to versions/<version> and makes it the current one. Settings are not touched."""
    payload = payload or PAYLOAD
    version = read_version(payload) if payload else None
    if not version or not runtime_python(payload):
        raise SetupError("This copy has nothing to install: open the Kindred Spirit Setup app to install her.")
    versions = os.path.join(app_dir(), "versions")
    dest = os.path.join(versions, version)
    os.makedirs(versions, exist_ok=True)
    fresh = not (read_version(dest) == version and runtime_python(dest))
    if fresh:
        part = dest + ".part"
        shutil.rmtree(part, ignore_errors=True)
        shutil.copytree(payload, part, symlinks=True)
        if os.path.exists(dest):  # a broken copy of the same version: set it aside, then remove it
            old = dest + ".old-%d" % time.time()
            os.replace(dest, old)
            shutil.rmtree(old, ignore_errors=True)
        os.replace(part, dest)
    cur = os.path.join(app_dir(), "current")
    tmp = cur + ".new"
    if os.path.lexists(tmp):
        os.remove(tmp)
    os.symlink(os.path.join("versions", version), tmp)
    os.replace(tmp, cur)
    prepare_home()
    save_state(installed=version)
    return {"version": version, "path": dest, "copied": fresh}


class SetupError(Exception):
    """A problem the player can act on; the message says what to do."""


# ---------------------------------------------------------------------- is she running?

def http_ok(url, timeout=2):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def port_open(port, timeout=1):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def brain_port():
    """Her brain's port from brain.toml (read only: the brain writes that file the first time it starts)."""
    try:
        with open(os.path.join(gw.DIR, "brain.toml"), "rb") as fh:
            return int(tomllib.load(fh).get("server", {}).get("port", 47811))
    except (OSError, ValueError, TypeError, AttributeError):
        return 47811


def running():
    return {
        "gateway": http_ok("http://127.0.0.1:%d/health" % gw.LISTEN_PORT),
        "brain": port_open(brain_port()),
        "dashboard": http_ok("http://127.0.0.1:%d/api/setup/hello" % DASHBOARD_PORT),
    }


def script_env(rt):
    """The environment start.sh and stop.sh get: this installed copy's Python, and the same home and ports."""
    env = dict(os.environ)
    env.pop("KINDRED_SETUP_PAYLOAD", None)
    env.update(KINDRED_PYTHON=runtime_python(rt["path"]) or "", KINDRED_HOME=gw.DIR,
               KINDRED_GATEWAY_PORT=str(gw.LISTEN_PORT), KINDRED_DASHBOARD_PORT=str(DASHBOARD_PORT))
    env["PATH"] = env.get("PATH") or "/usr/bin:/bin:/usr/sbin:/sbin"
    return env


def run_script(rt, name, *args, timeout=60):
    script = os.path.join(rt["path"], "kindred", "scripts", name)
    r = subprocess.run(["/bin/bash", script, *args], env=script_env(rt), capture_output=True, text=True,
                       timeout=timeout, cwd=os.path.join(rt["path"], "kindred"))
    return r.returncode, (r.stdout + r.stderr).strip()


# ---------------------------------------------------------------------- the steps

def _result(ok, message, details="", warn=False):
    return {"ok": ok, "warn": warn, "message": message, "details": details}


def step_computer():
    c = computer()
    rec = recommended_profile(c)
    chosen = load_state().get("profile", "auto")
    facts = [["System", c["os"]], ["Chip", c["chip"]], ["Memory", "%s GB" % c["ram_gb"]],
             ["Processor cores", "%d (%d fast)" % (c["cores"], c["fast_cores"])],
             ["Free space", "%s GB" % c["free_gb"]]]
    choices = [{"value": "auto", "label": "Let the Setup choose (%s)" % PROFILES[rec], "recommended": True,
                "note": "Picked from your memory and chip. You can change it any time."}]
    for level, label in PROFILES.items():
        choices.append({"value": level, "label": label, "note": {
            "low": "Smallest models: for computers with 8 GB of memory or less. She hears a little less well.",
            "medium": "A good balance for most laptops.",
            "high": "Bigger, better hearing: for 16 GB of memory or more, or Apple silicon."}[level]})
    done = "profile" in load_state()
    return {
        "id": "computer", "title": "Your computer",
        "why": "Pip runs next to Minecraft on your computer. The Setup looks at your memory and chip to pick "
               "settings that keep the game smooth: how big her hearing model is, and how much of the processor "
               "her voice may use.",
        "default": "Let the Setup choose. On this computer that's \"%s\"." % PROFILES[rec],
        "facts": facts, "choices": choices, "chosen": chosen,
        "actions": [{"id": "choose", "label": "Use this", "primary": True}],
        "status": "done" if done else "todo",
        "summary": "%s, %s GB memory: %s" % (c["chip"], c["ram_gb"], PROFILES[rec if chosen == "auto" else chosen]),
    }


def act_computer(action, body):
    if action != "choose":
        raise SetupError("unknown action")
    choice = str(body.get("choice") or "auto")
    if choice not in ("auto", *PROFILES):
        raise SetupError("Choose one of the options.")
    save_state(profile=choice)
    return _result(True, "Saved: %s." % ("chosen by the Setup" if choice == "auto" else PROFILES[choice]))


def test_computer():
    c = computer()
    problems, notes = [], []
    if c["free_gb"] and c["free_gb"] < NEEDS_GB:
        problems.append("Only %s GB free: Pip needs about %d GB. Free some space (empty the Trash, remove old "
                        "downloads), then test again." % (c["free_gb"], NEEDS_GB))
    if c["ram_gb"] and c["ram_gb"] < 8:
        notes.append("%s GB of memory is tight next to Minecraft: \"Light\" is the safe choice." % c["ram_gb"])
    if sys.platform == "darwin":
        major = int((platform.mac_ver()[0] or "0").split(".")[0])
        if major and major < 12:
            problems.append("macOS %s is older than Pip supports (macOS 12 Monterey or newer)." % platform.mac_ver()[0])
    details = "\n".join("%s: %s" % (k, v) for k, v in step_computer()["facts"])
    if problems:
        return _result(False, " ".join(problems), details)
    return _result(True, "This computer can run Pip." + (" " + " ".join(notes) if notes else ""), details, warn=bool(notes))


def step_install():
    rt = installed()
    mine = read_version(PAYLOAD) if PAYLOAD else None
    if rt and (not mine or rt["version"] == mine):
        status, summary = "done", "Version %s is installed." % rt["version"]
    elif rt:
        status, summary = "todo", "Version %s is installed; this Setup has %s." % (rt["version"], mine)
    else:
        status, summary = "todo", "Not installed yet."
    facts = [["Program", tilde(os.path.join(app_dir(), "versions"))],
             ["Your settings and memories", tilde(gw.DIR)]]
    if rt:
        facts.insert(0, ["Installed", rt["version"]])
    if mine:
        facts.insert(0, ["In this Setup", mine])
    return {
        "id": "install", "title": "Her brain on this computer",
        "why": "Pip's brain is a small program that runs on your computer while you play: it remembers, decides "
               "what she says and talks to the AI you choose. It comes with everything it needs (its own "
               "Python), so you don't install anything else by hand. It goes in your user folder; no "
               "administrator password is needed.",
        "default": "Install it. About 130 MB.",
        "facts": facts,
        "actions": [{"id": "install", "label": "Install" if not rt else "Install again", "primary": not rt}] if mine else [],
        "status": status, "summary": summary,
    }


def act_install(action, body):
    if action != "install":
        raise SetupError("unknown action")
    out = install_runtime()
    return _result(True, "Installed version %s." % out["version"] if out["copied"]
                   else "Version %s was already installed; it's the one in use." % out["version"], tilde(out["path"]))


def test_install():
    rt = installed()
    if not rt:
        return _result(False, "Her brain isn't installed yet: press Install first.")
    py = runtime_python(rt["path"])
    if not py:
        return _result(False, "The installed copy is missing its Python. Press \"Install again\".", tilde(rt["path"]))
    probe = ("import sys, numpy, websockets; sys.path.insert(0, 'brain'); import kindred.server; "
             "print('Python %d.%d.%d' % sys.version_info[:3], '| numpy', numpy.__version__, '| websockets', websockets.__version__)")
    try:
        r = subprocess.run([py, "-I", "-B", "-c", probe], cwd=os.path.join(rt["path"], "kindred"),
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return _result(False, "Her brain's Python didn't start: %s" % e)
    if r.returncode != 0:
        return _result(False, "Her brain's Python started but couldn't load her brain.", (r.stdout + r.stderr).strip()[-2000:])
    secrets = os.path.join(gw.DIR, "secrets.env")
    if os.path.exists(secrets) and os.stat(secrets).st_mode & 0o077:
        os.chmod(secrets, 0o600)
    return _result(True, "Her brain loads. Version %s." % rt["version"], r.stdout.strip())


def step_start():
    rt = installed()
    up = running() if rt else {"gateway": False, "brain": False, "dashboard": False}
    all_up = all(up.values())
    label = {"gateway": "Gateway (her link to the AI)", "brain": "Her brain", "dashboard": "Dashboard"}
    facts = [[label[k], "running" if v else "stopped"] for k, v in up.items()]
    return {
        "id": "start", "title": "Wake her up",
        "why": "Three small helpers run in the background while you play: the gateway (it talks to the AI and "
               "her voice), her brain (the game connects to it), and the dashboard (a page where you can see "
               "what she's thinking). They use little power and keep running after you close this page.",
        "default": "Start them now.",
        "facts": facts,
        "actions": ([{"id": "start", "label": "Start", "primary": not all_up}, {"id": "stop", "label": "Stop"}]
                    if rt else []),
        "links": ([{"label": "Open her dashboard", "url": dashboard_url()}] if up["dashboard"] else []),
        "status": "done" if all_up else "todo",
        "summary": "Running." if all_up else ("Install her brain first." if not rt else "Not running."),
    }


def act_start(action, body):
    rt = installed()
    if not rt:
        raise SetupError("Install her brain first (the step before).")
    if action == "stop":
        code, out = run_script(rt, "stop.sh")
        return _result(code == 0, "Stopped." if code == 0 else "Couldn't stop everything.", out)
    if action != "start":
        raise SetupError("unknown action")
    code, out = run_script(rt, "start.sh", "--background", timeout=90)
    deadline = time.time() + 15
    up = running()
    while not all(up.values()) and time.time() < deadline:
        time.sleep(0.5)
        up = running()
    if code != 0 or not all(up.values()):
        missing = ", ".join(k for k, v in up.items() if not v)
        return _result(False, "Started, but these aren't answering yet: %s." % (missing or "?"),
                       out + "\n\n" + log_tail("gateway.out", "brain.out", "dashboard.out"))
    save_state(woken=True)  # set up once: from now on, opening the app opens her dashboard
    return _result(True, "She's awake: the gateway, her brain and her dashboard are running.", out)


def test_start():
    if not installed():
        return _result(False, "Install her brain first (the step before).")
    up = running()
    if all(up.values()):
        return _result(True, "Everything answers: the gateway, her brain (port %d) and the dashboard." % brain_port())
    missing = [k for k, v in up.items() if not v]
    return _result(False, "Not answering: %s. Press Start; if it still fails, copy a help prompt." % ", ".join(missing),
                   log_tail("gateway.out", "brain.out", "dashboard.out"))


# ---------------------------------------------------------------------- waking her at login (opt-in)

def launch_agents_dir():
    return os.environ.get("KINDRED_LAUNCH_AGENTS_DIR") or os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents")


def login_item():
    return os.path.join(launch_agents_dir(), LOGIN_LABEL + ".plist")


def login_plist():
    """What macOS runs at login: start.sh from the installed copy in use ("current", so updates follow), in the
    background, with the same home and ports as now. It starts what isn't running and exits; the helpers stay."""
    cur = os.path.join(app_dir(), "current")
    return {
        "Label": LOGIN_LABEL,
        "ProgramArguments": ["/bin/bash", os.path.join(cur, "kindred", "scripts", "start.sh"), "--background"],
        "EnvironmentVariables": {"KINDRED_PYTHON": os.path.join(cur, "python", "bin", "python3"), "KINDRED_HOME": gw.DIR,
                                 "KINDRED_GATEWAY_PORT": str(gw.LISTEN_PORT), "KINDRED_DASHBOARD_PORT": str(DASHBOARD_PORT),
                                 "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
        "RunAtLoad": True,
        "AbandonProcessGroup": True,  # start.sh exits; the helpers it started keep running
        "StandardOutPath": os.path.join(gw.DIR, "logs", "login.out"),
        "StandardErrorPath": os.path.join(gw.DIR, "logs", "login.out"),
    }


def step_login():
    on = os.path.exists(login_item())
    mac = sys.platform == "darwin"
    return {
        "id": "login", "title": "Every time you play",
        "why": "Her brain, the gateway and her dashboard keep running until you restart or log out. To have them "
               "ready every time, the Setup can wake her when you log in to your Mac: macOS then lists her under "
               "System Settings > General > Login Items (as \"bash\", the small program that starts her). Otherwise, "
               "open Kindred Spirit Setup before you play: once she's set up, it wakes her and opens her dashboard.",
        "default": "Open Kindred Spirit Setup when you want to play (nothing runs at login).",
        "facts": [["Wakes her at login", "yes" if on else "no"]],
        "choices": [{"value": "app", "label": "When I open Kindred Spirit Setup", "recommended": True,
                     "note": "Nothing runs until you want to play."},
                    {"value": "login", "label": "When I log in to this Mac",
                     "note": "Ready at once; she uses a little memory all the time." if mac else "macOS only, for now."}],
        "chosen": "login" if on else "app",
        "actions": [{"id": "choose", "label": "Use this", "primary": True}] if installed() else [],
        "status": "done" if "login" in load_state() else "todo",
        "summary": "Wakes when you log in." if on else "Wakes when you open the Setup.",
    }


def act_login(action, body):
    if action != "choose":
        raise SetupError("unknown action")
    choice = str(body.get("choice") or "app")
    if choice not in ("app", "login"):
        raise SetupError("Choose one of the options.")
    if choice == "login":
        if sys.platform != "darwin":
            raise SetupError("Waking her at login works on macOS only, for now.")
        if not installed():
            raise SetupError("Install her brain first.")
        os.makedirs(launch_agents_dir(), exist_ok=True)
        with open(login_item(), "wb") as fh:
            plistlib.dump(login_plist(), fh)
        msg = "From your next login, she wakes by herself."
    else:
        if os.path.exists(login_item()):
            os.remove(login_item())
        msg = "Nothing runs at login. Open Kindred Spirit Setup when you want to play."
    save_state(login=choice)
    return _result(True, msg)


def test_login():
    if not os.path.exists(login_item()):
        return _result(True, "Nothing runs at login: open Kindred Spirit Setup when you want to play.")
    try:
        with open(login_item(), "rb") as fh:
            item = plistlib.load(fh)
    except (OSError, ValueError) as e:
        return _result(False, "The login item can't be read: %s. Choose again." % e)
    missing = [p for p in (item["ProgramArguments"][1], item["EnvironmentVariables"]["KINDRED_PYTHON"]) if not os.path.exists(p)]
    if missing:
        return _result(False, "The login item points to a program that isn't there any more. Install her brain again, "
                       "then choose again.", "\n".join(tilde(m) for m in missing))
    return _result(True, "She wakes when you log in.", tilde(login_item()))


# ---------------------------------------------------------------------- her AI (#94): setup_ai.py does the work

API_CHOICES = [k for k, v in setup_ai.PROVIDERS.items() if v["kind"] == "api"]


def _ai_fields(choices_with_keys):
    return [{"id": "key", "label": "Your key (it stays on this computer, only you can read it)", "type": "password",
             "for": choices_with_keys, "placeholder": "paste it here"},
            {"id": "model", "label": "Model (optional: empty is our pick for her)", "type": "text",
             "for": [k for k in setup_ai.PROVIDERS if k != "gemini"], "placeholder": ""}]


def step_ai():
    name, _, s = setup_ai.current()
    last = load_state().get("results", {}).get("ai") or {}
    up = s["upstreams"].get(name) or {}
    return {
        "id": "ai", "title": "Her conversation (System 1)",
        "why": "Pip talks with an AI service, through the gateway on your computer. This is the AI that answers you "
               "and says things on her own, so it should be quick. Every choice works; the free Gemini key is the "
               "easiest start, and you can change it any time.",
        "default": "Gemini with a free key from Google (about 2 minutes to get one).",
        "facts": [["In use", setup_ai.PROVIDERS.get(name, {}).get("label", name)],
                  ["Model", up.get("model") or "the provider's default"]],
        "choices": [dict(setup_ai.describe(k), recommended=(k == "gemini")) for k in setup_ai.PROVIDERS],
        "chosen": name if name in setup_ai.PROVIDERS else "gemini",
        "fields": _ai_fields(API_CHOICES),
        "actions": [{"id": "choose", "label": "Use this", "primary": True}]
                   + ([{"id": "pull", "label": "Download the model (Ollama)"}] if name == "ollama" else []),
        "status": "done" if last.get("ok") else ("problem" if last and not last.get("ok") else "todo"),
        "summary": ("%s answers." % setup_ai.PROVIDERS.get(name, {}).get("label", name)) if last.get("ok")
                   else "Choose her AI, then test it.",
    }


def act_ai(action, body):
    if action == "pull":
        log = setup_ai.pull_ollama_model()
        return _result(True, "Downloading %s in the background (a few GB): test again in a few minutes."
                       % setup_ai.ollama_model(), tilde(log))
    if action != "choose":
        raise SetupError("unknown action")
    name = str(body.get("choice") or "")
    try:
        setup_ai.apply(name, key=str(body.get("key") or ""), model=str(body.get("model") or ""))
    except setup_ai.Problem as e:
        raise SetupError(str(e))
    tested = test_ai()
    return dict(tested, message="Saved. " + tested["message"])


def test_ai():
    name, _, _ = setup_ai.current()
    if name == "ollama" and setup_ai.ollama_has_model(setup_ai.ollama_model()) is False:
        return _result(False, "Ollama hasn't got the model %s yet: press \"Download the model\"." % setup_ai.ollama_model())
    try:
        secs, text, tokens = setup_ai.call("reply")
    except setup_ai.Problem as e:
        return _result(False, setup_ai.explain(name, str(e)))
    if not text:
        return _result(False, setup_ai.explain(name, "The AI answered, but with nothing."))
    return _result(True, "She answered in %.1f s: \"%s\"" % (secs, text[:120]),
                   "%s; %s tokens for this test. Prices: see your provider's page (Gemini's free tier and Groq's are free "
                   "up to their limits; a subscription's tool uses your plan; Ollama is free)."
                   % (setup_ai.PROVIDERS.get(name, {}).get("label", name), tokens if tokens is not None else "?"),
                   warn=secs > 6)


def step_thinking():
    main, reflect, s = setup_ai.current()
    last = load_state().get("results", {}).get("thinking") or {}
    choices = [{"value": "same", "label": "The same AI as her conversation", "recommended": True,
                "note": "Simplest: nothing more to set up."},
               {"value": setup_ai.OFF, "label": "Off",
                "note": "She doesn't learn from your time together or write her story. Saves AI calls."}]
    choices += [setup_ai.describe(k) for k in setup_ai.PROVIDERS]
    return {
        "id": "thinking", "title": "Her slow thinking (System 2)",
        "why": "Now and then, in the background, Pip thinks about what happened: she learns what matters to you, "
               "keeps her memories tidy and writes her own story. It's called rarely, so a slower, stronger AI suits "
               "it; or simply the same one as her conversation.",
        "default": "The same AI as her conversation.",
        "facts": [["In use", "the same as her conversation" if reflect == "same" else
                   "off" if reflect == setup_ai.OFF else setup_ai.PROVIDERS.get(reflect, {}).get("label", reflect)]],
        "choices": choices, "chosen": reflect if reflect in ("same", setup_ai.OFF) or reflect in setup_ai.PROVIDERS else "same",
        "fields": _ai_fields(API_CHOICES),
        "actions": [{"id": "choose", "label": "Use this", "primary": True}],
        "status": "done" if last.get("ok") else ("problem" if last and not last.get("ok") else "todo"),
        "summary": "Chosen." if last.get("ok") else "Choose, then test.",
    }


def act_thinking(action, body):
    if action != "choose":
        raise SetupError("unknown action")
    choice = str(body.get("choice") or "same")
    try:
        if choice in ("same", setup_ai.OFF):
            setup_ai.thinking_choice(choice)
        else:
            setup_ai.apply(choice, key=str(body.get("key") or ""), model=str(body.get("model") or ""), kind="reflect")
    except setup_ai.Problem as e:
        raise SetupError(str(e))
    tested = test_thinking()
    return dict(tested, message="Saved. " + tested["message"])


def test_thinking():
    main, reflect, _ = setup_ai.current()
    if reflect == setup_ai.OFF:
        return _result(True, "Off: she won't learn from your time together until you choose an AI here.", warn=True)
    try:
        secs, text, _ = setup_ai.call("reflect")
    except setup_ai.Problem as e:
        return _result(False, setup_ai.explain(main if reflect == "same" else reflect, str(e)))
    return _result(bool(text), "Her slow thinking answered in %.1f s." % secs if text else "The AI answered with nothing.")


STEPS = {
    "computer": (step_computer, act_computer, test_computer),
    "install": (step_install, act_install, test_install),
    "start": (step_start, act_start, test_start),
    "ai": (step_ai, act_ai, test_ai),
    "thinking": (step_thinking, act_thinking, test_thinking),
    "instincts": (setup_models.step_instincts, setup_models.act_instincts, setup_models.test_instincts),
    "voice": (setup_models.step_voice, setup_models.act_voice, setup_models.test_voice),
    "hearing": (setup_models.step_hearing, setup_models.act_hearing, setup_models.test_hearing),
    "minecraft": (setup_minecraft.step_minecraft, setup_minecraft.act_minecraft, setup_minecraft.test_minecraft),
    "hello": (setup_minecraft.step_hello, setup_minecraft.act_hello, setup_minecraft.test_hello),
    "login": (step_login, act_login, test_login),
}
LOGS_FOR = {"computer": (), "install": ("setup.out",), "start": ("gateway.out", "brain.out", "dashboard.out"),
            "login": ("login.out",), "ai": ("gateway.out", "ollama-pull.out"), "thinking": ("gateway.out",),
            "instincts": ("setup-models.out", "embed.out"), "voice": ("setup-models.out", "kokoro.out"),
            "hearing": ("whisper.out",), "minecraft": (), "hello": ("brain.log",)}


# ---------------------------------------------------------------------- her dashboard, and opening the app again

def dashboard_url():
    return "http://127.0.0.1:%d/" % DASHBOARD_PORT


def ready():
    """Set up once (installed, this Setup's version, woken at least once): opening the app goes to her dashboard."""
    rt = installed()
    mine = read_version(PAYLOAD) if PAYLOAD else None
    return bool(rt and (not mine or rt["version"] == mine) and load_state().get("woken"))


def open_target():
    """Where opening the app lands: her dashboard once she's set up (waking her first if needed), else the steps."""
    if not ready():
        return "/setup"
    if not all(running().values()) and not run("start", "start")["ok"]:
        return "/setup"  # the "Wake her up" step shows what went wrong
    return dashboard_url()


def overview():
    steps = []
    for sid, (show, _, _) in STEPS.items():
        try:
            steps.append(show())
        except Exception as e:  # one broken step must not hide the others
            steps.append({"id": sid, "title": sid, "why": "", "status": "problem", "summary": str(e), "actions": []})
    rt = installed()
    up = http_ok(dashboard_url() + "api/setup/hello")
    return {"version": own_version(), "mode": "app" if PAYLOAD else "dashboard",
            "installed": rt["version"] if rt else None, "home": tilde(gw.DIR), "guide": GUIDE_URL, "steps": steps,
            "dashboard": {"url": dashboard_url(), "running": up}}


def run(step_id, action, body=None):
    """A button: "test" runs the step's test, anything else is the step's own action."""
    if step_id not in STEPS:
        raise SetupError("no such step")
    _, act, test = STEPS[step_id]
    try:
        out = test() if action == "test" else act(action, body or {})
    except SetupError as e:
        out = _result(False, str(e))
    except Exception as e:  # anything unexpected: say what it was, so the help prompt can carry it
        out = _result(False, "Something went wrong: %s: %s" % (type(e).__name__, e))
    results = load_state().get("results", {})
    results[step_id] = dict(out, action=action, time=time.strftime("%Y-%m-%d %H:%M:%S"))
    save_state(results=results)
    return out


# ---------------------------------------------------------------------- help: a prompt for any AI assistant

KEY_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),                  # Google
    re.compile(r"\b(?:sk|gsk|xai|pk|rk)[-_][0-9A-Za-z_\-]{16,}"),  # OpenAI, Anthropic (sk-ant-), Groq, others
    re.compile(r"\b(?:ghp|gho|github_pat)_[0-9A-Za-z_]{20,}"),
    re.compile(r"\b[0-9a-fA-F]{32,}\b"),                      # tokens such as hers in ~/.kindred-spirit/token
    re.compile(r"\b[0-9A-Za-z+_\-]{40,}={0,2}"),              # other long secrets
]
ASSIGNED = re.compile(r"(?i)\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)\s*[=:]\s*(\"?)[^\s\"]{8,}\2")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _secret_values():
    out = []
    for name in (os.path.join(gw.DIR, "secrets.env"), os.path.join(gw.DIR, "token")):
        try:
            with open(name, encoding="utf-8") as fh:
                for line in fh:
                    v = line.split("=", 1)[-1].strip().strip('"\'')
                    if len(v) >= 8 and not line.lstrip().startswith("#"):
                        out.append(v)
        except OSError:
            pass
    return out


def tilde(path):
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if home and path.startswith(home) else path


def redact(text):
    """Takes keys, tokens, e-mail addresses, the home folder and the user name out of text that leaves this computer."""
    text = str(text or "")
    for v in _secret_values():
        text = text.replace(v, "(hidden)")
    text = ASSIGNED.sub(lambda m: "%s=(hidden)" % m.group(1), text)
    for rx in KEY_PATTERNS:
        text = rx.sub("(hidden)", text)
    text = EMAIL.sub("(an e-mail address)", text)
    home = os.path.expanduser("~")
    if home and home != "/":
        text = text.replace(home, "~")
    user = os.path.basename(home) if home else ""
    if len(user) >= 3:
        text = re.sub(r"(?<![\w.-])%s(?![\w.-])" % re.escape(user), "(me)", text)
    return text


def log_tail(*names, lines=25):
    out = []
    for name in names:
        path = os.path.join(gw.DIR, "logs", name)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                tail = fh.readlines()[-lines:]
        except OSError:
            continue
        if tail:
            out.append("--- last lines of %s ---\n%s" % (name, "".join(tail).rstrip()))
    return "\n\n".join(out)


def help_prompt(step_id, error=None):
    """A ready prompt for ChatGPT, Claude or another assistant: the step, this computer, the exact error."""
    show = STEPS.get(step_id, (None,))[0]
    step = show() if show else {"title": step_id, "why": ""}
    c = computer()
    last = load_state().get("results", {}).get(step_id) or {}
    if not error and last and not last.get("ok", True):
        error = ("%s\n%s" % (last.get("message", ""), last.get("details", ""))).strip()
    parts = [
        "I'm setting up Kindred Spirit, a mod for Minecraft Java 1.21.1 (Fabric) with an AI companion called Pip, "
        "using its Setup app. One step isn't working. I'm not technical: please explain in simple words what "
        "went wrong and what I should do, one step at a time. If you need more information, tell me exactly "
        "where to find it.",
        "",
        "My computer:",
        "- %s, %s" % (c["os"], c["chip"]),
        "- %s GB memory, %s GB free disk space" % (c["ram_gb"], c["free_gb"]),
        "- Kindred Spirit Setup %s%s" % (own_version(), " (installed: %s)" % installed()["version"] if installed() else ""),
        "",
        "The step: \"%s\"" % step.get("title", step_id),
        "What it does: %s" % step.get("why", ""),
    ]
    if last.get("action"):
        parts.append("What I did: pressed \"%s\" (%s)" % ({"test": "Test it"}.get(last["action"], last["action"]),
                                                         last.get("time", "")))
    parts += ["", "The error, exactly as shown:", "```", (error or "(no error message: it just didn't work as expected)").strip(), "```"]
    logs = log_tail(*LOGS_FOR.get(step_id, ()))
    if logs:
        parts += ["", "The program's recent log:", "```", logs, "```"]
    parts += ["", "The project's setup guide, if it helps: %s" % GUIDE_URL]
    return redact("\n".join(parts))
