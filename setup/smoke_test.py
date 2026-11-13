#!/usr/bin/env python3
"""Checks a built Setup the way a player would use it, in a throwaway home folder.

    python3 setup/smoke_test.py setup/dist/Kindred-Spirit-Setup-0.3.0-macos-arm64.dmg
    python3 setup/smoke_test.py "setup/dist/Kindred Spirit Setup.app"
    python3 setup/smoke_test.py --models ...dmg     also download her models (~250 MB) and test her instincts, voice
                                                    and hearing: for a clean machine (CI), since her helpers use fixed
                                                    ports (8891, 8885, 8083) that a running Pip already has

It opens the app (without a browser), then through the Setup's own page API: chooses the computer's profile,
installs her brain, tests it, starts her (gateway, brain, dashboard), tests that, copies a help prompt and checks
it gives nothing private away, stops her and closes the Setup.

Nothing real is touched: HOME and KINDRED_HOME point to a temporary folder and every port is moved (the Setup
11541, the gateway 11537, the dashboard 11540, the brain 47911), so a Pip already running on this computer
is never met, stopped or replaced. Standard library only; macOS (hdiutil) for a .dmg.
"""
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

PORTS = {"setup": 11541, "gateway": 11537, "dashboard": 11540, "brain": 47911, "ai": 11599}
FAKE_KEY = "gsk_fake0000000000000000000000robin"  # a made-up key: the stand-in AI accepts anything
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def say(*a):
    print("--", *a, flush=True)


def free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def call(path, body=None, timeout=120):
    url = "http://127.0.0.1:%d%s" % (PORTS["setup"], path)
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def opened():
    """Where opening the app lands (the launcher opens /open): the Location it redirects to."""
    c = http.client.HTTPConnection("127.0.0.1", PORTS["setup"], timeout=60)
    c.request("GET", "/open")
    r = c.getresponse()
    assert r.status == 302, r.status
    return r.getheader("Location")


def step(state, sid):
    return next(s for s in state["steps"] if s["id"] == sid)


def app_from(path, work):
    """The .app itself, or copied out of the .dmg (as a player drags it to Applications)."""
    if path.endswith(".app"):
        return path
    mnt = os.path.join(work, "mnt")
    os.makedirs(mnt)
    subprocess.run(["hdiutil", "attach", "-quiet", "-nobrowse", "-readonly", "-mountpoint", mnt, path], check=True)
    try:
        names = os.listdir(mnt)
        assert "Applications" in names and "If macOS won't open it.txt" in names, names
        apps = [n for n in names if n.endswith(".app")]
        assert len(apps) == 1, names
        dest = os.path.join(work, "Applications", apps[0])
        os.makedirs(os.path.dirname(dest))
        subprocess.run(["ditto", os.path.join(mnt, apps[0]), dest], check=True)
    finally:
        subprocess.run(["hdiutil", "detach", "-quiet", mnt], check=False)
    return dest


MODEL_PORTS = {"embeddings": 8891, "kokoro": 8885, "whisper": 8083}


def wait_for(sid, minutes=20):
    """A step's download in the background, until it's done (or failed)."""
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        p = step(call("/api/setup/state"), sid).get("progress") or {}
        if p.get("state") in ("done", "failed"):
            assert p["state"] == "done", p
            return
        time.sleep(3)
    raise AssertionError("%s's download took over %d minutes" % (sid, minutes))


