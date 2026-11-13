"""Kindred Spirit Setup: updates (#97). Her brain, the mod and the Setup itself move together, to one release.

  check     GitHub Releases: the newest version (a pre-release only for someone already on one), its notes and its
            Setup for this Mac's chip (Kindred-Spirit-Setup-<version>-macos-<arch>.dmg and its .sha256)
  update    downloads that .dmg (progress, SHA-256, resume: downloads.py), installs its program as a new version
            next to the current one, restarts her on it, puts the matching mod jar into her Minecraft profile (or the
            mods folder chosen in the Setup), and replaces the Setup app with the new one
  roll back the previous version is kept: switch back to it, with its jar
Her settings, keys and memories in ~/.kindred-spirit are never touched. Two versions are kept; older ones go.
Standard library only (and macOS's hdiutil to open the .dmg).
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request

import downloads
import kindred_gateway as gw

REPO = "PetitPotam/kindred-spirit"
API = "https://api.github.com/repos/%s/releases?per_page=15" % REPO
APP = "Kindred Spirit Setup.app"


def ss():
    import setup_steps
    return setup_steps


def arch():
    import platform
    return "arm64" if platform.machine() == "arm64" else "x86_64"


def version_key(v):
    """0.3.0 > 0.3.0-rc.1 > 0.3.0-beta.2 > 0.2.1 (Semantic Versioning, good enough for our tags)."""
    main, _, pre = (v or "0").lstrip("v").partition("-")
    nums = [int(x) if x.isdigit() else 0 for x in main.split(".")] + [0, 0, 0]
    pre_parts = [(0, int(p)) if p.isdigit() else (1, p) for p in re.split(r"[.]", pre)] if pre else []
    return nums[:3], (1,) if not pre else (0,), pre_parts


def newer(a, b):
    return version_key(a) > version_key(b)


def fetch_json(url, opener=urllib.request.urlopen):
    req = urllib.request.Request(url, headers={"User-Agent": "kindred-spirit-setup", "Accept": "application/vnd.github+json"})
    with opener(req, timeout=20) as r:
        return json.loads(r.read())


def latest(current, releases=None):
    """The newest release with a Setup for this chip: {"version", "notes", "url", "size", "sha_url"}, or None."""
    releases = releases if releases is not None else fetch_json(API)
    on_pre = "-" in (current or "")
    name = None
    best = None
    for rel in releases:
        if rel.get("draft") or (rel.get("prerelease") and not on_pre):
            continue
        v = (rel.get("tag_name") or "").lstrip("v")
        name = "Kindred-Spirit-Setup-%s-macos-%s.dmg" % (v, arch())
        assets = {a["name"]: a for a in rel.get("assets") or []}
        if name in assets and name + ".sha256" in assets and (best is None or newer(v, best["version"])):
            best = {"version": v, "notes": (rel.get("body") or "")[:6000], "url": assets[name]["browser_download_url"],
                    "size": assets[name]["size"], "sha_url": assets[name + ".sha256"]["browser_download_url"],
                    "name": name}
    return best


def check():
    R = ss()
    rt = R.installed()
    cur = rt["version"] if rt else None
    try:
        rel = latest(cur)
    except Exception as e:  # offline, GitHub busy...: say so, keep the last answer
        R.save_state(update_error=str(e))
        raise R.SetupError("Couldn't ask GitHub for updates (%s). Try again later." % e)
    R.save_state(update={"checked": __import__("time").strftime("%Y-%m-%d %H:%M"), "latest": rel}, update_error="")
    return rel


def versions_dir():
    return os.path.join(ss().app_dir(), "versions")


def kept_versions():
    try:
        return sorted((v for v in os.listdir(versions_dir()) if not v.endswith((".part",)) and ".old-" not in v),
                      key=version_key, reverse=True)
    except OSError:
        return []


def open_dmg(dmg):
    """Mounts the .dmg read-only: (mount point, the app inside)."""
    mnt = tempfile.mkdtemp(prefix="kindred-update-")
    subprocess.run(["hdiutil", "attach", "-quiet", "-nobrowse", "-readonly", "-mountpoint", mnt, dmg], check=True)
    return mnt, os.path.join(mnt, APP)


def close_dmg(mnt):
    subprocess.run(["hdiutil", "detach", "-quiet", mnt], check=False)
    shutil.rmtree(mnt, ignore_errors=True)


def running_app():
    """This Setup app's own bundle (when it runs from one), to replace it."""
    pay = ss().PAYLOAD
    if pay and pay.endswith(os.path.join("Contents", "Resources", "payload")):
        return os.path.dirname(os.path.dirname(os.path.dirname(pay)))
    return None


