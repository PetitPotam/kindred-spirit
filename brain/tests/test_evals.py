"""The eval set (brain/evals) in stub mode: moments from real playtests replayed through the whole brain,
with the AI's part played by what the real AI did then. A case that passed before must still pass
(evals/baselines/stub.json); new passes are welcome (update the baseline)."""
import json
import os
import subprocess
import sys
import tempfile

BRAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_playtest_moments_dont_regress():
    out = os.path.join(tempfile.mkdtemp(), "stub.json")
    env = dict(os.environ, KINDRED_HOME=tempfile.mkdtemp())  # (never the player's own settings or logs)
    run = subprocess.run([sys.executable, "-m", "evals.run", "--mode", "stub", "-q", "--json", out], cwd=BRAIN, env=env,
                         capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-2000:]
    with open(out) as fh:
        results = json.load(fh)["results"]
    with open(os.path.join(BRAIN, "evals", "baselines", "stub.json")) as fh:
        baseline = json.load(fh)["cases"]
    now = {r["id"]: all(ok for _, ok, _ in r["brain"]) for r in results}
    lost = [cid for cid, ok in baseline.items() if ok and not now.get(cid)]
    assert not lost, "these playtest moments passed before and fail now: %s" % ", ".join(lost)
