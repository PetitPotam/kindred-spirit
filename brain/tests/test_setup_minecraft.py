"""Minecraft in the Setup (#96): a launcher profile per Minecraft version with its own folder, the matching jar
from the release, another launcher's mods folder, and the "say hi" check. A throwaway home with a fake Minecraft
folder; Fabric's installer and Modrinth are stand-ins (no network)."""
import json
import os
from pathlib import Path

import pytest

import gateway_stub  # noqa: F401  (puts services/ on the path)
import kindred_gateway as gw
import setup_minecraft as smc
import setup_steps


@pytest.fixture
def home(tmp_path, monkeypatch):
    kh = tmp_path / ".kindred-spirit"
    (kh / "logs").mkdir(parents=True)
    for name, rel in (("DIR", ""), ("STATE", "gateway.json"), ("SECRETS", "secrets.env"), ("LOCK", ".lock")):
        monkeypatch.setattr(gw, name, str(kh / rel).rstrip("/"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("KINDRED_APP_DIR", str(tmp_path / "app"))
    # the app's payload: the mod for two Minecraft versions and the release's versions.json
    pay = tmp_path / "payload"
    (pay / "mods").mkdir(parents=True)
    for mc in ("1.21.1", "26.3"):
        (pay / "mods" / ("kindred-spirit-0.3.0+%s.jar" % mc)).write_bytes(b"jar " + mc.encode())
    (pay / "mods" / "versions.json").write_text(json.dumps({"mod_version": "0.3.0", "versions": [
        {"minecraft": "1.21.1", "jar": "kindred-spirit-0.3.0+1.21.1.jar", "fabric_api": "0.116.18+1.21.1", "java": 21},
        {"minecraft": "26.3", "jar": "kindred-spirit-0.3.0+26.3.jar", "fabric_api": "0.166.2+26.3", "java": 25}]}))
    monkeypatch.setattr(setup_steps, "PAYLOAD", str(pay))
    # Fabric's installer, Java and Modrinth, without the network
    calls = []
    monkeypatch.setattr(smc.ip, "launcher_running", lambda: False)
    monkeypatch.setattr(smc.ip, "find_java", lambda: "/usr/bin/java")
    monkeypatch.setattr(smc.ip, "fabric_api", lambda: ("https://cdn.modrinth.com/x", "fabric-api-%s.jar" % smc.ip.MC_VERSION, "0" * 128))
    monkeypatch.setattr(smc.ip, "download", lambda url, dest, sha=None: (calls.append(url), open(dest, "wb").write(b"x")))

    def fabric(cmd, **kw):
        calls.append(cmd)
        mc_dir, mc, loader = cmd[cmd.index("-dir") + 1], cmd[cmd.index("-mcversion") + 1], cmd[cmd.index("-loader") + 1]
        vid = "fabric-loader-%s-%s" % (loader, mc)
        os.makedirs(os.path.join(mc_dir, "versions", vid))
        open(os.path.join(mc_dir, "versions", vid, vid + ".json"), "w").write("{}")
    monkeypatch.setattr(smc.subprocess, "run", fabric)
    return tmp_path, calls


def minecraft(tmp_path):
    from pathlib import Path
    mc = Path(smc.ip.minecraft_dir())  # (~/Library/Application Support/minecraft on macOS, ~/.minecraft on Linux)
    mc.mkdir(parents=True)
    (mc / "launcher_profiles.json").write_text('{"profiles": {"mine": {"name": "My modpack"}}}')
    return mc


def test_the_newest_minecraft_is_recommended(home):
    s = setup_minecraft_step()
    assert [c["value"] for c in s["choices"]] == ["26.3", "1.21.1", "folder"] and s["choices"][0]["recommended"]
    assert s["chosen"] == "26.3" and "friend" in s["why"]


def setup_minecraft_step():
    return smc.step_minecraft()


def test_the_launcher_must_have_run_once_and_be_closed(home, monkeypatch):
    tmp_path, _ = home
    r = setup_steps.run("minecraft", "choose", {"choice": "26.3"})
    assert not r["ok"] and "Open the Minecraft Launcher once" in r["message"]
    minecraft(tmp_path)
    monkeypatch.setattr(smc.ip, "launcher_running", lambda: True)
    r = setup_steps.run("minecraft", "choose", {"choice": "26.3"})
    assert not r["ok"] and "Quit the Minecraft Launcher" in r["message"]


def test_a_profile_per_version_with_its_own_folder_and_the_matching_jar(home):
    tmp_path, calls = home
    mc = minecraft(tmp_path)
    r = setup_steps.run("minecraft", "choose", {"choice": "26.3"})
    assert r["ok"], r
    profiles = json.loads((mc / "launcher_profiles.json").read_text())["profiles"]
    assert profiles["mine"] == {"name": "My modpack"}  # the player's own profiles are untouched
    p = profiles["kindred-spirit-26.3"]
    assert p["lastVersionId"].endswith("-26.3") and p["gameDir"].endswith("minecraft-kindred-26.3")
    mods = Path(smc.profile_names("26.3")[1]) / "mods"
    assert mods.parent.name.endswith("minecraft-kindred-26.3")
    assert sorted(os.listdir(mods)) == ["fabric-api-26.3.jar", "kindred-spirit-0.3.0+26.3.jar"]
    assert (mods / "kindred-spirit-0.3.0+26.3.jar").read_bytes() == b"jar 26.3"
    assert (mc / "launcher_profiles.json.before-kindred").exists()
    assert setup_steps.run("minecraft", "test")["ok"] and smc.step_minecraft()["status"] == "done"
    # 1.21.1 keeps the first profile's names (as scripts/install_profile.py has them), next to 26.3's
    assert setup_steps.run("minecraft", "choose", {"choice": "1.21.1"})["ok"]
    profiles = json.loads((mc / "launcher_profiles.json").read_text())["profiles"]
    assert {"kindred-spirit", "kindred-spirit-26.3", "mine"} <= set(profiles)
    assert profiles["kindred-spirit"]["gameDir"] == smc.profile_names("1.21.1")[1]


def test_another_launchers_mods_folder(home):
    tmp_path, _ = home
    mods = tmp_path / "PrismLauncher" / "instances" / "Robin" / "minecraft" / "mods"
    r = setup_steps.run("minecraft", "choose", {"choice": "folder", "minecraft": "1.21.1", "folder": str(mods.parent)})
    assert not r["ok"] and "mods" in r["message"]  # not a mods folder
    mods.mkdir(parents=True)
    (mods / "kindred-spirit-0.1.0+1.21.1.jar").write_bytes(b"old")
    r = setup_steps.run("minecraft", "choose", {"choice": "folder", "minecraft": "1.21.1", "folder": str(mods)})
    assert r["ok"], r
    assert sorted(os.listdir(mods)) == ["fabric-api-1.21.1.jar", "kindred-spirit-0.3.0+1.21.1.jar"]  # the old one replaced
    assert setup_steps.run("minecraft", "test")["ok"]


def test_saying_hi_is_seen_in_her_brains_log(home, monkeypatch):
    tmp_path, _ = home
    log = tmp_path / ".kindred-spirit" / "logs" / "brain.log"
    setup_steps.save_state(hello_since="2026-11-13 20:00:00", minecraft="26.3")
    log.write_text("2026-11-13 19:00:00,000 INFO game connected\n"  # before: doesn't count
                   "2026-11-13 19:00:05,000 INFO you: old | Pip: [happy] old answer\n")
    s = smc.step_hello()
    assert s["status"] == "todo" and s["facts"][0][1] == "not yet"
    monkeypatch.setattr(setup_steps, "running", lambda: {"gateway": True, "brain": True, "dashboard": True})
    assert "hasn't reached her brain" in setup_steps.run("hello", "test")["message"]
    with open(log, "a") as fh:
        fh.write("2026-11-13 20:01:00,000 INFO game connected\n2026-11-13 20:01:00,100 INFO mod 0.3.0 on Minecraft 26.3\n")
    assert "hasn't answered yet" in setup_steps.run("hello", "test")["message"]
    with open(log, "a") as fh:
        fh.write("2026-11-13 20:01:09,000 INFO you: hi Pip | Pip: [happy] {hop} Hello, Robin! Shall we explore?\n")
    r = setup_steps.run("hello", "test")
    assert r["ok"] and "Hello, Robin" in r["message"] and smc.step_hello()["status"] == "done"


def test_open_minecraft_starts_the_launcher_from_the_setup(home, monkeypatch):
    tmp_path, _ = home
    launcher = tmp_path / "launcher"
    monkeypatch.setattr(smc, "LAUNCHER", str(launcher))
    assert not setup_steps.run("hello", "open")["ok"]  # not installed
    launcher.write_text("")
    started = []
    monkeypatch.setattr(smc.subprocess, "Popen", lambda cmd, **kw: started.append((cmd, kw.get("start_new_session"))))
    r = setup_steps.run("hello", "open")
    assert r["ok"] and started == [([str(launcher)], True)] and setup_steps.load_state()["hello_since"]


def test_a_development_build_without_jars_says_so(home, monkeypatch, tmp_path):
    monkeypatch.setattr(setup_steps, "PAYLOAD", str(tmp_path / "empty"))
    monkeypatch.setattr(smc, "HERE", str(tmp_path / "nowhere" / "services"))
    s = smc.step_minecraft()
    assert s["choices"] == [] and s["actions"] == [] and "development build" in s["facts"][1][1]


def test_a_new_profile_brings_the_blueprints_you_already_have(home):
    """#175: the 26.3 profile started with no blueprints while the 1.21.1 one had 253; installing copies them over
    (same computer, nothing downloaded), and never over a profile that already has its own."""
    tmp_path, _ = home
    minecraft(tmp_path)  # (a launcher that has run once)
    old = Path(smc.profile_names("1.21.1")[1]) / "config" / "kindredspirit" / "blueprints"  # (".minecraft-kindred" on Linux)
    old.mkdir(parents=True)
    (old / "village_taiga_medium_house_1.nbt").write_bytes(b"nbt")
    (old / "circle_10x10.litematic").write_bytes(b"lite")
    (old / "catalogue.json").write_text("{}")
    (old / ".trash").mkdir()
    (old / ".trash" / "gone.nbt").write_bytes(b"x")
    smc.install("26.3", str(tmp_path / "payload" / "mods" / "kindred-spirit-0.3.0+26.3.jar"))
    new = Path(smc.profile_names("26.3")[1]) / "config" / "kindredspirit" / "blueprints"
    assert (new / "village_taiga_medium_house_1.nbt").exists() and (new / "circle_10x10.litematic").exists()
    assert not (new / ".trash").exists(), "what you threw away stays away"
    (old / "another.nbt").write_bytes(b"nbt")
    assert smc.carry_blueprints(smc.profile_names("26.3")[1]) == 0, "never over one that has its own"
    assert not (new / "another.nbt").exists()