def replace_app(new_app):
    """Puts the new Setup app where this one is (next to it first, then swapped). Skipped where it can't write."""
    old = running_app()
    if not old or not os.access(os.path.dirname(old), os.W_OK):
        return False
    tmp = old + ".new"
    shutil.rmtree(tmp, ignore_errors=True)
    subprocess.run(["ditto", new_app, tmp], check=True)
    gone = old + ".old"
    shutil.rmtree(gone, ignore_errors=True)
    os.replace(old, gone)
    os.replace(tmp, old)
    shutil.rmtree(gone, ignore_errors=True)
    return True


def point_current(version):
    cur = os.path.join(ss().app_dir(), "current")
    tmp = cur + ".new"
    if os.path.lexists(tmp):
        os.remove(tmp)
    os.symlink(os.path.join("versions", version), tmp)
    os.replace(tmp, cur)


def switch_to(version, previous):
    """Points "current" at an installed version, puts its mod jar in place and restarts her on it. The restart runs
    in a process of its own: when this runs inside her dashboard, stopping her stops this very process."""
    R = ss()
    point_current(version)
    R.save_state(installed=version, previous=previous)
    rt = R.installed()
    mods = refresh_mods(rt)
    scripts = os.path.join(rt["path"], "kindred", "scripts")
    with open(os.path.join(gw.DIR, "logs", "update.out"), "ab") as log:
        subprocess.Popen(["/bin/bash", "-c", 'sleep 1; "$1"; "$2" --background', "restart",
                          os.path.join(scripts, "stop.sh"), os.path.join(scripts, "start.sh")],
                         env=R.script_env(rt), cwd=os.path.join(rt["path"], "kindred"), stdout=log,
                         stderr=subprocess.STDOUT, start_new_session=True)
    return mods


def refresh_mods(rt):
    """The new version's jar for the Minecraft the player chose, where the Setup installed the mod."""
    import setup_minecraft as smc
    R = ss()
    st = R.load_state()
    mc = st.get("minecraft")
    if not mc:
        return "no Minecraft profile was set up, so no mod to update"
    vs = {v["minecraft"]: v for v in smc.versions_in(os.path.join(rt["path"], "mods"))}
    if mc not in vs:
        return "this version has no mod for Minecraft %s" % mc
    jar = os.path.join(rt["path"], "mods", vs[mc]["jar"])
    folder = os.path.expanduser(st["mods_folder"]) if st.get("mods_folder") else os.path.join(smc.profile_names(mc)[1], "mods")
    smc.put_mods(folder, mc, jar)
    return "the mod for Minecraft %s is now %s" % (mc, vs[mc]["jar"])


def prune():
    """Keeps the version in use and the one before; removes older ones."""
    R = ss()
    keep = {R.installed()["version"] if R.installed() else None, R.load_state().get("previous")}
    for v in kept_versions():
        if v not in keep:
            shutil.rmtree(os.path.join(versions_dir(), v), ignore_errors=True)


def do_update(rel):
    """The whole update, as one background job (the page shows its progress)."""
    R = ss()
    sha = fetch_text(rel["sha_url"]).split()[0]
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise IOError("the release's .sha256 file isn't a SHA-256")
    dmg = os.path.join(gw.DIR, "updates", rel["name"])
    state = {"previous": R.installed()["version"]}

    def install():
        mnt, app = open_dmg(dmg)
        try:
            R.install_runtime(os.path.join(app, "Contents", "Resources", "payload"))
            state["app"] = replace_app(app)
        finally:
            close_dmg(mnt)

    def restart():
        R.save_state(previous=state["previous"])
        prune()
        try:
            os.remove(dmg)
        except OSError:
            pass
        mods = switch_to(rel["version"], state["previous"])  # (her restart starts a second later, in its own process)
        R.save_state(updated={"to": rel["version"], "from": state["previous"], "app": state.get("app"), "mods": mods})

    return [downloads.File(rel["url"], dmg, sha, rel["size"], "Kindred Spirit Setup %s" % rel["version"]),
            downloads.Run(install, "installing version %s" % rel["version"], 20 << 20),
            downloads.Run(restart, "waking her up on it", 5 << 20)]


