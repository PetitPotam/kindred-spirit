"""The install checks' pieces (#104): the stand-in AI answers like an OpenAI-compatible service, streaming or not,
and the test script parses."""
import json
import os
import subprocess
import sys
import threading
import urllib.request

import pytest

REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(REPO, "brain", "tools"))
import fake_ai  # noqa: E402


@pytest.fixture
def ai():
    srv = fake_ai.ThreadingHTTPServer(("127.0.0.1", 0), fake_ai.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d/v1" % srv.server_address[1]
    srv.shutdown()


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read().decode()


def test_it_answers_a_chat(ai):
    out = json.loads(post(ai + "/chat/completions", {"model": "fake", "messages": [{"role": "user", "content": "hi"}]}))
    assert out["choices"][0]["message"]["content"] == fake_ai.ANSWER and out["usage"]["total_tokens"]


def test_it_streams_word_by_word_like_the_brain_asks(ai):
    raw = post(ai + "/chat/completions", {"stream": True, "messages": []})
    events = [line[6:] for line in raw.splitlines() if line.startswith("data: ")]
    assert events[-1] == "[DONE]"
    chunks = [json.loads(e) for e in events[:-1]]
    assert "".join(c["choices"][0]["delta"].get("content", "") for c in chunks) == fake_ai.ANSWER
    assert chunks[-1]["usage"] and chunks[-1]["choices"][0]["finish_reason"] == "stop"


def test_the_install_check_script_parses():
    subprocess.run(["bash", "-n", os.path.join(REPO, "scripts", "test-install.sh")], check=True)
    usage = subprocess.run(["bash", os.path.join(REPO, "scripts", "test-install.sh"), "nonsense"], capture_output=True, text=True)
    assert usage.returncode == 2 and "setup-app" in usage.stdout


def test_the_client_check_refuses_a_computer_with_a_pip(tmp_path):
    """It uses the real ~/.kindred-spirit and port 47811, so only on a clean machine that says it is one."""
    (tmp_path / ".kindred-spirit").mkdir()
    env = {"HOME": str(tmp_path), "PATH": os.environ["PATH"], "KINDRED_TEST_CLEAN_MACHINE": "1"}
    r = subprocess.run(["bash", os.path.join(REPO, "scripts", "test-install.sh"), "client"], env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and "clean machine" in r.stdout
    assert os.listdir(tmp_path / ".kindred-spirit") == []  # nothing written


def test_every_release_builds_tests_and_attaches_the_setup():
    """#98: the release workflow builds the Setup per chip from the release's jars, smoke-tests it, attaches it."""
    text = open(os.path.join(REPO, ".github", "workflows", "release.yml"), encoding="utf-8").read()
    setup = text[text.index("\n  setup:"):]
    for want in ("needs: release", "macos-15, ", "macos-15-intel", "--mods mod-files", "setup/smoke_test.py",
                 "gh release upload", ".dmg.sha256", "not yet tried by a person"):
        assert want in setup, want
    release = text[:text.index("\n  setup:")]
    assert "name: mod-files" in release
    # #155: the jars and versions.json in one flat folder, so the build finds them at the top of mod-files/
    upload = release[release.index("name: mod-files") - 200:release.index("name: mod-files") + 120]
    assert "path: mod-files/" in upload and "versions.json\n" not in upload.split("name: mod-files")[1]
    assert "cp versions.json mod-files/" in release
def test_stop_waits_for_helpers_to_exit_and_forces_stubborn_ones(tmp_path):
    """A restart needs the helpers' ports free: stop.sh waits, then forces one that ignores the polite stop."""
    import time
    (tmp_path / "run").mkdir()
    polite = subprocess.Popen(["sleep", "60"])
    stubborn = subprocess.Popen(["/bin/bash", "-c", "trap '' TERM; while true; do sleep 0.1; done"])
    time.sleep(0.3)  # (the trap is set)
    (tmp_path / "run" / "kokoro.pid").write_text(str(polite.pid))
    (tmp_path / "run" / "whisper.pid").write_text(str(stubborn.pid))
    t = time.time()
    out = subprocess.run(["bash", os.path.join(REPO, "scripts", "stop.sh")], env=dict(os.environ, KINDRED_HOME=str(tmp_path)),
                         capture_output=True, text=True, timeout=30)
    assert polite.wait(timeout=5) is not None and stubborn.wait(timeout=5) is not None
    assert "stopped kokoro" in out.stdout and "stopped whisper" in out.stdout and time.time() - t < 10
    assert not list((tmp_path / "run").iterdir())
