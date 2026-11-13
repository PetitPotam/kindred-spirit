#!/bin/bash
# Setup (macOS and Linux): prepares the brain, then a short guide asks what you already have for
# each part (the AI, speech-to-text, voice, memory), installs only what you chose, and tests it all.
#
#   scripts/setup.sh                    the guide (run it again any time to change your choices)
#   scripts/setup.sh --defaults         no questions: Gemini (key in secrets.env) and everything else local
#   scripts/setup.sh --no-voice         no questions: the brain only (type to her, subtitles only)
#   scripts/setup.sh --install NAME     install one local part: kokoro (voice), whisper (speech-to-text),
#                                       embed (memory embeddings)
#   KOKORO_FROM=/dir WHISPER_FROM=/dir scripts/setup.sh   copy models you already have instead of downloading
#
# Puts the brain's Python environment in brain/.venv and everything per-user in ~/.kindred-spirit.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
git -C "$ROOT" config core.hooksPath .githooks 2>/dev/null || true  # (no direct pushes to main: docs/MAINTAINING.md)
KH="${KINDRED_HOME:-$HOME/.kindred-spirit}"
MODE="${1:-guide}"
[[ "$MODE" == "guide" && ! -t 0 ]] && MODE="--defaults"  # not in a terminal: nobody to answer questions

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
fetch() { # url dest
  [[ -s "$2" ]] && { echo "  have $(basename "$2")"; return; }
  echo "  downloading $(basename "$2")..."; curl -fL --progress-bar -o "$2.part" "$1" && mv "$2.part" "$2"
}
copy_or_fetch() { # from-dir file url dest-dir
  if [[ -n "$1" && -s "$1/$2" && ! -s "$4/$2" ]]; then
    cp -c "$1/$2" "$4/$2" 2>/dev/null || cp "$1/$2" "$4/$2"; echo "  copied $2"
  else fetch "$3" "$4/$2"; fi
}

PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then PY="$(command -v "$c")"; break; fi
done
[[ -z "$PY" ]] && { echo "Python 3.11 or newer is needed (macOS: brew install python@3.12)"; exit 1; }

brain() {
  say "Brain ($PY)"
  mkdir -p "$KH/logs"
  [[ -d "$ROOT/brain/.venv" ]] || "$PY" -m venv "$ROOT/brain/.venv"
  "$ROOT/brain/.venv/bin/pip" install -q --upgrade pip
  "$ROOT/brain/.venv/bin/pip" install -q -r "$ROOT/brain/requirements-dev.txt"
  (cd "$ROOT/brain" && .venv/bin/python -m kindred.hardware)
}

secrets_file() {
  [[ -f "$KH/secrets.env" ]] && return
  umask 077
  cat > "$KH/secrets.env" <<'EOT'
# API keys for the Kindred gateway. This file is only readable by you; never commit or share it.
# Free Gemini key: https://aistudio.google.com/apikey
GEMINI_API_KEY=
# GROQ_API_KEY=
# OPENAI_API_KEY=
# OPENROUTER_API_KEY=
EOT
  echo "  created $KH/secrets.env: put your Gemini key there (or switch the gateway to another AI)"
}

install_kokoro() {
  say "Voice: Kokoro (speaks)"
  mkdir -p "$KH/kokoro"
  [[ -d "$KH/kokoro/venv" ]] || "$PY" -m venv "$KH/kokoro/venv"
  "$KH/kokoro/venv/bin/pip" install -q kokoro-onnx soundfile
  R=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
  copy_or_fetch "${KOKORO_FROM:-}" kokoro-v1.0.int8.onnx "$R/kokoro-v1.0.int8.onnx" "$KH/kokoro"
  copy_or_fetch "${KOKORO_FROM:-}" voices-v1.0.bin "$R/voices-v1.0.bin" "$KH/kokoro"
}

install_embed() {
  say "Memory: local embeddings (understands what memories mean)"
  mkdir -p "$KH/embed/models"
  [[ -d "$KH/embed/venv" ]] || "$PY" -m venv "$KH/embed/venv"
  "$KH/embed/venv/bin/pip" install -q fastembed
  "$KH/embed/venv/bin/python" -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='$KH/embed/models')" \
    && echo "  embedding model ready (bge-small, ~65 MB)"
}

install_whisper() {
  say "Speech-to-text: Whisper (listens)"
  if ! command -v whisper-server >/dev/null; then
    if command -v brew >/dev/null; then brew install whisper-cpp
    else echo "  install whisper.cpp's whisper-server (https://github.com/ggml-org/whisper.cpp) and run this again"; fi
  fi
  mkdir -p "$KH/whisper"
  eval "$(cd "$ROOT/brain" && .venv/bin/python -m kindred.hardware --env)"
  copy_or_fetch "${WHISPER_FROM:-}" "$KINDRED_WHISPER_MODEL" \
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$KINDRED_WHISPER_MODEL" "$KH/whisper"
  copy_or_fetch "${WHISPER_FROM:-}" ggml-silero-v5.1.2.bin \
    "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin" "$KH/whisper"
}

case "$MODE" in
  --install)
    case "${2:-}" in
      kokoro) install_kokoro ;; embed) install_embed ;; whisper) install_whisper ;;
      *) echo "install what? kokoro, whisper or embed"; exit 2 ;;
    esac ;;
  --defaults)
    brain; secrets_file; install_kokoro; install_embed; install_whisper
    say "Done. Next: put your key in $KH/secrets.env, then run scripts/start.sh" ;;
  --no-voice)
    brain; secrets_file
    say "Done. Next: put your key in $KH/secrets.env, then run scripts/start.sh" ;;
  guide)
    brain
    mkdir -p "$KH"
    exec "$ROOT/brain/.venv/bin/python" "$ROOT/scripts/guide.py" ;;
  *) echo "unknown option $MODE (see the top of this script)"; exit 2 ;;
esac
