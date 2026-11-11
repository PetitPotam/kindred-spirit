#!/bin/bash
# Starts the helpers that are not already running, then the brain.
#
#   scripts/start.sh               brain in this window (Ctrl+C stops it; helpers keep running)
#   scripts/start.sh --background  everything in the background (logs in ~/.kindred-spirit/logs)
#   scripts/stop.sh                stops what this script started
#
#   :8083 whisper-server   speech-to-text (local, Metal GPU on Apple silicon), tuned for
#                          push-to-talk clips up to 15 s (-ac 768: about twice as fast)
#   :8090 speech cleaner   drops silent clips, cleans the text            (services/speech_cleaner.py)
#   :8885 kokoro           the companion's voice (local)                  (services/kokoro_server.py)
#   :11437 gateway         the one AI address; Gemini by default          (services/kindred_gateway.py)
#   :47811 brain           the mod connects here                          (brain/kindred)
#
# The helpers run at low CPU priority with thread counts picked for this computer
# (python -m kindred.hardware), so Minecraft keeps the CPU when both want it.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KH="${KINDRED_HOME:-$HOME/.kindred-spirit}"
LOGS="$KH/logs"; RUN="$KH/run"
mkdir -p "$LOGS" "$RUN"
BPY="$ROOT/brain/.venv/bin/python"
[[ -x "$BPY" ]] || { echo "Run scripts/setup.sh first."; exit 1; }
set -a; eval "$(cd "$ROOT/brain" && "$BPY" -m kindred.hardware --env)"; set +a
NICE="nice -n ${KINDRED_NICE:-10}"

up() { curl -s -o /dev/null --max-time 2 "$1"; }
start() { # name pidfile-name command...
  local name="$1"; shift
  nohup $NICE "$@" >> "$LOGS/$name.out" 2>&1 &
  echo $! > "$RUN/$name.pid"
}
wait_up() { for _ in $(seq 1 40); do up "$1" && return 0; sleep 0.25; done; return 1; }

# Speech-to-text: use the profile's model, or any model already downloaded.
if up http://127.0.0.1:8083/; then echo "whisper: already running"
elif command -v whisper-server >/dev/null; then
  M="$KH/whisper/$KINDRED_WHISPER_MODEL"
  [[ -s "$M" ]] || M="$(ls "$KH"/whisper/ggml-*.bin 2>/dev/null | grep -v silero | head -1)"
  if [[ -n "$M" ]]; then
    VAD=(); [[ -s "$KH/whisper/ggml-silero-v5.1.2.bin" ]] && VAD=(--vad -vm "$KH/whisper/ggml-silero-v5.1.2.bin")
    start whisper whisper-server -m "$M" --host 127.0.0.1 --port 8083 --inference-path /audio/transcriptions \
      -l en -t "$KINDRED_WHISPER_THREADS" -ac 768 "${VAD[@]}" -sns
    echo "whisper: started ($(basename "$M"), $KINDRED_WHISPER_THREADS threads)"
  else echo "whisper: no model in $KH/whisper (run scripts/setup.sh); voice input off"; fi
else echo "whisper: whisper-server not installed; voice input off (typing /kindred still works)"; fi

if up http://127.0.0.1:8090/; then echo "speech cleaner: already running"
else start speech-cleaner "$BPY" -I "$ROOT/services/speech_cleaner.py"; echo "speech cleaner: started"; fi

if up http://127.0.0.1:8885/health; then echo "kokoro voice: already running"
elif [[ -x "$KH/kokoro/venv/bin/python" && -s "$KH/kokoro/voices-v1.0.bin" ]]; then
  start kokoro "$KH/kokoro/venv/bin/python" -I "$ROOT/services/kokoro_server.py" --models "$KH/kokoro"
  echo "kokoro voice: starting ($KINDRED_TTS_THREADS threads)"
else echo "kokoro voice: not set up (scripts/setup.sh); subtitles only"; fi

if up http://127.0.0.1:11437/health; then echo "gateway: already running"
else start gateway "$BPY" -I "$ROOT/services/kindred_gateway.py" serve; echo "gateway: started"; fi

wait_up http://127.0.0.1:11437/health || echo "gateway did not come up: see $LOGS/gateway.out"
grep -qE '^(GEMINI_API_KEY)=.+' "$KH/secrets.env" 2>/dev/null || [[ -n "${GEMINI_API_KEY:-}" ]] \
  || echo "note: no GEMINI_API_KEY in $KH/secrets.env (fine if you switched the gateway to another AI)"

cd "$ROOT/brain"
if [[ "${1:-}" == "--background" ]]; then
  if (exec 3<>/dev/tcp/127.0.0.1/47811) 2>/dev/null; then echo "brain: already running"
  else nohup "$BPY" -m kindred >> "$LOGS/brain.out" 2>&1 & echo $! > "$RUN/brain.pid"; echo "brain: started"; fi
else
  echo "brain: running here (Ctrl+C to stop)"
  exec "$BPY" -m kindred
fi
