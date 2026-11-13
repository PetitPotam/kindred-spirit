"""Her local models in the Setup (#95): downloads that resume and check their SHA-256, the three steps (instincts,
voice, hearing), sizes for the computer, and the voice preview and microphone test routes. A local file server
stands in for the internet; a throwaway home folder for hers."""
import hashlib
import http.client
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import gateway_stub  # noqa: F401  (puts services/ on the path)
import downloads
import kindred_gateway as gw
import setup_models
import setup_steps
from kindred import hardware

DATA = os.urandom(300_000)
SHA = hashlib.sha256(DATA).hexdigest()


class Files(BaseHTTPRequestHandler):
    """Serves DATA, honouring Range (as GitHub and Hugging Face do); counts requests."""
    served = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        start = int(self.headers.get("Range", "bytes=0-")[6:].split("-")[0] or 0)
        Files.served.append(start)
        body = DATA[start:]
        self.send_response(206 if start else 200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    Files.served = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Files)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d/model.bin" % srv.server_address[1]
    srv.shutdown()


@pytest.fixture
def home(tmp_path, monkeypatch):
    kh = tmp_path / ".kindred-spirit"
    (kh / "logs").mkdir(parents=True)
    for name, rel in (("DIR", ""), ("STATE", "gateway.json"), ("SECRETS", "secrets.env"), ("LOCK", ".lock")):
        monkeypatch.setattr(gw, name, str(kh / rel).rstrip("/"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("KINDRED_HOME", str(kh))
    monkeypatch.setenv("KINDRED_APP_DIR", str(tmp_path / "app"))
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.delenv("KINDRED_PROFILE", raising=False)
    monkeypatch.setattr(setup_steps, "PAYLOAD", "")
    monkeypatch.setattr(setup_models, "WHISPER_PLACES", [])  # not this computer's Homebrew
    return kh


# ---------------------------------------------------------------------- downloads

def test_a_download_resumes_and_is_checked(server, tmp_path):
    f = downloads.File(server, str(tmp_path / "m" / "model.bin"), SHA, len(DATA))
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "model.bin.part").write_bytes(DATA[:100_000])  # a download cut off earlier
    seen = []
    downloads.fetch(f, seen.append)
    assert (tmp_path / "m" / "model.bin").read_bytes() == DATA and not (tmp_path / "m" / "model.bin.part").exists()
    assert Files.served == [100_000], "it continued where it stopped"
    assert seen[-1] == len(DATA) and seen == sorted(seen)
    Files.served = []
    downloads.fetch(f)
    assert Files.served == [], "a file already there with the right SHA-256 isn't downloaded again"


def test_a_wrong_file_is_never_kept(server, tmp_path):
    f = downloads.File(server, str(tmp_path / "model.bin"), "0" * 64, len(DATA))
    with pytest.raises(IOError, match="SHA-256"):
        downloads.fetch(f)
    assert not os.path.exists(f.dest) and not os.path.exists(f.dest + ".part")


def test_jobs_run_in_the_background_and_report(server, tmp_path):
    ran = []
    downloads.start("t", [downloads.File(server, str(tmp_path / "a.bin"), SHA, len(DATA)),
                          downloads.Run(lambda: ran.append(1), "warming up")])
    for _ in range(100):
        if downloads.status("t")["state"] != "running":
            break
        time.sleep(0.05)
    st = downloads.status("t")
    assert st["state"] == "done" and st["percent"] == 100 and ran == [1]
    downloads.start("bad", [downloads.Run(lambda: 1 / 0, "a step that fails")])
    for _ in range(100):
        if downloads.status("bad")["state"] != "running":
            break
        time.sleep(0.05)
    assert downloads.status("bad")["state"] == "failed" and "ZeroDivisionError" in downloads.status("bad")["error"]
    assert downloads.status("never")["state"] == "idle"


# ---------------------------------------------------------------------- the steps

def test_the_model_steps_come_after_her_ai(home):
    assert list(setup_steps.STEPS) == ["computer", "install", "start", "ai", "thinking", "instincts", "voice",
                                       "hearing", "login"]
    for sid in ("instincts", "voice", "hearing"):
        s = setup_steps.STEPS[sid][0]()
        assert s["choices"][0]["recommended"] and s["default"] and len(s["why"]) > 60 and s["status"] == "todo"


def test_her_voice_downloads_kokoro_pinned_and_remembers_the_voice(home, monkeypatch):
    jobs = []
    monkeypatch.setattr(setup_models.downloads, "start", lambda name, items: jobs.append((name, items)))
    (home / "brain.toml").write_text('[voice]\nenabled = false  # subtitles only\n')
    r = setup_steps.run("voice", "choose", {"choice": "local_kokoro", "voice": "bf_emma"})
    assert r["ok"] and "background" in r["message"]
    name, items = jobs[0]
    files = [i for i in items if isinstance(i, downloads.File)]
    assert name == "kokoro" and {os.path.basename(f.dest) for f in files} == {"kokoro-v1.0.int8.onnx", "voices-v1.0.bin"}
    assert all(len(f.sha256) == 64 and f.url.startswith("https://github.com/thewh1teagle/kokoro-onnx/") for f in files)
    state = json.loads((home / "gateway.json").read_text())
    assert state["tts"]["use"] == "local_kokoro" and state["tts"]["providers"]["local_kokoro"]["voice"] == "bf_emma"
    assert "enabled = true" in (home / "brain.toml").read_text()  # her voice switched on in her brain too
    assert not setup_steps.run("voice", "choose", {"choice": "local_kokoro", "voice": "nope"})["ok"]
    assert setup_steps.run("voice", "choose", {"choice": "none"})["ok"]
    assert "enabled = false" in (home / "brain.toml").read_text()


def test_her_hearing_is_sized_for_the_computer_and_can_be_changed(home, tmp_path, monkeypatch):
    jobs = []
    monkeypatch.setattr(setup_models.downloads, "start", lambda name, items: jobs.append((name, items)))
    r = setup_steps.run("hearing", "choose", {"choice": "local_whisper"})
    assert not r["ok"] and "no Whisper program" in r["message"]  # none on this "computer"
    tool = tmp_path / "bin" / "whisper-server"
    tool.parent.mkdir(exist_ok=True)
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o755)
    monkeypatch.setattr(hardware, "detect", lambda: {"ram_gb": 8, "cores": 8, "fast_cores": 4, "apple_silicon": False, "gpu": "cpu"})
    assert setup_models.hearing_size() == "medium"
    assert setup_steps.run("hearing", "choose", {"choice": "local_whisper", "size": "tiny"})["ok"]
    files = jobs[0][1]
    assert [os.path.basename(f.dest) for f in files] == ["ggml-tiny.en-q5_1.bin", "ggml-silero-v5.1.2.bin"]
    assert files[0].sha256 == setup_models.WHISPER_FILES["ggml-tiny.en-q5_1.bin"][0]
    assert hardware.profile(hardware.detect())["whisper_model"] == "ggml-tiny.en-q5_1.bin"  # start.sh follows the choice
    assert hardware.profile(hardware.detect(), choice="auto")["whisper_model"] == "ggml-small.en-q5_1.bin"
    assert not setup_steps.run("hearing", "choose", {"choice": "local_whisper", "size": "huge"})["ok"]


