"""#40: hosting her on Windows. The real run is scripts/test-install-windows.ps1 on GitHub's Windows machines
(Platforms); these check what must not slip: a pinned, checked download, the same ports and folders as on a Mac."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as fh:
        return fh.read()


def test_whisper_for_windows_is_pinned_and_checked():
    s = read("scripts", "setup-windows.ps1")
    assert re.search(r'\$WhisperZip = "https://github\.com/ggml-org/whisper\.cpp/releases/download/b\d+/whisper-bin-x64\.zip"', s)
    assert re.search(r'\$WhisperSha = "[0-9a-f]{64}"', s) and "Get-FileHash -Algorithm SHA256" in s


def test_the_same_ports_and_folders_as_on_a_mac():
    start, bash = read("scripts", "start-windows.ps1"), read("scripts", "start.sh")
    for port in ("8083", "8885", "8891", "11437", "11440", "47811"):
        assert port in start and port in bash, port
    for f in ("kokoro_server.py", "embed_server.py", "kindred_gateway.py", "dashboard.py", "voices-v1.0.bin", "asleep"):
        assert f in start, f
    assert "-Keep" in read("scripts", "stop-windows.ps1")


def test_ci_runs_the_windows_check():
    wf = read(".github", "workflows", "platforms.yml")
    assert "scripts\\test-install-windows.ps1" in wf and "Not yet supported::Hosting Pip on Windows" not in wf
