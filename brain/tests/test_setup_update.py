"""Updates in the Setup (#97): the newest release for this chip, an update that installs the new program, the
matching mod jar and the new app together, and a way back. A fake GitHub, a fake disk image, a throwaway home."""
import os

import pytest

import gateway_stub  # noqa: F401  (puts services/ on the path)
import kindred_gateway as gw
import setup_minecraft as smc
import setup_steps
import setup_update as su


def release(tag, assets=("arm64", "x86_64"), pre=False, draft=False, body="What's new"):
    v = tag.lstrip("v")
    files = []
    for a in assets:
        name = "Kindred-Spirit-Setup-%s-macos-%s.dmg" % (v, a)
        files += [{"name": name, "size": 1000, "browser_download_url": "https://example.invalid/" + name},
                  {"name": name + ".sha256", "size": 90, "browser_download_url": "https://example.invalid/" + name + ".sha256"}]
    return {"tag_name": tag, "prerelease": pre, "draft": draft, "body": body, "assets": files}


def test_versions_compare_like_releases():
    order = ["0.2.0-preview", "0.2.1", "0.3.0-beta.1", "0.3.0-beta.2", "0.3.0-rc.1", "0.3.0", "0.10.0", "1.0.0"]
    assert sorted(reversed(order), key=su.version_key) == order
    assert su.newer("0.3.0", "0.3.0-rc.1") and not su.newer("0.3.0", "0.3.0")


def test_the_newest_release_with_a_setup_for_this_chip(monkeypatch):
    monkeypatch.setattr(su, "arch", lambda: "arm64")
    rels = [release("v0.4.0", draft=True), release("v0.3.1-beta.1", pre=True), release("v0.3.0"),
            release("v0.3.5", assets=("x86_64",)), release("v0.2.0-preview")]
    assert su.latest("0.2.0", rels)["version"] == "0.3.0"  # no drafts, no pre-releases, only with this chip's file
    assert su.latest("0.3.0-beta.1", rels)["version"] == "0.3.1-beta.1"  # someone on a pre-release gets them
    best = su.latest("0.2.0", rels)
    assert best["name"] == "Kindred-Spirit-Setup-0.3.0-macos-arm64.dmg" and best["sha_url"].endswith(".sha256")
    assert su.latest("0.2.0", [release("v0.2.0-preview", assets=())]) is None


