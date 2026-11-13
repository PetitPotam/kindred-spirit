"""Kindred Spirit Setup: her local models (#95): instincts (embeddings), voice (Kokoro) and hearing (Whisper).

Each step chooses between "on this computer" (the default: downloaded with progress, a SHA-256 check and resume, by
downloads.py, sized for the computer), a service that uses a key you already gave (#94), or off. The files land
where scripts/start.sh and the gateway already look for them:

  ~/.kindred-spirit/embed/venv, embed/models     fastembed and bge-small-en-v1.5 (System 0: what memories mean)
  ~/.kindred-spirit/kokoro/venv, kokoro/*.onnx   Kokoro and its voices (her voice)
  ~/.kindred-spirit/whisper/ggml-*.bin           a Whisper model sized for this computer, and Silero VAD (hearing)

Whisper runs in whisper.cpp's whisper-server: the one the Setup app carries (payload/bin, built by setup/build.py),
else one on this computer (Homebrew's). Used by setup_steps.py. Standard library only.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

import downloads
import kindred_gateway as gw
from kindred import hardware

KOKORO = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
WHISPER = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
# (file, sha256, bytes). Kokoro's release publishes no digests: these are of the files as published there (v1.0).
KOKORO_FILES = [("kokoro-v1.0.int8.onnx", "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb", 92361271),
                ("voices-v1.0.bin", "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d", 28214398)]
WHISPER_FILES = {  # Hugging Face's own SHA-256 (the LFS object id)
    "ggml-tiny.en-q5_1.bin": ("c77c5766f1cef09b6b7d47f21b546cbddd4157886b3b5d6d4f709e91e66c7c2b", 32166155),
    "ggml-base.en-q5_1.bin": ("4baf70dd0d7c4247ba2b81fafd9c01005ac77c2f9ef064e00dcf195d0e2fdd2f", 59721011),
    "ggml-small.en-q5_1.bin": ("bfdff4894dcb76bbf647d56263ea2a96645423f1669176f4844a1bf8e478ad30", 190098681),
    "ggml-large-v3-turbo-q5_0.bin": ("394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2", 574041195),
}
VAD = ("ggml-silero-v5.1.2.bin", "29940d98d42b91fbd05ce489f3ecf7c72f0a42f027e4875919a28fb4c04ea2cf", 885098,
       "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin")
HEARING_SIZES = {"tiny": "ggml-tiny.en-q5_1.bin", "low": "ggml-base.en-q5_1.bin", "medium": "ggml-small.en-q5_1.bin",
                 "high": "ggml-large-v3-turbo-q5_0.bin"}
SIZE_LABELS = {"tiny": "Tiny (32 MB): any computer, hears less well", "low": "Small (60 MB): 8 GB of memory or less",
               "medium": "Medium (190 MB): most laptops", "high": "Large (574 MB): 16 GB or more, or Apple silicon"}
VOICES = [("bf_lily", "Lily: young, British (her own voice)"), ("bf_emma", "Emma: British, warm"),
          ("bf_isabella", "Isabella: British, bright"), ("af_heart", "Heart: American, gentle"),
          ("af_bella", "Bella: American, lively"), ("af_nicole", "Nicole: American, soft"),
          ("af_sky", "Sky: American, airy")]
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
WHISPER_PLACES = ["/opt/homebrew/bin/whisper-server", "/usr/local/bin/whisper-server"]  # Homebrew's, if any
PREVIEW = "Hi! I'm Pip. Shall we go and find some diamonds together?"


def ss():
    import setup_steps  # (imported here: setup_steps imports this module)
    return setup_steps


def kh(*parts):
    return os.path.join(gw.DIR, *parts)


def python():
    """The Python that makes her venvs: the installed copy's (through "current", so it survives updates)."""
    cur = os.path.join(ss().app_dir(), "current", "python", "bin", "python3")
    return cur if os.path.exists(cur) else sys.executable


