#!/usr/bin/env python3
"""Builds Kindred Spirit Setup: one download with its own Python, her brain, the gateway and the dashboard.

    python3 setup/build.py                               macOS, this Mac's chip: setup/dist/*.dmg and its .sha256
    python3 setup/build.py --arch x86_64                 for Intel Macs (works from an Apple silicon Mac too)
    python3 setup/build.py --python-archive FILE.tar.gz  use a Python archive you already have (checked all the same)
    python3 setup/build.py --format app                  just the .app (no .dmg), for trying it out

Needs Python 3.11+ with pip (to fetch the brain's two libraries for the target) and, for macOS, the tools that
come with it (hdiutil, codesign, sips, iconutil). How the pieces fit: setup/README.md.

Built in two parts, so other systems can be added later (#40 Windows, #81 Linux):
  payload()       the same everywhere: python/ (a standalone CPython for the target), kindred/ (brain, services,
                  scripts), VERSION
  package_macos() wraps the payload in "Kindred Spirit Setup.app", inside a .dmg
A package_windows() or package_linux() would wrap the same payload in their own way.
"""
import argparse
import glob
import hashlib
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "setup")
APP_NAME = "Kindred Spirit Setup"
BUNDLE_ID = "io.github.petitpotam.kindredspirit.setup"

# Python for the app: python-build-standalone (https://github.com/astral-sh/python-build-standalone, the builds uv
# uses; Python's own licence). Pinned with its SHA-256, so a changed file is refused. Moving to a newer one: pick
# a release at least two weeks old, change PBS_RELEASE and PY_VERSION, and copy the new digests from the release.
PBS_RELEASE = "20261026"
PY_VERSION = "3.12.16"  # the brain is tested on 3.11 and 3.12 (CI)
PY_MINOR = "3.12"
PYTHONS = {  # target: (archive name, sha256, pip platform tag for the brain's libraries)
    "macos-arm64": ("cpython-%s+%s-aarch64-apple-darwin-install_only_stripped.tar.gz" % (PY_VERSION, PBS_RELEASE),
                    "353d5f1b4fd2715e7053f12f068435d5bbad16b91e057006b5d01e0925709a7e", "macosx_11_0_arm64"),
    "macos-x86_64": ("cpython-%s+%s-x86_64-apple-darwin-install_only_stripped.tar.gz" % (PY_VERSION, PBS_RELEASE),
                     "37c38fda76fec1fbf310adcbafb7f0d96af13b5511bf8ea954c3aa8eec185734", "macosx_10_13_x86_64"),
}
PBS_URL = "https://github.com/astral-sh/python-build-standalone/releases/download/%s/%s"

# What goes in kindred/: what runs on the player's computer, nothing for development (tests, evals, the mod's source)
CODE = ["brain/kindred", "brain/requirements.txt", "services", "scripts/start.sh", "scripts/stop.sh",
        "scripts/install_profile.py", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"]
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "tests", "eval_questions.json")
# parts of Python nobody needs here: its test suite, the Tk GUI toolkit and IDLE
PY_TRIM = ["lib/python%s/test" % PY_MINOR, "lib/python%s/idlelib" % PY_MINOR, "lib/python%s/tkinter" % PY_MINOR,
           "lib/python%s/turtledemo" % PY_MINOR, "lib/tcl*", "lib/tk*", "lib/itcl*", "lib/thread*", "share"]


def say(*a):
    print("==>", *a, flush=True)


def version():
    with open(os.path.join(ROOT, "mod", "gradle.properties"), encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("mod_version="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("mod_version not found in mod/gradle.properties")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def python_archive(target, given, cache):
    """The standalone Python for the target: the file given, the cached one, or downloaded; always hash-checked."""
    name, digest, _ = PYTHONS[target]
    path = given or os.path.join(cache, name)
    if not os.path.exists(path):
        if given:
            raise SystemExit("no such file: %s" % given)
        os.makedirs(cache, exist_ok=True)
        say("downloading %s" % name)
        req = urllib.request.Request(PBS_URL % (PBS_RELEASE, name), headers={"User-Agent": "kindred-spirit-setup-build"})
        with urllib.request.urlopen(req, timeout=120) as r, open(path + ".part", "wb") as out:
            shutil.copyfileobj(r, out)
        os.replace(path + ".part", path)
    got = sha256(path)
    if got != digest:
        raise SystemExit("%s has SHA-256 %s, expected %s: refusing it" % (path, got, digest))
    return path


def extract(archive, dest):
    with tarfile.open(archive) as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")  # no absolute paths, no links out of dest
        else:
            tar.extractall(dest)  # Python older than 3.11.4: the archive's hash was checked above


def payload(stage, target, archive):
    """stage/payload: python/, kindred/, VERSION."""
    out = os.path.join(stage, "payload")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    say("Python %s for %s" % (PY_VERSION, target))
    extract(archive, out)  # the archive holds a python/ folder
    py = os.path.join(out, "python")
    for rel in PY_TRIM:
        for found in glob.glob(os.path.join(py, rel)):
            shutil.rmtree(found, ignore_errors=True)
    site = os.path.join(py, "lib", "python%s" % PY_MINOR, "site-packages")
    say("her brain's libraries (brain/requirements.txt) for %s" % target)
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                    "--target", site, "--platform", PYTHONS[target][2], "--python-version", PY_MINOR,
                    "--implementation", "cp", "--only-binary=:all:", "--no-compile", "--upgrade",
                    "-r", os.path.join(ROOT, "brain", "requirements.txt")], check=True)
    say("her brain, the gateway and the dashboard")
    code = os.path.join(out, "kindred")
    for rel in CODE:
        src, dst = os.path.join(ROOT, rel), os.path.join(code, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=SKIP)
        else:
            shutil.copy2(src, dst)
    with open(os.path.join(out, "VERSION"), "w", encoding="utf-8") as fh:
        fh.write(version() + "\n")
    runnable = os.path.join(py, "bin", "python3")
    if target == "macos-" + ("arm64" if platform.machine() == "arm64" else "x86_64") and os.path.exists(runnable):
        # compiled once here, so the app starts quickly and never writes inside itself (it runs with -B)
        subprocess.run([runnable, "-I", "-m", "compileall", "-q", "-j", "0", code, site], check=True)
    return out


