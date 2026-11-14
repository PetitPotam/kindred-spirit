#!/bin/bash
# Inside her Docker image (docker/Dockerfile, #128): your ~/.kindred-spirit is mounted at /home/pip/.kindred-spirit,
# so her settings, memories, key and the game's token are the same files as without Docker. The first start downloads
# her voice (Kokoro, ~120 MB) and hearing (Whisper, 57 MB by default) into it, once; then everything starts, and the
# container runs as long as her dashboard does ("Stop everything" on the dashboard stops the container; "Put her to
# sleep" stops only her brain, voice and hearing). Her brain's log is the container's log.
#
#   KINDRED_NO_MODELS=1   no downloads (voice and hearing off unless already there; the tests use it)
#   KINDRED_WHISPER_MODEL a bigger hearing model, e.g. ggml-small.en-q5_1.bin (181 MB), better and slower on a CPU
set -uo pipefail
ROOT=/opt/kindred
KH="${KINDRED_HOME:-$HOME/.kindred-spirit}"
mkdir -p "$KH/logs" "$KH/kokoro" "$KH/whisper" "$KH/embed/models" 2>/dev/null
if ! touch "$KH/.docker-can-write" 2>/dev/null; then
  echo "Can't write in $KH: is ~/.kindred-spirit mounted there, and yours? (docker/README.md)" >&2
  exit 1
fi
rm -f "$KH/.docker-can-write"
if [[ ! -f "$KH/secrets.env" ]]; then
  (umask 077; printf 'GEMINI_API_KEY=\n' > "$KH/secrets.env")
  echo "Made $KH/secrets.env: put your Gemini key there (or choose another AI on the dashboard), then restart."
fi

fetch() { # url dest
  [[ -s "$2" ]] && return 0
  echo "downloading $(basename "$2")..."
  curl -fsSL --retry 3 -o "$2.part" "$1" && mv "$2.part" "$2" || { rm -f "$2.part"; echo "  couldn't download $(basename "$2")"; }
}
uses() { # what the gateway uses for a part (gateway.json), or its default
  "$KINDRED_PYTHON" -c "import json,os,sys; p=os.path.join(sys.argv[3],'gateway.json'); s=json.load(open(p)) if os.path.exists(p) else {}; print(s.get(sys.argv[1],{}).get('use',sys.argv[2]))" "$1" "$2" "$KH"
}
if [[ "${KINDRED_NO_MODELS:-}" != 1 ]]; then
  if [[ "$(uses tts local_kokoro)" == local_kokoro ]]; then
    R=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
    fetch "$R/kokoro-v1.0.int8.onnx" "$KH/kokoro/kokoro-v1.0.int8.onnx"
    fetch "$R/voices-v1.0.bin" "$KH/kokoro/voices-v1.0.bin"
  fi
  if [[ "$(uses stt local_whisper)" == local_whisper ]]; then
    # (a CPU in a container: the small, fast model unless you choose another one)
    M="${KINDRED_WHISPER_MODEL:-ggml-base.en-q5_1.bin}"
    fetch "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$M" "$KH/whisper/$M"
    fetch "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin" "$KH/whisper/ggml-silero-v5.1.2.bin"
  fi
fi
# (start.sh asks the hardware check which model to use: this one)
export KINDRED_WHISPER_MODEL="${KINDRED_WHISPER_MODEL:-ggml-base.en-q5_1.bin}"

bash "$ROOT/scripts/start.sh" --background || exit 1
RUN="${KINDRED_RUN_DIR:-$KH/run}"
DASH="$(cat "$RUN/dashboard.pid" 2>/dev/null)"
[[ -n "$DASH" ]] || { echo "her dashboard didn't start: $KH/logs/dashboard.out" >&2; tail -20 "$KH/logs/dashboard.out" >&2; exit 1; }
echo "Ready: play Minecraft with the Kindred Spirit mod on this computer. Her dashboard: http://127.0.0.1:11440"
touch "$KH/logs/brain.out"
exec tail -n +1 -F --pid="$DASH" "$KH/logs/brain.out" 2>/dev/null
