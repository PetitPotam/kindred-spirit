#!/usr/bin/env python3
"""Adds a "Kindred Spirit (Fabric 1.21.1)" profile to the official Minecraft Launcher.

    python3 scripts/install_profile.py                    install or update (the launcher must be closed)
    python3 scripts/install_profile.py --minecraft 26.3   for another Minecraft version the mod supports
    python3 scripts/install_profile.py --dry-run          show what it would do

What it does, and nothing more:
  1. Installs Fabric Loader for that Minecraft version with Fabric's official installer (versions/ folder).
  2. Creates a separate game folder (minecraft-kindred next to your minecraft folder) so this
     profile has its own mods, settings and worlds; your other profiles are not touched. Another
     Minecraft version gets a folder and profile of its own (minecraft-kindred-26.3), so a world is
     never opened in the wrong game.
  3. Puts Fabric API (from Modrinth, hash-checked) and the Kindred Spirit jar in its mods folder.
  4. Copies your options.txt there the first time, so keys and video settings feel the same.
  5. Adds the profile to launcher_profiles.json, after saving a backup next to it.

Standard library only. Needs Java to run Fabric's installer (any Java 17+).
"""
import argparse
import base64
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

MC_VERSION = "1.21.1"
LOADER = "0.20.1"
INSTALLER = "https://maven.fabricmc.net/net/fabricmc/fabric-installer/1.1.2/fabric-installer-1.1.2.jar"
PROFILE_ID = "kindred-spirit"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "kindred-spirit-installer/0.1"}


