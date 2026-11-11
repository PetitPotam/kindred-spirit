#!/bin/bash
# One-time setup for the brain and the local voice (macOS and Linux).
#
#   scripts/setup.sh                 everything: brain, Kokoro voice, Whisper speech-to-text
#   scripts/setup.sh --no-voice      brain only (type to your companion with /kindred, subtitles only)
#   KOKORO_FROM=/dir WHISPER_FROM=/dir scripts/setup.sh   copy models you already have instead of downloading
#
# Puts the brain's Python environment in brain/.venv and everything per-user in ~/.kindred-spirit.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KH="${KINDRED_HOME:-$HOME/.kindred-spirit}"
VOICE=1; [[ "${1:-}" == "--no-voice" ]] && VOICE=0

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

say "Brain ($PY)"
mkdir -p "$KH/logs"
[[ -d "$ROOT/brain/.venv" ]] || "$PY" -m venv "$ROOT/brain/.venv"
"$ROOT/brain/.venv/bin/pip" install -q --upgrade pip
"$ROOT/brain/.venv/bin/pip" install -q -r "$ROOT/brain/requirements-dev.txt"
(cd "$ROOT/brain" && .venv/bin/python -m kindred.hardware)

if [[ ! -f "$KH/secrets.env" ]]; then
  umask 077
  cat > "$KH/secrets.env" <<'EOT'
# API keys for the Kindred gateway. This file is only readable by you; never commit or share it.
# Free Gemini key: https://aistudio.google.com/apikey
GEMINI_API_KEY=
# GROQ_API_KEY=
# OPENAI_API_KEY=
# OPENROUTER_API_KEY=
EOT
  echo "  created $KH/secrets.env: put your Gemini key there (or switch the gateway to Ollama)"
fi

if [[ $VOICE == 1 ]]; then
  say "Voice: Kokoro (speaks)"
  mkdir -p "$KH/kokoro"
  [[ -d "$KH/kokoro/venv" ]] || "$PY" -m venv "$KH/kokoro/venv"
  "$KH/kokoro/venv/bin/pip" install -q kokoro-onnx soundfile
  R=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
  copy_or_fetch "${KOKORO_FROM:-}" kokoro-v1.0.int8.onnx "$R/kokoro-v1.0.int8.onnx" "$KH/kokoro"
  copy_or_fetch "${KOKORO_FROM:-}" voices-v1.0.bin "$R/voices-v1.0.bin" "$KH/kokoro"

  say "Voice: Whisper (listens)"
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
fi

say "Done. Next: put your key in $KH/secrets.env, then run scripts/start.sh"
