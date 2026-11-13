"""Downloads for the Setup (#95): her models, with progress, a SHA-256 check and resume.

    job = downloads.start("voice", [downloads.File(url, dest, sha256, size), downloads.Pip(venv, ["kokoro-onnx"]), ...])
    downloads.status("voice")   -> {"state": "running"|"done"|"failed"|"idle", "percent", "text", "error"}

A file goes to DEST.part first and continues from where it stopped (an HTTP Range request), so a broken connection or
a closed laptop costs nothing; it's only renamed to DEST once its SHA-256 matches. A file already there with the
right SHA-256 is kept. Python packages go into a venv made with the Setup's own Python (pip shows its own progress
in the log). One job per name at a time, in a background thread; the page polls status().

Standard library only.
"""
import hashlib
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request

UA = {"User-Agent": "kindred-spirit-setup"}
CHUNK = 1 << 20
_jobs = {}
_lock = threading.Lock()


class File:
    def __init__(self, url, dest, sha256, size, label=None):
        self.url, self.dest, self.sha256, self.size = url, dest, sha256, size
        self.label = label or os.path.basename(dest)

    weight = property(lambda self: self.size)


class Pip:
    """Python packages into a venv at `venv` (made if missing) with `python`; ~50 MB counted for progress."""

    def __init__(self, python, venv, packages, log, label=None):
        self.python, self.venv, self.packages, self.log = python, venv, packages, log
        self.label = label or "the Python packages (%s)" % ", ".join(packages)

    weight = property(lambda self: 50 * 1024 * 1024)


class Run:
    """Any other step: a function that does it (e.g. warming a model up)."""

    def __init__(self, fn, label, weight=1024 * 1024):
        self.fn, self.label, self.weight = fn, label, weight


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def have(f):
    """The file is there and is the right one."""
    return os.path.exists(f.dest) and os.path.getsize(f.dest) == f.size and sha256_of(f.dest) == f.sha256


def fetch(f, progress=lambda n: None, opener=urllib.request.urlopen):
    """Downloads one File, resuming DEST.part; progress(bytes_so_far) as it goes."""
    if have(f):
        progress(f.size)
        return
    os.makedirs(os.path.dirname(f.dest), exist_ok=True)
    part = f.dest + ".part"
    for attempt in range(4):
        done = os.path.getsize(part) if os.path.exists(part) else 0
        if done > f.size:  # not ours, or the file changed: start again
            os.remove(part)
            done = 0
        if done < f.size:
            headers = dict(UA, Range="bytes=%d-" % done) if done else dict(UA)
            try:
                with opener(urllib.request.Request(f.url, headers=headers), timeout=60) as r:
                    if done and getattr(r, "status", 200) != 206:  # the server ignored Range: from the start
                        done = 0
                    with open(part, "ab" if done else "wb") as out:
                        for block in iter(lambda: r.read(CHUNK), b""):
                            out.write(block)
                            done += len(block)
                            progress(done)
            except (urllib.error.URLError, OSError, TimeoutError):
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))
                continue
        progress(done)
        if done == f.size and sha256_of(part) == f.sha256:
            os.replace(part, f.dest)
            return
        os.remove(part)  # complete but wrong: never keep it
        if attempt == 3:
            break
    raise IOError("%s didn't download correctly (its SHA-256 didn't match): try again later" % f.label)


def pip_install(p):
    os.makedirs(os.path.dirname(p.log), exist_ok=True)
    with open(p.log, "a", encoding="utf-8") as log:
        if not os.path.exists(os.path.join(p.venv, "bin", "python")):
            subprocess.run([p.python, "-m", "venv", p.venv], check=True, stdout=log, stderr=subprocess.STDOUT)
        subprocess.run([os.path.join(p.venv, "bin", "python"), "-m", "pip", "install", "--disable-pip-version-check",
                        "--progress-bar", "off"] + p.packages, check=True, stdout=log, stderr=subprocess.STDOUT)


def _run(name, items):
    total = sum(i.weight for i in items) or 1
    base = 0
    try:
        for item in items:
            _set(name, text="Getting %s…" % item.label)
            if isinstance(item, File):
                fetch(item, lambda n, b=base: _set(name, percent=min(99, int(100 * (b + n) / total)),
                                                   text="Getting %s… %d of %d MB" % (item.label, n >> 20, item.size >> 20)))
            elif isinstance(item, Pip):
                pip_install(item)
            else:
                item.fn()
            base += item.weight
            _set(name, percent=min(99, int(100 * base / total)))
        _set(name, state="done", percent=100, text="Done.")
    except Exception as e:  # shown on the page, with a help prompt
        _set(name, state="failed", error="%s: %s" % (type(e).__name__, e) if not isinstance(e, IOError) else str(e))


def _set(name, **kw):
    with _lock:
        _jobs.setdefault(name, {}).update(kw)


def start(name, items):
    """Starts a job unless it's already running; returns its status."""
    with _lock:
        if _jobs.get(name, {}).get("state") == "running":
            return dict(_jobs[name])
        _jobs[name] = {"state": "running", "percent": 0, "text": "Starting…", "error": ""}
    threading.Thread(target=_run, args=(name, items), daemon=True).start()
    return status(name)


def status(name):
    with _lock:
        return dict(_jobs.get(name) or {"state": "idle", "percent": 0, "text": "", "error": ""})


def free_gb(path):
    try:
        return shutil.disk_usage(path).free / 2 ** 30
    except OSError:
        return 0
