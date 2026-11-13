#!/bin/sh
# Pip's eval set: moments from real playtests, replayed through the whole brain (brain/evals/run.py).
#   scripts/eval.sh                        stub mode (no services, no AI): what CI runs
#   scripts/eval.sh --mode local           + local embeddings (System 0's understanding), still no AI
#   scripts/eval.sh --mode live --judge    the real AI through your gateway (a few cents) and a judge
#   scripts/eval.sh --list                 the cases
# Context breakdown from the gateway log: scripts/eval.sh context --since "2026-11-12 23:04"
cd "$(dirname "$0")/../brain" || exit 1
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null | sed 's|/.git$||')/brain/.venv/bin/python"
[ -x "$PY" ] || PY=python3
if [ "$1" = "context" ]; then shift; exec "$PY" -m evals.context "$@"; fi
exec "$PY" -m evals.run "$@"
