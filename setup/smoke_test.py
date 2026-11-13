#!/usr/bin/env python3
"""Checks a built Setup the way a player would use it, in a throwaway home folder.

    python3 setup/smoke_test.py setup/dist/Kindred-Spirit-Setup-0.3.0-macos-arm64.dmg
    python3 setup/smoke_test.py "setup/dist/Kindred Spirit Setup.app"

It opens the app (without a browser), then through the Setup's own page API: chooses the computer's profile,
installs her brain, tests it, starts her (gateway, brain, dashboard), tests that, copies a help prompt and checks
it gives nothing private away, stops her and closes the Setup.

Nothing real is touched: HOME and KINDRED_HOME point to a temporary folder and every port is moved (the Setup
11541, the gateway 11537, the dashboard 11540, the brain 47911), so a Pip already running on this computer
is never met, stopped or replaced. Standard library only; macOS (hdiutil) for a .dmg.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

PORTS = {"setup": 11541, "gateway": 11537, "dashboard": 11540, "brain": 47911}


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


def main(argv):
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
    env = {"HOME": home, "KINDRED_HOME": kh, "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "KINDRED_SETUP_NO_BROWSER": "1",
           "KINDRED_SETUP_PORT": str(PORTS["setup"]), "KINDRED_GATEWAY_PORT": str(PORTS["gateway"]),
           "KINDRED_DASHBOARD_PORT": str(PORTS["dashboard"]), "TMPDIR": work}
    app = app_from(os.path.abspath(argv[0]), work)
    launcher = os.path.join(app, "Contents", "MacOS", "kindred-setup")
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
        assert [s["id"] for s in state["steps"]][:3] == ["computer", "install", "start"], state["steps"]
        for sid, action, extra in [("computer", "choose", {"choice": "auto"}), ("computer", "test", {}),
                                   ("install", "install", {}), ("install", "test", {}),
                                   ("start", "start", {}), ("start", "test", {})]:
            t = time.time()
            r = call("/api/setup/run", dict(step=sid, action=action, **extra))
            say("%s / %s: %s (%.1f s)" % (sid, action, r["message"], time.time() - t))
            assert r["ok"], r
        state = call("/api/setup/state")
        assert all(s["status"] == "done" for s in state["steps"]), [(s["id"], s["status"]) for s in state["steps"]]
        assert os.path.islink(os.path.join(home, "Library", "Application Support", "Kindred Spirit", "current"))
        assert oct(os.stat(os.path.join(kh, "secrets.env")).st_mode & 0o777) == "0o600"
        prompt = call("/api/setup/help", {"step": "start", "error": "Traceback in %s/x.py, key AIzaSyFAKE0000000000000000000000" % home})["prompt"]
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
        try:
            call("/api/setup/quit", {}, timeout=5)
        except Exception:
            pass
        time.sleep(1)
        busy = [k for k, p in PORTS.items() if not free(p)]
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
