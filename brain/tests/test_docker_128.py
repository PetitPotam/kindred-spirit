"""#128: her Docker image. The real build and run are scripts/test-install.sh docker (CI: Platforms); these check the
promises that must not slip: pinned inputs, ports on 127.0.0.1 only, her own run folder."""
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as fh:
        return fh.read()


def test_what_goes_in_is_pinned():
    df = read("docker", "Dockerfile")
    froms = re.findall(r"^FROM (\S+)", df, re.M)
    assert froms and all("@sha256:" in f for f in froms), froms
    assert re.search(r"WHISPER_COMMIT=[0-9a-f]{40}\b", df)
    assert re.search(r"kokoro-onnx==[\d.]+ soundfile==[\d.]+ fastembed==[\d.]+", df)
    assert "USER pip" in df, "never root"


def test_the_ports_are_published_on_this_computer_only():
    for script in (("scripts", "docker-run.sh"), ("scripts", "docker-run.ps1"), ("docker", "README.md"),
                   ("scripts", "test-install.sh")):
        text = read(*script)
        published = re.findall(r"-p (\S+?):?(47811|11440):\2", text)
        assert published and all(host == "127.0.0.1" for host, _ in published), (script, published)


def test_stop_uses_the_run_folder_it_is_given(tmp_path):
    run = tmp_path / "elsewhere"
    run.mkdir()
    p = subprocess.Popen(["sleep", "30"])
    (run / "brain.pid").write_text(str(p.pid))
    (tmp_path / "run").mkdir()
    out = subprocess.run(["bash", os.path.join(ROOT, "scripts", "stop.sh")], capture_output=True, text=True, timeout=30,
                         env=dict(os.environ, KINDRED_HOME=str(tmp_path), KINDRED_RUN_DIR=str(run))).stdout
    assert "stopped brain" in out and p.wait(5) is not None


def test_a_whisper_model_chosen_by_hand_wins(monkeypatch):
    from kindred import hardware
    monkeypatch.setenv("KINDRED_WHISPER_MODEL", "ggml-base.en-q5_1.bin")
    hw = {"ram_gb": 32, "apple_silicon": False, "fast_cores": 8, "cores": 8, "gpu": "cpu"}
    assert hardware.profile(hw, "high")["whisper_model"] == "ggml-base.en-q5_1.bin"