def minecraft_dir():
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "minecraft")
    if sys.platform.startswith("win"):
        return os.path.join(os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming")), ".minecraft")
    return os.path.join(home, ".minecraft")


def find_java():
    cands = [os.path.join(os.environ["JAVA_HOME"], "bin", "java")] if os.environ.get("JAVA_HOME") else []
    cands += ["/opt/homebrew/opt/openjdk@25/bin/java", "/opt/homebrew/opt/openjdk@21/bin/java", shutil.which("java") or ""]
    cands += sorted(glob.glob(os.path.join(minecraft_dir(), "runtime", "*", "*", "*", "jre.bundle", "Contents", "Home", "bin", "java")))
    cands += sorted(glob.glob(os.path.join(minecraft_dir(), "runtime", "*", "*", "*", "bin", "java*")))
    for c in cands:
        if c and os.path.exists(c):
            try:
                if subprocess.run([c, "-version"], capture_output=True, timeout=20).returncode == 0:
                    return c
            except OSError:
                continue
    sys.exit("Java not found. macOS: brew install openjdk@25 (or set JAVA_HOME).")


def download(url, dest, sha512=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        data = r.read()
    if sha512 and hashlib.sha512(data).hexdigest() != sha512:
        sys.exit("Checksum mismatch for %s: not installing it." % url)
    with open(dest, "wb") as fh:
        fh.write(data)


def fabric_api():
    q = 'game_versions=["%s"]&loaders=["fabric"]' % MC_VERSION
    url = "https://api.modrinth.com/v2/project/fabric-api/version?" + urllib.parse.quote(q, safe="=&")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        versions = json.load(r)
    v = next(v for v in versions if v.get("version_type") == "release")
    f = next(f for f in v["files"] if f.get("primary")) if any(f.get("primary") for f in v["files"]) else v["files"][0]
    return f["url"], f["filename"], f["hashes"]["sha512"]


def mod_jar():
    # one jar per Minecraft version (mod/versions/): the one for this profile's Minecraft
    jars = glob.glob(os.path.join(ROOT, "mod", "build", "libs", "kindred-spirit-*+%s.jar" % MC_VERSION))
    if not jars:
        sys.exit("Build the mod first:  cd mod && ./gradlew :%s:build" % MC_VERSION)
    return max(jars, key=os.path.getmtime)


def launcher_running():
    try:
        if sys.platform == "darwin":
            return subprocess.run(["pgrep", "-f", "Minecraft.app/Contents/MacOS/launcher"], capture_output=True).returncode == 0
        if sys.platform.startswith("win"):
            out = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
            return "MinecraftLauncher.exe" in out or "Minecraft.exe" in out
        return subprocess.run(["pgrep", "-f", "minecraft-launcher"], capture_output=True).returncode == 0
    except OSError:
        return False


def main():
    global MC_VERSION
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--game-dir", help="where this profile keeps its mods and worlds")
    ap.add_argument("--minecraft", default=MC_VERSION,
                    help="the Minecraft version (one of mod/versions/, default %s)" % MC_VERSION)
    a = ap.parse_args()
    supported = sorted(os.listdir(os.path.join(ROOT, "mod", "versions")))
    if a.minecraft not in supported:
        sys.exit("Kindred Spirit is made for Minecraft %s, not %s." % (", ".join(supported), a.minecraft))
    other = a.minecraft != MC_VERSION  # (another version: its own folder and profile, next to the default one)
    MC_VERSION = a.minecraft
    profile_id = PROFILE_ID + ("-" + MC_VERSION if other else "")

    mc = minecraft_dir()
    folder = ("minecraft-kindred" if sys.platform == "darwin" else ".minecraft-kindred") + ("-" + MC_VERSION if other else "")
    game = a.game_dir or os.path.join(os.path.dirname(mc), folder)
    profiles = os.path.join(mc, "launcher_profiles.json")
    version_id = "fabric-loader-%s-%s" % (LOADER, MC_VERSION)
    jar = mod_jar()
    print("Minecraft folder:   ", mc)
    print("Profile game folder:", game)
    print("Fabric version:     ", version_id)
    print("Kindred Spirit jar: ", os.path.basename(jar))
    if not os.path.exists(profiles):
        sys.exit("No launcher_profiles.json: open the Minecraft Launcher once, then run this again.")
    if launcher_running():
        sys.exit("Please quit the Minecraft Launcher first (it rewrites its profiles when it closes).")
    if a.dry_run:
        return 0

    if not os.path.exists(os.path.join(mc, "versions", version_id, version_id + ".json")):
        print("Installing Fabric Loader %s..." % LOADER)
        with tempfile.TemporaryDirectory() as tmp:
            inst = os.path.join(tmp, "fabric-installer.jar")
            download(INSTALLER, inst)
            subprocess.run([find_java(), "-jar", inst, "client", "-dir", mc, "-mcversion", MC_VERSION,
                            "-loader", LOADER, "-noprofile"], check=True)

    mods = os.path.join(game, "mods")
    os.makedirs(mods, exist_ok=True)
    url, name, sha = fabric_api()
    for old in glob.glob(os.path.join(mods, "fabric-api-*.jar")):
        if os.path.basename(old) != name:
            os.remove(old)
    if not os.path.exists(os.path.join(mods, name)):
        print("Downloading", name)
        download(url, os.path.join(mods, name), sha)
    for old in glob.glob(os.path.join(mods, "kindred-spirit-*.jar")):
        os.remove(old)
    shutil.copy2(jar, mods)
    if not os.path.exists(os.path.join(game, "options.txt")) and os.path.exists(os.path.join(mc, "options.txt")):
        shutil.copy2(os.path.join(mc, "options.txt"), os.path.join(game, "options.txt"))
        print("Copied your options.txt (keys, video settings)")

    backup = profiles + ".before-kindred"
    if not os.path.exists(backup):
        shutil.copy2(profiles, backup)
    with open(profiles, encoding="utf-8") as fh:
        data = json.load(fh)
    with open(os.path.join(ROOT, "mod", "src", "main", "resources", "assets", "kindredspirit", "icon.png"), "rb") as fh:
        icon = "data:image/png;base64," + base64.b64encode(fh.read()).decode()
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    entry = data.setdefault("profiles", {}).get(profile_id, {"created": now})
    entry.update({"name": "Kindred Spirit (Fabric %s)" % MC_VERSION, "type": "custom", "lastVersionId": version_id,
                  "gameDir": game, "icon": icon, "lastUsed": now})
    data["profiles"][profile_id] = entry
    tmp = profiles + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, profiles)
    print("\nDone. In the Minecraft Launcher pick \"Kindred Spirit (Fabric %s)\" and press Play." % MC_VERSION)
    print("(Backup of your profiles: %s)" % backup)
    return 0


if __name__ == "__main__":
    sys.exit(main())