def main(argv):
    models = "--models" in argv
    argv = [a for a in argv if a != "--models"]
    if models:
        PORTS.update(MODEL_PORTS)
    if len(argv) != 1:
        raise SystemExit(__doc__)
    busy = [k for k, p in PORTS.items() if not free(p)]
    if busy:
        raise SystemExit("ports in use, for %s: stop what uses them first" % ", ".join(busy))
    work = tempfile.mkdtemp(prefix="kindred-smoke-")
    home = os.path.join(work, "riverrobin")  # a made-up user
    kh = os.path.join(home, ".kindred-spirit")
    os.makedirs(kh)
    with open(os.path.join(kh, "brain.toml"), "w", encoding="utf-8") as fh:  # her brain on the test's ports
        fh.write('[server]\nport = %d\n\n[gateway]\nurl = "http://127.0.0.1:%d/v1"\n' % (PORTS["brain"], PORTS["gateway"]))
    with open(os.path.join(kh, "gateway.json"), "w", encoding="utf-8") as fh:  # "Groq" is the stand-in AI here
        json.dump({"upstreams": {"groq": {"base": "http://127.0.0.1:%d/v1" % PORTS["ai"]}},
                   "stt": {"use": "none"}, "tts": {"use": "none"}, "embeddings": {"use": "none"}}, fh)

    env = {"HOME": home, "KINDRED_HOME": kh, "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "KINDRED_SETUP_NO_BROWSER": "1",
           "KINDRED_SETUP_PORT": str(PORTS["setup"]), "KINDRED_GATEWAY_PORT": str(PORTS["gateway"]),
           "KINDRED_DASHBOARD_PORT": str(PORTS["dashboard"]), "TMPDIR": work,
           "KINDRED_LAUNCH_AGENTS_DIR": os.path.join(work, "LaunchAgents")}  # never the real login items
    app = app_from(os.path.abspath(argv[0]), work)
    launcher = os.path.join(app, "Contents", "MacOS", "kindred-setup")
    # the stand-in AI runs on the app's own Python, like every other helper here (on GitHub's Macs, another Python
    # serving its first connection was held up for tens of seconds, or timed out)
    fake_ai = subprocess.Popen([os.path.join(app, "Contents", "Resources", "payload", "python", "bin", "python3"), "-I",
                                "-B", os.path.join(REPO, "brain", "tools", "fake_ai.py"), "--port", str(PORTS["ai"])],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if not free(PORTS["ai"]):
            break
        time.sleep(0.25)
    ok = False
    try:
        say("opening", os.path.basename(app))
        t = time.time()
        subprocess.run([launcher], env=env, check=True, timeout=60)
        say("the Setup answered in %.1f s" % (time.time() - t))
        hello = call("/api/setup/hello")
        assert hello["setup"] is True, hello
        state = call("/api/setup/state")
        assert state["mode"] == "app" and state["installed"] is None, state
        assert [s["id"] for s in state["steps"]] == ["computer", "install", "start", "ai", "thinking", "instincts", "voice",
                                                     "hearing", "minecraft", "hello", "login"], state["steps"]
        assert opened() == "/setup", "before setup, opening the app shows the steps"
        for sid, action, extra in [("computer", "choose", {"choice": "auto"}), ("computer", "test", {}),
                                   ("install", "install", {}), ("install", "test", {}),
                                   ("start", "start", {}), ("start", "test", {}),
                                   ("ai", "choose", {"choice": "groq", "key": FAKE_KEY}), ("ai", "test", {}),
                                   ("thinking", "choose", {"choice": "off"}), ("thinking", "choose", {"choice": "same"}),
                                   ] + ([("instincts", "choose", {"choice": "local"}), ("instincts", "wait", {}),
                                         ("instincts", "test", {}),
                                         ("voice", "choose", {"choice": "local_kokoro", "voice": "bf_lily"}),
                                         ("voice", "wait", {}), ("voice", "test", {}),
                                         ("hearing", "choose", {"choice": "local_whisper", "size": "tiny"}),
                                         ("hearing", "wait", {}), ("hearing", "test", {})] if models else
                                        [("instincts", "choose", {"choice": "none"}), ("instincts", "test", {}),
                                         ("voice", "choose", {"choice": "none"}), ("voice", "test", {}),
                                         ("hearing", "choose", {"choice": "none"}), ("hearing", "test", {})]) + [
                                   ("login", "choose", {"choice": "login"}), ("login", "test", {}),
                                   ("login", "choose", {"choice": "app"}), ("login", "test", {})]:
            t = time.time()
            if action == "wait":
                wait_for(sid)
                say("%s: downloaded (%.0f s)" % (sid, time.time() - t))
                continue
            r = call("/api/setup/run", dict(step=sid, action=action, **extra), timeout=300)
            say("%s / %s: %s (%.1f s)" % (sid, action, r["message"], time.time() - t))
            assert r["ok"], r
            if (sid, action) == ("login", "test") and extra == {}:
                item = os.path.join(work, "LaunchAgents", "io.github.petitpotam.kindredspirit.plist")
                say("  login item %s" % ("written" if os.path.exists(item) else "removed"))
        for path, want in [("/", "Kindred Dashboard"), ("/api/settings", '"gateway"'), ("/api/live", '"health"'),
                           ("/api/sessions", '"sessions"'), ("/setup", "Kindred Spirit Setup")]:
            with urllib.request.urlopen("http://127.0.0.1:%d%s" % (PORTS["dashboard"], path), timeout=20) as r:
                assert want in r.read().decode(), path
        say("her dashboard answers: its page, settings, live, sessions and the Setup steps")
        mc = step(call("/api/setup/state"), "minecraft")
        if mc["choices"]:  # the app carries the mod: install it into another launcher's (throwaway) mods folder
            mods = os.path.join(work, "PrismLauncher", "instances", "Robin", "minecraft", "mods")
            os.makedirs(mods)
            version = mc["choices"][0]["value"]
            r = call("/api/setup/run", {"step": "minecraft", "action": "choose", "choice": "folder",
                                        "minecraft": version, "folder": mods}, timeout=300)
            assert r["ok"], r
            assert call("/api/setup/run", {"step": "minecraft", "action": "test"})["ok"]
            say("the mod for Minecraft %s and Fabric API went into another launcher's mods folder: %s"
                % (version, ", ".join(sorted(os.listdir(mods)))))
        else:
            say("this build carries no mod jars: the Minecraft step wasn't tried")
        if models:
            req = urllib.request.Request("http://127.0.0.1:%d/api/setup/preview" % PORTS["setup"], method="POST",
                                         data=b'{"voice": "af_heart"}', headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                wav = r.read()
            assert wav[:4] == b"RIFF", wav[:40]
            say("\"Hear it\" played another voice: %d KB" % (len(wav) // 1024))
        assert opened() == "http://127.0.0.1:%d/" % PORTS["dashboard"], "once set up, opening the app opens her dashboard"
        say("opening the app again goes to her dashboard")
        state = call("/api/setup/state")
        assert state["dashboard"]["running"], state["dashboard"]
        # (saying hi needs Minecraft itself: not on a test machine)
        assert all(s["status"] == "done" for s in state["steps"] if s["id"] not in ("minecraft", "hello")), \
            [(s["id"], s["status"]) for s in state["steps"]]
        assert os.path.islink(os.path.join(home, "Library", "Application Support", "Kindred Spirit", "current"))
        assert oct(os.stat(os.path.join(kh, "secrets.env")).st_mode & 0o777) == "0o600"
        assert "GROQ_API_KEY=" + FAKE_KEY in open(os.path.join(kh, "secrets.env")).read()
        assert FAKE_KEY not in json.dumps(call("/api/setup/state")), "a key is never shown back"
        prompt = call("/api/setup/help", {"step": "start", "error": "Traceback in %s/x.py, key AIzaSyFAKE0000000000000000000000" % home})["prompt"]
        assert FAKE_KEY not in call("/api/setup/help", {"step": "ai"})["prompt"]
        assert home not in prompt and "AIzaSy" not in prompt and "Kindred Spirit Setup" in prompt, prompt
        say("help prompt: %d characters, nothing private in it" % len(prompt))
        r = call("/api/setup/run", {"step": "start", "action": "stop"})
        say("start / stop:", r["message"])
        ok = True
    finally:
        if not ok:
            for name in ("setup.out", "gateway.out", "brain.out", "dashboard.out"):
                p = os.path.join(kh, "logs", name)
                if os.path.exists(p):
                    print("\n===== %s\n%s" % (name, open(p, encoding="utf-8", errors="replace").read()[-3000:]))
            rt = os.path.join(home, "Library", "Application Support", "Kindred Spirit", "current", "kindred", "scripts", "stop.sh")
            if os.path.exists(rt):
                subprocess.run(["/bin/bash", rt], env=env, check=False)
        fake_ai.terminate()
        try:
            call("/api/setup/quit", {}, timeout=5)
        except Exception:
            pass
        for _ in range(40):  # (helpers take a moment to let go of their ports)
            busy = [k for k, p in PORTS.items() if not free(p)]
            if not busy:
                break
            time.sleep(0.25)
        if ok and busy:
            ok = False
            print("still running after stop: %s" % ", ".join(busy))
        if ok:
            shutil.rmtree(work, ignore_errors=True)
        else:
            print("kept for a look: %s" % work)
    say("passed" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
