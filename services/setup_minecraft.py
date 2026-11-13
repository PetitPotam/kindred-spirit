"""Kindred Spirit Setup: Minecraft, Fabric and the mod (#96), then saying hi to her once to check the whole chain.

The Setup app carries the mod for every Minecraft version a release supports (payload/mods/: the jars and the
release's versions.json, made by CI). This installs, for the version the player picks (the newest recommended):
  - Fabric Loader, with Fabric's official installer (needs Java: the Minecraft Launcher's own is used);
  - a launcher profile "Kindred Spirit (Fabric <version>)" with its own game folder (minecraft-kindred-<version>),
    so the player's other profiles, mods and worlds are untouched; launcher_profiles.json is backed up first;
  - Fabric API (from Modrinth, hash-checked) and the Kindred jar in that folder's mods/;
or, for another launcher (Prism, CurseForge, MultiMC...), the mod and Fabric API into a mods folder the player names.
The helpers are scripts/install_profile.py's (the same installer the terminal guide uses), so both stay one.

A friend who only joins a host's LAN world needs only this step. Standard library only.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import kindred_gateway as gw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import install_profile as ip  # noqa: E402  (finding Minecraft and Java, Fabric's installer, Fabric API)

LAUNCHER = "/Applications/Minecraft.app/Contents/MacOS/launcher"


def ss():
    import setup_steps
    return setup_steps


def mods_dir():
    """The mod files this Setup carries: payload/mods (the app), else the repository's build (development)."""
    pay = ss().PAYLOAD
    if pay and os.path.isdir(os.path.join(pay, "mods")):
        return os.path.join(pay, "mods")
    rt = ss().installed()
    if rt and os.path.isdir(os.path.join(rt["path"], "mods")):
        return os.path.join(rt["path"], "mods")
    return os.path.join(os.path.dirname(HERE), "mod", "build", "libs")


def versions():
    """[{"minecraft", "jar", "fabric_api"}], newest first: from versions.json, else from the jars' names."""
    d = mods_dir()
    try:
        with open(os.path.join(d, "versions.json"), encoding="utf-8") as fh:
            vs = [v for v in json.load(fh).get("versions", []) if os.path.exists(os.path.join(d, v.get("jar", "")))]
    except (OSError, ValueError, AttributeError):
        vs = []
        for jar in glob.glob(os.path.join(d, "kindred-spirit-*+*.jar")):
            m = re.match(r"kindred-spirit-(.+)\+(.+)\.jar$", os.path.basename(jar))
            if m and "-sources" not in jar:
                vs.append({"minecraft": m.group(2), "jar": os.path.basename(jar)})
    return sorted(vs, key=lambda v: [int(x) if x.isdigit() else 0 for x in v["minecraft"].split(".")], reverse=True)


def profile_names(mc):
    """The profile id and game folder for a version, as scripts/install_profile.py names them (1.21.1: the first)."""
    other = mc != "1.21.1"
    folder = ("minecraft-kindred" if sys.platform == "darwin" else ".minecraft-kindred") + ("-" + mc if other else "")
    return ip.PROFILE_ID + ("-" + mc if other else ""), os.path.join(os.path.dirname(ip.minecraft_dir()), folder)


def launcher_ready():
    """The launcher has run once (it writes launcher_profiles.json then), and isn't running now."""
    return os.path.exists(os.path.join(ip.minecraft_dir(), "launcher_profiles.json"))


def installed_for(mc):
    pid, game = profile_names(mc)
    try:
        with open(os.path.join(ip.minecraft_dir(), "launcher_profiles.json"), encoding="utf-8") as fh:
            prof = json.load(fh).get("profiles", {}).get(pid)
    except (OSError, ValueError):
        prof = None
    jars = glob.glob(os.path.join(game, "mods", "kindred-spirit-*.jar"))
    return bool(prof and jars and glob.glob(os.path.join(game, "mods", "fabric-api-*.jar"))), pid, game


