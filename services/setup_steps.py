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
Nothing outside those two folders is touched by these steps.

Standard library only, like the dashboard.
"""
import json
import os
import platform
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
from kindred import hardware  # noqa: E402

PAYLOAD = os.environ.get("KINDRED_SETUP_PAYLOAD") or ""  # the app's own copy: python/, kindred/, VERSION
DASHBOARD_PORT = int(os.environ.get("KINDRED_DASHBOARD_PORT", "11440"))
GUIDE_URL = "https://github.com/PetitPotam/kindred-spirit/blob/main/docs/SETUP.md"
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
        "links": ([{"label": "Open the dashboard", "url": "http://127.0.0.1:%d/" % DASHBOARD_PORT}] if up["dashboard"] else []),
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
    return _result(True, "She's awake: the gateway, her brain and the dashboard are running.", out)


def test_start():
    if not installed():
        return _result(False, "Install her brain first (the step before).")
    up = running()
    if all(up.values()):
        return _result(True, "Everything answers: the gateway, her brain (port %d) and the dashboard." % brain_port())
    missing = [k for k, v in up.items() if not v]
    return _result(False, "Not answering: %s. Press Start; if it still fails, copy a help prompt." % ", ".join(missing),
                   log_tail("gateway.out", "brain.out", "dashboard.out"))


STEPS = {
    "computer": (step_computer, act_computer, test_computer),
    "install": (step_install, act_install, test_install),
    "start": (step_start, act_start, test_start),
}
LOGS_FOR = {"computer": (), "install": ("setup.out",), "start": ("gateway.out", "brain.out", "dashboard.out")}


def overview():
    steps = []
    for sid, (show, _, _) in STEPS.items():
        try:
            steps.append(show())
        except Exception as e:  # one broken step must not hide the others
            steps.append({"id": sid, "title": sid, "why": "", "status": "problem", "summary": str(e), "actions": []})
    rt = installed()
    return {"version": own_version(), "mode": "app" if PAYLOAD else "dashboard",
            "installed": rt["version"] if rt else None, "home": tilde(gw.DIR), "guide": GUIDE_URL, "steps": steps}


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