def icon(dest):
    """AppIcon.icns from Pip's icon (docs/art/pip-icon.png, 512 px), with macOS's own sips and iconutil."""
    src = os.path.join(ROOT, "docs", "art", "pip-icon.png")
    with tempfile.TemporaryDirectory() as tmp:
        iconset = os.path.join(tmp, "AppIcon.iconset")
        os.makedirs(iconset)
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                px = min(size * scale, 512)
                name = "icon_%dx%d%s.png" % (size, size, "@2x" if scale == 2 else "")
                subprocess.run(["sips", "-z", str(px), str(px), src, "--out", os.path.join(iconset, name)],
                               check=True, capture_output=True)
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", dest], check=True)


def package_macos(stage, out_dir, target, fmt):
    ver = version()
    app = os.path.join(stage, APP_NAME + ".app")
    shutil.rmtree(app, ignore_errors=True)
    contents = os.path.join(app, "Contents")
    os.makedirs(os.path.join(contents, "MacOS"))
    os.makedirs(os.path.join(contents, "Resources"))
    say("the app: %s.app" % APP_NAME)
    os.replace(os.path.join(stage, "payload"), os.path.join(contents, "Resources", "payload"))
    launcher = os.path.join(contents, "MacOS", "kindred-setup")
    shutil.copy2(os.path.join(HERE, "macos", "launcher.sh"), launcher)
    os.chmod(launcher, 0o755)
    icon(os.path.join(contents, "Resources", "AppIcon.icns"))
    with open(os.path.join(contents, "Info.plist"), "wb") as fh:
        plistlib.dump({
            "CFBundleName": APP_NAME, "CFBundleDisplayName": APP_NAME, "CFBundleIdentifier": BUNDLE_ID,
            "CFBundleExecutable": "kindred-setup", "CFBundleIconFile": "AppIcon", "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": ver.split("-")[0], "CFBundleVersion": ver,
            "CFBundleInfoDictionaryVersion": "6.0", "LSMinimumSystemVersion": "12.0",
            "LSArchitecturePriority": ["arm64" if target.endswith("arm64") else "x86_64"],
            "NSHumanReadableCopyright": "Kindred Spirit, AGPL-3.0. Not an official Minecraft product.",
        }, fh)
    # Ad-hoc signature: no Apple Developer certificate (that costs money), but Apple silicon runs only signed code,
    # and it seals the bundle so a damaged download is noticed. macOS still asks the first time: docs/SETUP.md.
    if shutil.which("codesign"):
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app], check=True, capture_output=True)
    os.makedirs(out_dir, exist_ok=True)
    base = "Kindred-Spirit-Setup-%s-%s" % (ver, target)
    if fmt == "app":
        dest = os.path.join(out_dir, APP_NAME + ".app")
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(app, dest, symlinks=True)
        return dest
    say("the disk image")
    disk = os.path.join(stage, "disk")
    shutil.rmtree(disk, ignore_errors=True)
    os.makedirs(disk)
    os.replace(app, os.path.join(disk, APP_NAME + ".app"))
    os.symlink("/Applications", os.path.join(disk, "Applications"))
    shutil.copy2(os.path.join(HERE, "macos", "If macOS won't open it.txt"), disk)
    dmg = os.path.join(out_dir, base + ".dmg")
    if os.path.exists(dmg):
        os.remove(dmg)
    subprocess.run(["hdiutil", "create", "-quiet", "-volname", APP_NAME, "-srcfolder", disk, "-fs", "HFS+",
                    "-format", "UDZO", "-imagekey", "zlib-level=9", "-ov", dmg], check=True)
    return dmg


def write_checksum(path):
    line = "%s  %s\n" % (sha256(path), os.path.basename(path))
    with open(path + ".sha256", "w", encoding="utf-8") as fh:
        fh.write(line)
    return line.strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    here = "arm64" if platform.machine() == "arm64" else "x86_64"
    ap.add_argument("--system", default="macos", choices=["macos"], help="only macOS so far (#40, #81)")
    ap.add_argument("--arch", default=here, choices=["arm64", "x86_64"])
    ap.add_argument("--format", default="dmg", choices=["dmg", "app"])
    ap.add_argument("--python-archive", help="a python-build-standalone archive you already have")
    ap.add_argument("--cache", default=os.path.join(HERE, "cache"), help="where downloads are kept")
    ap.add_argument("--out", default=os.path.join(HERE, "dist"))
    args = ap.parse_args(argv)
    if sys.version_info < (3, 11):
        raise SystemExit("build with Python 3.11 or newer")
    target = "%s-%s" % (args.system, args.arch)
    archive = python_archive(target, args.python_archive, args.cache)
    with tempfile.TemporaryDirectory(prefix="kindred-setup-") as stage:
        payload(stage, target, archive)
        out = package_macos(stage, args.out, target, args.format)
    if os.path.isfile(out):
        say("done: %s" % write_checksum(out))
    else:
        say("done: %s" % out)
    return out


if __name__ == "__main__":
    main()
