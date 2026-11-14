"""Chooses settings that keep the game smooth on this computer.

The voice helpers share the machine with Minecraft, which matters most on laptops. This looks
at memory and CPU cores and picks the speech model size and how many threads the helpers may
use. scripts/start.sh runs it as:  python -m kindred.hardware --env

The Setup's choice ("profile" in ~/.kindred-spirit/setup.json: auto, low, medium or high) is used when
set; KINDRED_PROFILE=low|medium|high overrides both.
"""
import json
import os
import platform
import subprocess
import sys

WHISPER_MODELS = {
    # name                       file                                   size   needs RAM
    "high": ("large-v3-turbo-q5_0", "ggml-large-v3-turbo-q5_0.bin", "547 MB"),
    "medium": ("small.en-q5_1", "ggml-small.en-q5_1.bin", "181 MB"),
    "low": ("base.en-q5_1", "ggml-base.en-q5_1.bin", "57 MB"),
}
HEARING_FILES = dict({k: v[1] for k, v in WHISPER_MODELS.items()}, tiny="ggml-tiny.en-q5_1.bin")  # the Setup's sizes


def _sysctl(name):
    try:
        return int(subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, timeout=2).stdout.strip())
    except Exception:
        return 0


def detect():
    """Returns a dict: ram_gb, cores, fast_cores, apple_silicon, gpu (best guess)."""
    ram = 0
    if sys.platform == "darwin":
        ram = _sysctl("hw.memsize")
    elif hasattr(os, "sysconf"):
        try:
            ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (ValueError, OSError):
            ram = 0
    if not ram and sys.platform.startswith("win"):
        try:
            import ctypes

            class MEM(ctypes.Structure):
                _fields_ = [("len", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong),
                            ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
            m = MEM()
            m.len = ctypes.sizeof(MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            ram = m.total
        except Exception:
            ram = 0
    cores = os.cpu_count() or 2
    fast = _sysctl("hw.perflevel0.physicalcpu") if sys.platform == "darwin" else 0
    apple = sys.platform == "darwin" and platform.machine() == "arm64"
    return {
        "ram_gb": round(ram / 2 ** 30, 1) if ram else 0,
        "cores": cores,
        "fast_cores": fast or max(1, cores // 2),
        "apple_silicon": apple,
        # whisper.cpp uses Metal on Apple silicon, so speech-to-text barely touches the CPU there
        "gpu": "metal" if apple else "cpu",
    }


def chosen_profile():
    """KINDRED_PROFILE, or what the player chose in the Setup; "auto" when neither says."""
    forced = os.environ.get("KINDRED_PROFILE", "").lower()
    if forced in WHISPER_MODELS:
        return forced
    home = os.environ.get("KINDRED_HOME") or os.path.join(os.path.expanduser("~"), ".kindred-spirit")
    try:
        with open(os.path.join(home, "setup.json"), encoding="utf-8") as fh:
            saved = str(json.load(fh).get("profile", "auto")).lower()
    except (OSError, ValueError, AttributeError):
        saved = "auto"
    return saved if saved in WHISPER_MODELS else "auto"


def chosen_hearing():
    """The Whisper model the player chose in the Setup ("hearing_size" in setup.json), or None."""
    home = os.environ.get("KINDRED_HOME") or os.path.join(os.path.expanduser("~"), ".kindred-spirit")
    try:
        with open(os.path.join(home, "setup.json"), encoding="utf-8") as fh:
            size = json.load(fh).get("hearing_size")
    except (OSError, ValueError, AttributeError):
        return None
    return HEARING_FILES.get(size)


def profile(hw, choice=None):
    """Settings for this computer: choice is low, medium, high or auto (None: the player's choice)."""
    forced = chosen_profile() if choice is None else choice
    if forced in WHISPER_MODELS:
        level = forced
    elif hw["ram_gb"] >= 15 and (hw["apple_silicon"] or hw["fast_cores"] >= 6):
        level = "high"
    elif hw["ram_gb"] >= 7.5:
        level = "medium"
    else:
        level = "low"
    fast = hw["fast_cores"]
    # Leave most cores to Minecraft: its render and server threads are what you feel as lag.
    return {
        "level": level,
        # (KINDRED_WHISPER_MODEL set by hand wins: her Docker image picks the small one for a CPU, #128)
        "whisper_model": os.environ.get("KINDRED_WHISPER_MODEL") or (choice is None and chosen_hearing())
        or WHISPER_MODELS[level][1],
        "whisper_threads": max(1, min(4, fast // 2 if hw["gpu"] == "cpu" else 2)),
        "tts_threads": {"high": 3, "medium": 2, "low": 2}[level] if fast >= 4 else max(1, fast // 2),
        "nice": 10,
    }


def main(argv):
    hw = detect()
    p = profile(hw)
    if "--env" in argv:
        for k, v in p.items():
            print("KINDRED_%s=%s" % (k.upper(), v))
        return 0
    print("This computer: %.1f GB memory, %d cores (%d fast), %s" % (
        hw["ram_gb"], hw["cores"], hw["fast_cores"], "Apple silicon (Metal)" if hw["apple_silicon"] else hw["gpu"]))
    print("Profile: %s -> Whisper %s, %d Whisper threads, %d voice threads, helpers at low priority" % (
        p["level"], p["whisper_model"], p["whisper_threads"], p["tts_threads"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