def test_instincts_choose_the_small_local_model_by_default(home, monkeypatch):
    jobs = []
    monkeypatch.setattr(setup_models.downloads, "start", lambda name, items: jobs.append((name, items)))
    assert setup_steps.run("instincts", "choose", {"choice": "local"})["ok"]
    assert jobs[0][0] == "embed" and isinstance(jobs[0][1][0], downloads.Pip) and jobs[0][1][0].packages == ["fastembed"]
    assert setup_steps.run("instincts", "choose", {"choice": "none"})["ok"]
    assert json.loads((home / "gateway.json").read_text())["embeddings"]["use"] == "none"
    assert setup_steps.run("instincts", "test")["ok"]
    choices = [c["value"] for c in setup_models.step_instincts()["choices"]]
    assert "gemini" not in choices  # only services whose key was given
    (home / "secrets.env").write_text("GEMINI_API_KEY=AIzaFake000000000000000000\n")
    assert "gemini" in [c["value"] for c in setup_models.step_instincts()["choices"]]


def test_tests_say_what_is_missing_without_calling_anything(home):
    setup_models.set_use("tts", "local_kokoro")
    r = setup_steps.run("voice", "test")
    assert not r["ok"] and "isn't downloaded" in r["message"]
    setup_models.set_use("stt", "none")
    assert setup_steps.run("hearing", "test")["ok"]


def test_progress_shows_on_the_step(home, monkeypatch):
    monkeypatch.setattr(setup_models.downloads, "status",
                        lambda name: {"state": "running", "percent": 42, "text": "Getting voices… 12 of 27 MB", "error": ""})
    p = setup_models.step_voice()["progress"]
    assert p == {"state": "running", "percent": 42, "text": "Getting voices… 12 of 27 MB"}


# ---------------------------------------------------------------------- the page's routes

@pytest.fixture
def dash(home, monkeypatch):
    import dashboard
    srv = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
    monkeypatch.setattr(dashboard, "PORT", srv.server_address[1])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def post(port, path, body, ctype="application/json"):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("POST", path, body if isinstance(body, bytes) else json.dumps(body), {"Content-Type": ctype})
    r = c.getresponse()
    return r.status, r.getheader("Content-Type"), r.read()


def test_hear_it_and_the_microphone_test(dash, monkeypatch):
    monkeypatch.setattr(setup_models, "speak", lambda text=None, voice=None: b"RIFF....WAVE" + (voice or "").encode())
    code, ctype, body = post(dash, "/api/setup/preview", {"voice": "af_heart"})
    assert code == 200 and ctype.startswith("audio/wav") and body.endswith(b"af_heart")
    monkeypatch.setattr(setup_models, "transcribe", lambda wav: "hello pip" if wav.startswith(b"RIFF") else "")
    code, _, body = post(dash, "/api/setup/hear", b"RIFF-a-recording", "audio/wav")
    assert code == 200 and json.loads(body) == {"text": "hello pip"}

    def off(wav):
        raise setup_steps.SetupError("Her hearing is off: you type to her.")
    monkeypatch.setattr(setup_models, "transcribe", off)
    code, _, body = post(dash, "/api/setup/hear", b"RIFF", "audio/wav")
    assert code == 400 and "off" in json.loads(body)["error"]