def use(part):
    return gw.load()[part]["use"]


def set_use(part, value, **provider):
    def edit(s):
        s[part]["use"] = value
        if provider:
            s[part]["providers"][value].update(provider)
    gw.change(edit)


def keyed(part, name):
    """Can this service be used: is its key saved?"""
    key = (gw.load()[part]["providers"].get(name) or {}).get("key", "")
    return not key.startswith("env:") or bool(gw.secret(key[4:]))


def job_view(name):
    st = downloads.status(name)
    if st["state"] == "idle":
        return None
    return {"state": st["state"], "percent": st.get("percent", 0), "text": st.get("error") or st.get("text", "")}


def wake_helpers():
    """Starts what isn't running yet (a voice or hearing just installed) with the installed copy's start.sh."""
    rt = ss().installed()
    if rt:
        ss().run_script(rt, "start.sh", "--background", timeout=90)


def gateway(path, body, ctype="application/json", timeout=60):
    req = urllib.request.Request("http://127.0.0.1:%d/v1%s" % (gw.LISTEN_PORT, path), method="POST",
                                 data=body if isinstance(body, bytes) else json.dumps(body).encode(),
                                 headers={"Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise ss().SetupError("The gateway answered with an error (HTTP %d): %s" % (e.code, detail))
    except (urllib.error.URLError, OSError) as e:
        raise ss().SetupError("The gateway isn't answering (%s): wake her up first." % getattr(e, "reason", e))


def retry(fn, seconds=20):
    """A helper that was just started needs a few seconds (Kokoro loads its model)."""
    deadline, last = time.time() + seconds, None
    while time.time() < deadline:
        try:
            return fn()
        except ss().SetupError as e:
            last = e
            time.sleep(1)
    raise last


# ---------------------------------------------------------------------- System 0: her instincts (embeddings)

def embed_ready():
    return os.path.exists(kh("embed", "venv", "bin", "python")) and os.path.isdir(kh("embed", "models"))


def step_instincts():
    R = ss()
    now = use("embeddings")
    choices = [{"value": "local", "label": "A small model on this computer (bge-small, about 65 MB)", "recommended": True,
                "note": "Free and private. " + ("Installed." if embed_ready() else "Downloaded when you press \"Use this\".")}]
    for name, label in (("gemini", "Gemini"), ("openai", "OpenAI")):
        if keyed("embeddings", name):
            choices.append({"value": name, "label": "%s, with the key you gave" % label, "note": "Sends your memories' text to %s." % label})
    choices.append({"value": "none", "label": "None: keyword search only", "note": "She still remembers, a little less cleverly."})
    return {
        "id": "instincts", "title": "Her instincts (System 0)",
        "why": "Before the AI is asked anything, Pip's instincts find the memories that matter right now: a small model "
               "turns words into meanings, so \"the place with the sheep\" finds \"the meadow farm\". It runs on your "
               "computer and is quick.",
        "default": "The small model on this computer.",
        "facts": [["In use", {"local": "the small model on this computer", "none": "keyword search"}.get(now, now)]],
        "choices": choices, "chosen": now if any(c["value"] == now for c in choices) else "local",
        "actions": [{"id": "choose", "label": "Use this", "primary": True}],
        "progress": job_view("embed"),
        "status": "done" if (R.load_state().get("results", {}).get("instincts") or {}).get("ok") else "todo",
        "summary": "Ready." if now != "local" or embed_ready() else "Not downloaded yet.",
    }


def act_instincts(action, body):
    R = ss()
    if action != "choose":
        raise R.SetupError("unknown action")
    choice = str(body.get("choice") or "local")
    if choice not in ("local", "gemini", "openai", "none"):
        raise R.SetupError("Choose one of the options.")
    set_use("embeddings", choice)
    if choice != "local" or embed_ready():
        return R._result(True, "Saved.")
    if downloads.free_gb(gw.DIR) < 1:
        raise R.SetupError("Not enough free space: about 1 GB is needed.")
    venv = kh("embed", "venv")
    warm = [os.path.join(venv, "bin", "python"), "-c",
            "import sys; from fastembed import TextEmbedding; TextEmbedding(sys.argv[1], cache_dir=sys.argv[2])",
            EMBED_MODEL, kh("embed", "models")]
    downloads.start("embed", [
        downloads.Pip(python(), venv, ["fastembed"], kh("logs", "setup-models.out"), "fastembed (the program)"),
        downloads.Run(lambda: subprocess.run(warm, check=True, capture_output=True, timeout=900),
                      "the model (bge-small, from Hugging Face)", 65 << 20)])
    return R._result(True, "Downloading in the background: the bar shows how far it is. Test it when it's done.")


def test_instincts():
    R = ss()
    if use("embeddings") == "none":
        return R._result(True, "Keyword search: nothing to test.")
    if use("embeddings") == "local" and not embed_ready():
        return R._result(False, "The small model isn't downloaded yet: press \"Use this\".")
    wake_helpers()
    out = json.loads(retry(lambda: gateway("/embeddings", {"input": "a cozy cottage by the lake"})))
    dims = len(out["data"][0]["embedding"])
    return R._result(dims > 0, "She understands meanings: %d numbers for a sentence." % dims)


# ---------------------------------------------------------------------- her voice (Kokoro)

def kokoro_ready():
    return os.path.exists(kh("kokoro", "venv", "bin", "python")) and all(
        os.path.exists(kh("kokoro", f)) for f, _, _ in KOKORO_FILES)


def step_voice():
    R = ss()
    now = use("tts")
    voice = gw.load()["tts"]["providers"]["local_kokoro"].get("voice") or "bf_lily"
    choices = [{"value": "local_kokoro", "label": "Kokoro on this computer (about 400 MB with its program)",
                "recommended": True, "note": "Free and private, her own bright young voice. "
                + ("Installed." if kokoro_ready() else "Downloaded when you press \"Use this\".")}]
    if keyed("tts", "openai"):
        choices.append({"value": "openai", "label": "OpenAI's voices, with the key you gave", "note": "Paid per use."})
    choices.append({"value": "none", "label": "No voice: subtitles only", "note": "She writes what she says."})
    return {
        "id": "voice", "title": "Her voice",
        "why": "Pip speaks her answers aloud (and shows them as subtitles). Kokoro makes her voice on your computer: "
               "free, private, and quick enough to start speaking while she's still thinking.",
        "default": "Kokoro on this computer, with Lily's voice.",
        "facts": [["In use", {"local_kokoro": "Kokoro", "none": "subtitles only"}.get(now, now)], ["Voice", voice]],
        "choices": choices, "chosen": now if any(c["value"] == now for c in choices) else "local_kokoro",
        "fields": [{"id": "voice", "label": "Her voice (press \"Hear it\" to listen)", "type": "select",
                    "for": ["local_kokoro"], "options": [{"value": v, "label": l} for v, l in VOICES], "value": voice}],
        "actions": [{"id": "choose", "label": "Use this", "primary": True}],
        "audio": {"label": "Hear it", "for": ["local_kokoro"]} if kokoro_ready() else None,
        "progress": job_view("kokoro"),
        "status": "done" if (R.load_state().get("results", {}).get("voice") or {}).get("ok") else "todo",
        "summary": "Ready." if now != "local_kokoro" or kokoro_ready() else "Not downloaded yet.",
    }


def act_voice(action, body):
    R = ss()
    if action != "choose":
        raise R.SetupError("unknown action")
    choice = str(body.get("choice") or "local_kokoro")
    if choice not in ("local_kokoro", "openai", "none"):
        raise R.SetupError("Choose one of the options.")
    voice = str(body.get("voice") or "bf_lily")
    if choice == "local_kokoro":
        if voice not in dict(VOICES):
            raise R.SetupError("Choose one of the voices.")
        set_use("tts", choice, voice=voice)
    else:
        set_use("tts", choice)
    _brain_voice(choice != "none")
    if choice != "local_kokoro" or kokoro_ready():
        return R._result(True, "Saved.")
    if downloads.free_gb(gw.DIR) < 1:
        raise R.SetupError("Not enough free space: about 1 GB is needed.")
    downloads.start("kokoro", [downloads.Pip(python(), kh("kokoro", "venv"), ["kokoro-onnx", "soundfile"],
                                             kh("logs", "setup-models.out"), "Kokoro (the program)")]
                    + [downloads.File(KOKORO + f, kh("kokoro", f), sha, size) for f, sha, size in KOKORO_FILES])
    return R._result(True, "Downloading in the background: the bar shows how far it is. Then press \"Hear it\".")


def _brain_voice(on):
    """brain.toml's voice switch (subtitles only when off), as scripts/guide.py does."""
    path = kh("brain.toml")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    want = "enabled = %s" % ("true" if on else "false")
    import re
    new = re.sub(r"(?m)^(\s*)enabled\s*=\s*(true|false)", lambda m: m.group(1) + want, text, count=1) \
        if re.search(r"(?ms)^\[voice\].*?^\s*enabled\s*=", text) else text
    if new != text:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new)


def speak(text=PREVIEW, voice=None):
    """Her voice saying something, as WAV (for "Hear it" and the test)."""
    if use("tts") == "local_kokoro" and not kokoro_ready():
        raise ss().SetupError("Kokoro isn't downloaded yet: press \"Use this\".")
    wake_helpers()
    body = {"input": text}
    if voice in dict(VOICES):
        body["voice"] = voice
    return retry(lambda: gateway("/audio/speech", body, timeout=90), seconds=40)


def test_voice():
    R = ss()
    if use("tts") == "none":
        return R._result(True, "Subtitles only: nothing to test.")
    wav = speak("Testing, one, two, three.")
    ok = wav[:4] == b"RIFF" and len(wav) > 2000
    return R._result(ok, "Her voice works: %d KB of sound. Press \"Hear it\" to listen." % (len(wav) // 1024) if ok
                     else "The voice answered, but not with sound.")


# ---------------------------------------------------------------------- her hearing (Whisper)

def whisper_server():
    """whisper.cpp's server: the one the Setup app carries, else one on this computer."""
    rt = ss().installed()
    for c in ([os.path.join(rt["path"], "bin", "whisper-server")] if rt else []) + \
             [shutil.which("whisper-server") or ""] + WHISPER_PLACES:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return ""


def hearing_size():
    saved = ss().load_state().get("hearing_size")
    return saved if saved in HEARING_SIZES else hardware.profile(hardware.detect())["level"]


def hearing_ready(size=None):
    return os.path.exists(kh("whisper", HEARING_SIZES[size or hearing_size()])) and os.path.exists(kh("whisper", VAD[0]))


def step_hearing():
    R = ss()
    now = use("stt")
    size = hearing_size()
    server = whisper_server()
    choices = [{"value": "local_whisper", "label": "Whisper on this computer", "recommended": True,
                "note": "Free and private" + (", on your graphics chip" if hardware.detect()["apple_silicon"] else "")
                + (". " + ("Installed." if hearing_ready() else "Downloaded when you press \"Use this\".") if server
                   else ". This copy of the Setup has no Whisper program, and none was found on this computer.")}]
    for name, label in (("groq", "Groq, with the key you gave (free tier)"), ("openai", "OpenAI, with the key you gave")):
        if keyed("stt", name):
            choices.append({"value": name, "label": label, "note": "Your voice is sent to them to be written down."})
    choices.append({"value": "none", "label": "None: I'll type to her", "note": "Plain chat in the game."})
    return {
        "id": "hearing", "title": "Her hearing",
        "why": "Hold V in the game and talk: Pip hears you. Whisper writes down what you said, on your computer. "
               "Bigger models hear better but use more memory; the Setup picks one for this computer.",
        "default": "Whisper on this computer, %s." % SIZE_LABELS[size].split(":")[0].lower(),
        "facts": [["In use", {"local_whisper": "Whisper", "none": "typing only"}.get(now, now)],
                  ["Size", SIZE_LABELS[size].split(":")[0]]],
        "choices": choices, "chosen": now if any(c["value"] == now for c in choices) else "local_whisper",
        "fields": [{"id": "size", "label": "Model size", "type": "select", "for": ["local_whisper"], "value": size,
                    "options": [{"value": k, "label": v} for k, v in SIZE_LABELS.items()]}],
        "actions": [{"id": "choose", "label": "Use this", "primary": True}],
        "mic": {"label": "Test the microphone", "seconds": 4} if now != "none" else None,
        "progress": job_view("whisper"),
        "status": "done" if (R.load_state().get("results", {}).get("hearing") or {}).get("ok") else "todo",
        "summary": "Ready." if now != "local_whisper" or hearing_ready() else "Not downloaded yet.",
    }


def act_hearing(action, body):
    R = ss()
    if action != "choose":
        raise R.SetupError("unknown action")
    choice = str(body.get("choice") or "local_whisper")
    if choice not in ("local_whisper", "groq", "openai", "none"):
        raise R.SetupError("Choose one of the options.")
    if choice == "local_whisper" and not whisper_server():
        raise R.SetupError("This copy of the Setup has no Whisper program: choose Groq (free, with a key) or "
                           "typing, or install whisper.cpp (Homebrew: brew install whisper-cpp).")
    size = str(body.get("size") or hearing_size())
    if size not in HEARING_SIZES:
        raise R.SetupError("Choose a size.")
    set_use("stt", choice)
    R.save_state(hearing_size=size)
    if choice != "local_whisper" or hearing_ready(size):
        return R._result(True, "Saved.")
    name = HEARING_SIZES[size]
    sha, n = WHISPER_FILES[name]
    if downloads.free_gb(gw.DIR) < n / 2 ** 30 + 0.5:
        raise R.SetupError("Not enough free space for this size: choose a smaller one, or free some space.")
    downloads.start("whisper", [downloads.File(WHISPER + name, kh("whisper", name), sha, n),
                                downloads.File(VAD[3], kh("whisper", VAD[0]), VAD[1], VAD[2])])
    return R._result(True, "Downloading in the background: the bar shows how far it is. Then test the microphone.")


def transcribe(wav):
    """What her hearing makes of a recording (the microphone test)."""
    if use("stt") == "none":
        raise ss().SetupError("Her hearing is off: you type to her.")
    if use("stt") == "local_whisper" and not hearing_ready():
        raise ss().SetupError("Whisper isn't downloaded yet: press \"Use this\".")
    wake_helpers()
    boundary = "kindred" + uuid.uuid4().hex
    body = (b"--" + boundary.encode() + b'\r\nContent-Disposition: form-data; name="file"; filename="mic.wav"\r\n'
            b"Content-Type: audio/wav\r\n\r\n" + wav + b"\r\n--" + boundary.encode() + b"--\r\n")
    out = retry(lambda: gateway("/audio/transcriptions", body, "multipart/form-data; boundary=" + boundary), seconds=30)
    return (json.loads(out).get("text") or "").strip()


def test_hearing():
    R = ss()
    if use("stt") == "none":
        return R._result(True, "You type to her: nothing to test.")
    if use("tts") == "none":
        return R._result(True, "Use \"Test the microphone\" to check her hearing.", warn=True)
    heard = transcribe(speak("Testing, one, two, three."))  # her own voice, heard back
    ok = bool(heard)
    return R._result(ok, "She heard her own voice: \"%s\". Now try \"Test the microphone\"." % heard if ok
                     else "Her hearing answered with nothing: try \"Test the microphone\".")
