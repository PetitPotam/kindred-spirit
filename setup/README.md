# Building Kindred Spirit Setup

The player's guide is [docs/SETUP.md](../docs/SETUP.md); the design is issue #82. This folder builds the
download.

```bash
python3 setup/build.py                    # this Mac's chip -> setup/dist/Kindred-Spirit-Setup-<version>-macos-<arch>.dmg (+ .sha256)
python3 setup/build.py --arch x86_64      # for Intel Macs, from any Mac
python3 setup/build.py --format app       # just the .app, to try it
python3 setup/smoke_test.py setup/dist/Kindred-Spirit-Setup-*-macos-arm64.dmg   # install and start it, in a throwaway home
```

The build needs Python 3.11+ with pip, and macOS's own tools (`hdiutil`, `codesign`, `sips`, `iconutil`). It
downloads two things, kept in `setup/cache/` and `pip`'s cache: a standalone Python (about 25 MB, pinned by its
SHA-256 in `build.py`) and the brain's two libraries for the target (`brain/requirements.txt`: numpy, websockets).

## What's inside

```
Kindred-Spirit-Setup-<version>-macos-arm64.dmg
  Kindred Spirit Setup.app/Contents/
    Info.plist
    MacOS/kindred-setup          macos/launcher.sh: starts the guide, opens the browser
    Resources/AppIcon.icns       from docs/art/pip-icon.png
    Resources/payload/           the same on every system:
      python/                    CPython 3.12 from python-build-standalone, with numpy and websockets
      kindred/                   brain/kindred, services/, scripts/start.sh, stop.sh, install_profile.py, licences
      VERSION                    mod_version from mod/gradle.properties
  Applications ->                a link, to drag the app onto
  If macOS won't open it.txt     macos/If macOS won't open it.txt
```

**How it runs.** Opening the app runs `launcher.sh`, which starts `services/dashboard.py --setup` with the app's
own Python, on `127.0.0.1:11441`, and opens `/setup` in the browser. The steps live in `services/setup_steps.py`
and the page in `services/setup.html`. "Install" copies the payload to
`~/Library/Application Support/Kindred Spirit/versions/<version>` and points `current` at it; "Start" runs that
copy's `scripts/start.sh --background` with `KINDRED_PYTHON` set to its Python. The app itself is never written to
(its Python runs with `-B`; the code is compiled at build time), so it keeps its signature and works from a
read-only disk image. Settings stay in `~/.kindred-spirit`, as with `scripts/setup.sh`.

**Adding a step.** Write `step_<id>()` (what the page shows: title, why, default, facts, choices, actions,
status, summary), `act_<id>(action, body)` and `test_<id>()` in `setup_steps.py`, add them to `STEPS` (and the
logs worth sending with a help prompt to `LOGS_FOR`), and test them in `brain/tests/test_setup_app.py`. The page
draws every step the same way.

## Why a .app in a .dmg, unsigned

- **A .dmg** is what Mac players expect: open it, drag the app to Applications. It keeps the app's permissions
  and links intact, carries the "If macOS won't open it" note next to the app, and `hdiutil` comes with macOS (and
  with GitHub's macOS runners), so nothing extra is needed to build it. A .zip would work too, but is unpacked
  into Downloads, where people tend to run apps from and forget the note.
- **Unsigned (ad-hoc signed):** signing with a Developer ID and notarising needs a paid Apple Developer membership.
  The app is signed "ad hoc" instead (no identity), which Apple silicon requires to run code at all and which seals
  the bundle; Gatekeeper still asks the first time, and docs/SETUP.md explains how to open it anyway. If the
  project ever pays for a membership, `codesign` with the Developer ID and `xcrun notarytool` slot into
  `package_macos()`.
- **A browser page, not a native window:** the guide is the dashboard's own web page, so it's the same on every
  system, the dashboard can show it later, and the app needs no Swift or GUI toolkit.
- **One file per chip** (arm64, x86_64) rather than one "universal" app: python-build-standalone ships one Python
  per chip, and a universal app would be twice the download for everyone.

## Other systems

`build.py` makes a payload that is the same everywhere, then wraps it per system. Windows (#40) and Linux (#81)
need: their entries in `PYTHONS` (python-build-standalone has `x86_64-pc-windows-msvc` and
`x86_64-unknown-linux-gnu`), a `package_windows()` / `package_linux()`, a launcher for that system, and
`scripts/start.sh` / `stop.sh` equivalents there (the brain itself and the services are cross-platform Python).
`setup_steps.app_dir()` already knows where the program goes on each.