@pytest.fixture
def home(tmp_path, monkeypatch):
    kh = tmp_path / ".kindred-spirit"
    (kh / "logs").mkdir(parents=True)
    for name, rel in (("DIR", ""), ("STATE", "gateway.json"), ("SECRETS", "secrets.env"), ("LOCK", ".lock")):
        monkeypatch.setattr(gw, name, str(kh / rel).rstrip("/"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("KINDRED_APP_DIR", str(tmp_path / "app"))
    monkeypatch.setattr(setup_steps, "PAYLOAD", "")
    monkeypatch.setattr(su, "arch", lambda: "arm64")
    monkeypatch.setattr(smc.ip, "launcher_running", lambda: False)
    restarts, mods = [], []
    monkeypatch.setattr(su.subprocess, "Popen", lambda cmd, **kw: restarts.append(cmd))
    monkeypatch.setattr(smc, "put_mods", lambda folder, mc, jar: mods.append((folder, mc, os.path.basename(jar))))
    return tmp_path, restarts, mods


def payload(where, version):
    (where / "python" / "bin").mkdir(parents=True)
    (where / "python" / "bin" / "python3").write_text("#!/bin/sh\n")
    (where / "python" / "bin" / "python3").chmod(0o755)
    (where / "kindred" / "scripts").mkdir(parents=True)
    (where / "mods").mkdir()
    (where / "mods" / ("kindred-spirit-%s+26.3.jar" % version)).write_text("jar")
    (where / "VERSION").write_text(version + "\n")
    return str(where)


def run_job(items):
    """The update's steps, one after the other (the File is already "downloaded")."""
    for item in items:
        if isinstance(item, su.downloads.Run):
            item.fn()


def test_an_update_moves_brain_mod_and_app_together_and_can_go_back(home, monkeypatch):
    tmp_path, restarts, mods = home
    setup_steps.install_runtime(payload(tmp_path / "old", "0.2.0"))
    setup_steps.save_state(minecraft="26.3")
    (tmp_path / ".kindred-spirit" / "brain.toml").write_text("# hers\n")
    monkeypatch.setattr(su, "fetch_json", lambda url: [release("v0.3.0", body="She can plant crops now.")])
    assert setup_steps.run("updates", "check")["message"].startswith("Version 0.3.0 is available")
    step = su.step_updates()
    assert step["actions"][0]["id"] == "update" and "plant crops" in step["notes"] and step["status"] == "todo"

    new_app = tmp_path / "mnt" / su.APP
    payload(new_app / "Contents" / "Resources" / "payload", "0.3.0")
    monkeypatch.setattr(su, "fetch_text", lambda url: "a" * 64 + "  Kindred-Spirit-Setup-0.3.0-macos-arm64.dmg\n")
    monkeypatch.setattr(su, "open_dmg", lambda dmg: (str(tmp_path / "mnt"), str(new_app)))
    monkeypatch.setattr(su, "close_dmg", lambda mnt: None)
    jobs = []
    monkeypatch.setattr(su.downloads, "start", lambda name, items: jobs.append(items))
    assert setup_steps.run("updates", "update")["ok"]
    items = jobs[0]
    assert items[0].sha256 == "a" * 64 and items[0].url.endswith("macos-arm64.dmg")
    run_job(items)
    assert setup_steps.installed()["version"] == "0.3.0"
    assert mods[-1][1:] == ("26.3", "kindred-spirit-0.3.0+26.3.jar")  # the matching jar, for her profile
    assert mods[-1][0].endswith(os.path.join("minecraft-kindred-26.3", "mods"))
    assert "stop.sh" in restarts[-1][-2] and "start.sh" in restarts[-1][-1]  # restarted in a process of its own
    assert (tmp_path / ".kindred-spirit" / "brain.toml").read_text() == "# hers\n"  # her settings untouched
    st = setup_steps.load_state()
    assert st["previous"] == "0.2.0" and st["updated"]["to"] == "0.3.0"
    assert set(su.kept_versions()) == {"0.3.0", "0.2.0"}

    step = su.step_updates()
    assert [a["id"] for a in step["actions"]] == ["check", "rollback"] and step["status"] == "done"
    r = setup_steps.run("updates", "rollback")
    assert r["ok"] and setup_steps.installed()["version"] == "0.2.0"
    assert mods[-1][1:] == ("26.3", "kindred-spirit-0.2.0+26.3.jar")
    assert setup_steps.load_state()["previous"] == "0.3.0"  # and forward again, if wanted


def test_only_two_versions_are_kept(home):
    tmp_path, _, _ = home
    for v in ("0.1.0", "0.2.0", "0.3.0"):
        setup_steps.install_runtime(payload(tmp_path / v, v))
    setup_steps.save_state(previous="0.2.0")
    su.prune()
    assert sorted(su.kept_versions()) == ["0.2.0", "0.3.0"]


def test_no_update_while_minecraft_runs_or_without_a_check(home, monkeypatch):
    tmp_path, _, _ = home
    setup_steps.install_runtime(payload(tmp_path / "old", "0.2.0"))
    assert "Check for updates" in setup_steps.run("updates", "update")["message"]
    setup_steps.save_state(update={"checked": "now", "latest": {"version": "0.3.0"}})
    monkeypatch.setattr(smc.ip, "launcher_running", lambda: True)
    assert "Quit Minecraft" in setup_steps.run("updates", "update")["message"]

    def offline(url):
        raise OSError("no network")
    monkeypatch.setattr(su, "fetch_json", offline)
    r = setup_steps.run("updates", "check")
    assert not r["ok"] and "Try again later" in r["message"]


def test_the_newest_already(home, monkeypatch):
    tmp_path, _, _ = home
    setup_steps.install_runtime(payload(tmp_path / "v", "0.3.0"))
    monkeypatch.setattr(su, "fetch_json", lambda url: [release("v0.3.0")])
    assert "newest version (0.3.0)" in setup_steps.run("updates", "check")["message"]
    assert su.step_updates()["status"] == "done" and su.step_updates()["notes"] is None
