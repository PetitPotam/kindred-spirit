# Testing on every system

Most of us have one computer. These checks show whether Kindred Spirit installs and runs on the others too:
macOS on Apple silicon and on Intel, Linux and Windows. They run on clean machines, with no AI key (a stand-in AI,
`brain/tools/fake_ai.py`, answers her) and without touching your own Pip.

## What is checked, and where

| | macOS, Apple silicon | macOS, Intel | Linux (Ubuntu) | Windows |
|---|---|---|---|---|
| **Kindred Spirit Setup**: build the app, install and start her from the `.dmg` | ✅ | ✅ (built and run on Intel) | not yet (#81) | not yet (#40) |
| **Her brain** with `scripts/setup.sh`, then the gateway, brain and dashboard answer, and she answers a chat from a pretend game | ✅ | ✅ | ✅ | not yet (#40) |
| **Minecraft's side**: Fabric Loader, Fabric API, the mod and the launcher profile in a fresh Minecraft folder (`scripts/install_profile.py`) | ✅ | ✅ | ✅ | the friend's install instead ↓ |
| **A friend's PC**: `scripts/update-pip-windows.ps1` builds the mod and puts it and Fabric API in a fresh mods folder | (no script yet) | (no script yet) | (no script yet) | ✅ |
| **The game itself**: a real Minecraft client loads the mod and reaches her brain | not yet (#105) | not yet (#105) | not yet (#105) | not yet (#105) |

"Not yet" is said out loud in the results (a notice on the run), never skipped silently.

**Not covered by any of this yet:**
- Opening the downloaded app by double-click, with macOS's first-run warning: that needs a person.
- Her voice and hearing models.
- Playing for real with a microphone.

## On GitHub (the main tool)

`.github/workflows/platforms.yml` runs on GitHub's own machines, which are free for a public repository:
`macos-15` (Apple silicon), `macos-15-intel`, `ubuntu-24.04` and `windows-2025`.

It runs:
- by itself, on pull requests that change the install, the mod or the brain (not on documentation-only changes);
- on every release tag;
- by hand: on GitHub, open **Actions → Platforms → Run workflow**.

Each macOS run keeps the `.dmg` it built for 14 days, under the run's **Artifacts**, so someone with that kind of Mac
can try it.

It isn't part of "CI passed", so it doesn't block merging. Look at it before merging anything that touches the
install.

## On your own computer

The same script runs every check that applies to your system, in a throwaway folder and on moved ports (11537,
11540, 47911, 11599), so a Pip you're running isn't touched:

```bash
scripts/test-install.sh all          # or: brain, minecraft, setup-app
```

`KINDRED_PYTHON=brain/.venv/bin/python scripts/test-install.sh brain` uses a brain environment you already have,
instead of running `setup.sh` (which makes `brain/.venv`). The `minecraft` and `setup-app` checks download
things: Fabric's installer and Fabric API, and the Setup's Python.

### Linux, with Docker (any computer)

```bash
docker build -f scripts/test-install.Dockerfile -t kindred-test-install .
docker run --rm kindred-test-install           # or: docker run --rm kindred-test-install brain
```

It's a clean Ubuntu 24.04 with Java 25 and Python. Docker can't run Windows or macOS, so for those, use GitHub's
machines or a virtual machine.

### Windows or Linux in a virtual machine on a Mac

On an Apple silicon Mac, [UTM](https://mac.getutm.app) (free) or Parallels Desktop runs **Windows 11 for ARM** and
**Ubuntu for ARM**. Windows 11 for ARM runs ordinary x64 programs too, through its own emulation.

- **Ubuntu:** install Git, Python 3 and a JDK 25, clone the repository, and run `scripts/test-install.sh all`.
- **Windows:** follow "Setting up a friend's Windows PC" in [AGENTS.md](../AGENTS.md) (Java 21, then
  `scripts\update-pip-windows.ps1`).
- **Playing Minecraft itself in a virtual machine** needs 3D graphics: Parallels handles this better than UTM.
  It's fine for checking that the mod loads, but slow.

### An Intel Mac, from an Apple silicon Mac

The real check is GitHub's `macos-15-intel` machine. For a partial check on an Apple silicon Mac with Rosetta 2,
build the Intel app and run its smoke test. The app's Intel Python then runs under Rosetta:

```bash
python3 setup/build.py --arch x86_64
python3 setup/smoke_test.py setup/dist/Kindred-Spirit-Setup-*-macos-x86_64.dmg
```

This shows the Intel build is complete and starts. It says nothing about speed on a real Intel Mac.

## Help wanted

If you have a Windows PC, a Linux computer or an Intel Mac, trying the latest build and saying how it went (in an
issue, with the "Copy a help prompt" text or the terminal output) helps more than anything else right now.