def fetch_text(url, opener=urllib.request.urlopen):
    with opener(urllib.request.Request(url, headers={"User-Agent": "kindred-spirit-setup"}), timeout=20) as r:
        return r.read(4096).decode("ascii", "replace")


# ---------------------------------------------------------------------- the step

def step_updates():
    R = ss()
    st = R.load_state()
    rt = R.installed()
    cur = rt["version"] if rt else None
    found = (st.get("update") or {}).get("latest")
    can = bool(found and cur and newer(found["version"], cur))
    prev = st.get("previous") if st.get("previous") in kept_versions() else None
    actions = [{"id": "check", "label": "Check for updates", "primary": not can}]
    if can:
        actions.insert(0, {"id": "update", "label": "Update to %s" % found["version"], "primary": True})
    if prev and prev != cur:
        actions.append({"id": "rollback", "label": "Go back to %s" % prev})
    facts = [["Installed", cur or "not yet"],
             ["Newest", (found["version"] if found else "?") + (" (checked %s)" % st["update"]["checked"] if st.get("update") else "")]]
    if st.get("updated"):
        u = st["updated"]
        facts.append(["Last update", "to %s; %s%s" % (u["to"], u.get("mods") or "",
                                                      "; the Setup app was replaced too" if u.get("app") else "")])
    return {
        "id": "updates", "title": "Updates",
        "why": "New versions of Pip come as releases on GitHub. Her brain, the mod and this Setup must be the same "
               "version, so they're updated together, in one go. Your settings, keys and memories stay as they are, "
               "and the version before is kept, so you can go back to it.",
        "default": "Check now and then (opening the Setup is a good moment). Close Minecraft before updating.",
        "facts": facts, "actions": actions if rt else [],
        "notes": found["notes"] if can else None,
        "progress": _progress(),
        "status": "done" if cur and not can else "todo",
        "summary": ("Version %s is available." % found["version"]) if can else
                   ("Up to date." if found and cur else "Not checked yet."),
    }


def _progress():
    st = downloads.status("update")
    return None if st["state"] == "idle" else {"state": st["state"], "percent": st.get("percent", 0),
                                               "text": st.get("error") or st.get("text", "")}


def act_updates(action, body):
    R = ss()
    if not R.installed():
        raise R.SetupError("Install her brain first.")
    if action == "check":
        rel = check()
        cur = R.installed()["version"]
        if rel and newer(rel["version"], cur):
            return R._result(True, "Version %s is available (you have %s): see what's new, then press Update." %
                             (rel["version"], cur))
        return R._result(True, "You have the newest version (%s)." % cur)
    if action == "update":
        rel = (R.load_state().get("update") or {}).get("latest")
        if not rel or not newer(rel["version"], R.installed()["version"]):
            raise R.SetupError("Nothing newer to install: press \"Check for updates\" first.")
        import setup_minecraft as smc
        if smc.ip.launcher_running():
            raise R.SetupError("Quit Minecraft (and its launcher) first, then press Update.")
        downloads.start("update", do_update(rel))
        return R._result(True, "Updating to %s in the background: the bar shows how far it is." % rel["version"])
    if action == "rollback":
        st = R.load_state()
        prev = st.get("previous")
        if not prev or prev not in kept_versions():
            raise R.SetupError("There's no earlier version to go back to.")
        mods = switch_to(prev, R.installed()["version"])
        return R._result(True, "Back on version %s; %s." % (prev, mods))
    raise R.SetupError("unknown action")


def test_updates():
    R = ss()
    rt = R.installed()
    if not rt:
        return R._result(False, "Install her brain first.")
    up = R.running()
    return R._result(all(up.values()), "Version %s is installed and running." % rt["version"] if all(up.values())
                     else "Version %s is installed, but not everything is running: wake her up." % rt["version"])