def install(mc, jar_path):
    """Fabric Loader, the profile and its mods for Minecraft `mc` (what install_profile.py's main does)."""
    ip.MC_VERSION = mc
    pid, game = profile_names(mc)
    mc_dir = ip.minecraft_dir()
    profiles = os.path.join(mc_dir, "launcher_profiles.json")
    version_id = "fabric-loader-%s-%s" % (ip.LOADER, mc)
    if not os.path.exists(os.path.join(mc_dir, "versions", version_id, version_id + ".json")):
        java = ip.find_java()  # (exits with a message when there's none: caught by the caller)
        with tempfile.TemporaryDirectory() as tmp:
            inst = os.path.join(tmp, "fabric-installer.jar")
            ip.download(ip.INSTALLER, inst)
            subprocess.run([java, "-jar", inst, "client", "-dir", mc_dir, "-mcversion", mc, "-loader", ip.LOADER,
                            "-noprofile"], check=True, capture_output=True, timeout=600)
    put_mods(os.path.join(game, "mods"), mc, jar_path)
    if not os.path.exists(os.path.join(game, "options.txt")) and os.path.exists(os.path.join(mc_dir, "options.txt")):
        shutil.copy2(os.path.join(mc_dir, "options.txt"), os.path.join(game, "options.txt"))
    backup = profiles + ".before-kindred"
    if not os.path.exists(backup):
        shutil.copy2(profiles, backup)
    with open(profiles, encoding="utf-8") as fh:
        data = json.load(fh)
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    entry = data.setdefault("profiles", {}).get(pid, {"created": now})
    entry.update({"name": "Kindred Spirit (Fabric %s)" % mc, "type": "custom", "lastVersionId": version_id,
                  "gameDir": game, "lastUsed": now, "icon": "Grass"})
    data["profiles"][pid] = entry
    with open(profiles + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(profiles + ".tmp", profiles)
    return pid, game


def put_mods(mods, mc, jar_path):
    """Fabric API for `mc` (Modrinth, SHA-512 checked) and the Kindred jar, replacing older ones of each."""
    os.makedirs(mods, exist_ok=True)
    ip.MC_VERSION = mc
    url, name, sha = ip.fabric_api()
    for old in glob.glob(os.path.join(mods, "fabric-api-*.jar")):
        if os.path.basename(old) != name:
            os.remove(old)
    if not os.path.exists(os.path.join(mods, name)):
        ip.download(url, os.path.join(mods, name), sha)
    for old in glob.glob(os.path.join(mods, "kindred-spirit-*.jar")):
        os.remove(old)
    shutil.copy2(jar_path, mods)


# ---------------------------------------------------------------------- the steps

def step_minecraft():
    R = ss()
    vs = versions()
    st = R.load_state()
    chosen = st.get("minecraft") or (vs[0]["minecraft"] if vs else "")
    done, pid, game = installed_for(chosen) if chosen else (False, "", "")
    choices = [{"value": v["minecraft"], "label": "Minecraft %s, with a Kindred Spirit profile" % v["minecraft"],
                "recommended": i == 0,
                "note": ("The newest: what most players have. " if i == 0 else "For worlds made in %s. " % v["minecraft"])
                + ("Installed." if installed_for(v["minecraft"])[0] else "")} for i, v in enumerate(vs)]
    if vs:
        choices.append({"value": "folder", "label": "Into another launcher (Prism, CurseForge, MultiMC…)",
                        "note": "The mod and Fabric API go into that instance's mods folder; the instance needs Fabric "
                                "Loader for the same Minecraft version."})
    facts = [["Minecraft Launcher", "found" if launcher_ready() else "not found, or never opened"],
             ["Mod versions in this Setup", ", ".join(v["minecraft"] for v in vs) or "none (a development build)"]]
    if done:
        facts.append(["Profile", "Kindred Spirit (Fabric %s)" % chosen])
    return {
        "id": "minecraft", "title": "Minecraft",
        "why": "Pip lives in Minecraft Java Edition through a mod (Kindred Spirit) that runs with Fabric, a light "
               "mod loader. This adds a profile called \"Kindred Spirit\" to the Minecraft Launcher, with its own game "
               "folder, so your other worlds and mods stay as they are. Only joining a friend who hosts Pip on a LAN "
               "world? This is the only step you need.",
        "default": "The newest Minecraft (%s), as a new launcher profile. Quit the Minecraft Launcher first." %
                   (vs[0]["minecraft"] if vs else "?"),
        "facts": facts, "choices": choices, "chosen": chosen if any(c["value"] == chosen for c in choices) else
        (vs[0]["minecraft"] if vs else ""),
        "fields": [{"id": "folder", "label": "The instance's mods folder (drag it here from Finder, or paste its path)",
                    "type": "text", "for": ["folder"], "placeholder": "~/Library/Application Support/PrismLauncher/instances/…/minecraft/mods"},
                   {"id": "minecraft", "label": "Its Minecraft version", "type": "select", "for": ["folder"],
                    "options": [{"value": v["minecraft"], "label": v["minecraft"]} for v in vs],
                    "value": vs[0]["minecraft"] if vs else ""}],
        "actions": [{"id": "choose", "label": "Install", "primary": not done}] if vs else [],
        "status": "done" if done or st.get("mods_folder") else "todo",
        "summary": ("Installed for Minecraft %s." % chosen) if done else "Not installed yet.",
    }


def act_minecraft(action, body):
    R = ss()
    if action != "choose":
        raise R.SetupError("unknown action")
    vs = {v["minecraft"]: v for v in versions()}
    choice = str(body.get("choice") or "")
    if choice == "folder":
        mc = str(body.get("minecraft") or "")
        folder = os.path.expanduser(str(body.get("folder") or "").strip().strip("'\""))
        if mc not in vs:
            raise R.SetupError("Choose the instance's Minecraft version.")
        if not folder or os.path.basename(folder.rstrip("/")) != "mods" or not os.path.isdir(os.path.dirname(folder.rstrip("/"))):
            raise R.SetupError("Give the instance's \"mods\" folder (inside its minecraft folder).")
        try:
            put_mods(folder, mc, os.path.join(mods_dir(), vs[mc]["jar"]))
        except (OSError, StopIteration, ValueError) as e:
            raise R.SetupError("Couldn't put the mods there: %s" % e)
        R.save_state(mods_folder=R.tilde(folder), minecraft=mc)
        return R._result(True, "Done: Kindred Spirit and Fabric API are in that mods folder. Start the instance with "
                         "Fabric Loader for Minecraft %s." % mc)
    if choice not in vs:
        raise R.SetupError("Choose a Minecraft version.")
    if not launcher_ready():
        raise R.SetupError("Open the Minecraft Launcher once (and sign in), quit it, then press Install again.")
    if ip.launcher_running():
        raise R.SetupError("Quit the Minecraft Launcher first (it rewrites its profiles when it closes), then press Install.")
    try:
        pid, game = install(choice, os.path.join(mods_dir(), vs[choice]["jar"]))
    except SystemExit as e:  # install_profile's own messages ("Java not found...")
        raise R.SetupError("%s Open Minecraft %s once from the launcher (it brings its own Java), then try again."
                           % (e, choice))
    except subprocess.CalledProcessError as e:
        raise R.SetupError("Fabric's installer failed: %s" % (e.stderr or b"").decode("utf-8", "replace")[-600:])
    except (OSError, StopIteration, ValueError) as e:
        raise R.SetupError("Couldn't install: %s (is the internet reachable?)" % e)
    R.save_state(minecraft=choice, hello_since=time.strftime("%Y-%m-%d %H:%M:%S"))
    return R._result(True, "Installed: the profile \"Kindred Spirit (Fabric %s)\" is in the Minecraft Launcher." % choice,
                     "Its game folder: %s" % R.tilde(game))


def test_minecraft():
    R = ss()
    st = R.load_state()
    if st.get("mods_folder"):
        folder = os.path.expanduser(st["mods_folder"])
        ok = glob.glob(os.path.join(folder, "kindred-spirit-*.jar")) and glob.glob(os.path.join(folder, "fabric-api-*.jar"))
        return R._result(bool(ok), "Kindred Spirit and Fabric API are in %s." % st["mods_folder"] if ok else
                         "The mods aren't in %s any more: press Install again." % st["mods_folder"])
    mc = st.get("minecraft")
    if not mc:
        return R._result(False, "Nothing installed yet: choose a version and press Install.")
    done, pid, game = installed_for(mc)
    return R._result(done, "The profile \"Kindred Spirit (Fabric %s)\" is ready, with the mod and Fabric API." % mc if done
                     else "The profile or its mods are missing: press Install again.", R.tilde(game))


def brain_log():
    return os.path.join(gw.DIR, "logs", "brain.log")


def chain_since(since):
    """What her brain's log shows since `since` (a time): the game connecting, and her answering you."""
    seen = {"connected": None, "talked": None}
    try:
        with open(brain_log(), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                when = line[:19]
                if when < since:
                    continue
                if " game connected" in line:
                    seen["connected"] = when
                m = re.search(r" you: (.*) \| \w+: \[[^\]]*\](?: \{[^}]*\})? (.*)$", line)
                if m:
                    seen["talked"] = (m.group(1)[:80], m.group(2)[:120])
    except OSError:
        pass
    return seen


def step_hello():
    R = ss()
    st = R.load_state()
    seen = chain_since(st.get("hello_since") or "0000")
    done = bool(seen["connected"] and seen["talked"])
    mc = st.get("minecraft") or "?"
    return {
        "id": "hello", "title": "Say hi to her",
        "why": "The last check, with everything together: start Minecraft with the Kindred Spirit profile, open a "
               "world (a new one in Creative is quickest), and type \"hi Pip\" in the chat (T). She floats in beside "
               "you and answers. To talk by voice, hold V.",
        "default": "Press \"Open Minecraft\", choose \"Kindred Spirit (Fabric %s)\" next to Play, and say hi." % mc,
        "facts": [["The game connected to her brain", "yes, at %s" % seen["connected"][11:16] if seen["connected"] else "not yet"],
                  ["She answered you", "“%s” → “%s”" % seen["talked"] if seen["talked"] else "not yet"]],
        "actions": ([{"id": "open", "label": "Open Minecraft", "primary": not done}] if os.path.exists(LAUNCHER) else []),
        "status": "done" if done else "todo",
        "summary": "She answered you: everything works." if done else "Waiting for you to say hi in the game.",
    }


def act_hello(action, body):
    R = ss()
    if action != "open":
        raise R.SetupError("unknown action")
    if not os.path.exists(LAUNCHER):
        raise R.SetupError("The Minecraft Launcher isn't in Applications: install it from minecraft.net, then try again.")
    R.save_state(hello_since=time.strftime("%Y-%m-%d %H:%M:%S"))
    # started from here, not from the Dock: the game then asks for the microphone in this app's name (macOS gives the
    # launcher none of its own when it's started from the Dock, and the game records silence)
    subprocess.Popen([LAUNCHER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return R._result(True, "The Minecraft Launcher is opening. Choose \"Kindred Spirit (Fabric %s)\", press Play, "
                     "open a world and say hi to her. This page notices when she answers."
                     % (R.load_state().get("minecraft") or ""))


def test_hello():
    R = ss()
    st = R.load_state()
    seen = chain_since(st.get("hello_since") or "0000")
    if seen["connected"] and seen["talked"]:
        return R._result(True, "Everything works: the game reached her brain, and she answered “%s” with “%s”." %
                         seen["talked"])
    if seen["connected"]:
        return R._result(False, "The game reached her brain, but she hasn't answered yet: type \"hi Pip\" in the chat. "
                         "If she stays quiet, test her conversation's step again.")
    if not all(R.running().values()):
        return R._result(False, "She isn't awake: go back to \"Wake her up\" and press Start.")
    return R._result(False, "The game hasn't reached her brain yet. Is the profile \"Kindred Spirit\" the one playing, "
                     "and are you in a world?", R.log_tail("brain.log"))
