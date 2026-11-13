#!/bin/bash
# Starts the helpers that are not already running, then the brain.
#
#   scripts/start.sh               brain in this window (Ctrl+C stops it; helpers keep running)
#   scripts/start.sh --background  everything in the background (logs in ~/.kindred-spirit/logs)
#   scripts/stop.sh                stops what this script started
#
#   :11437 gateway         the one address for AI, speech-to-text, voice, embeddings and memory
#                          (services/kindred_gateway.py; what it uses: docs/GATEWAY.md)
#   local tools the gateway may use (started only if gateway.json says so):
#   :8083 whisper-server   speech-to-text (Metal GPU on Apple silicon), tuned for 15 s push-to-talk clips
#   :8885 kokoro           the companion's voice                          (services/kokoro_server.py)
#   :8891 embeddings       what memories mean, for recall                 (services/embed_server.py)
#   :47811 brain           the mod connects here                          (brain/kindred)
#   :11440 dashboard       what she's doing, thinking and remembering: open http://127.0.0.1:11440
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
rotate() { # a .out file over 5 MB moves to .out.1 (one kept), so logs never fill the disk (#26)
  local f="$LOGS/$1.out"
  [[ -f "$f" ]] && [[ $(wc -c < "$f") -gt 5000000 ]] && mv -f "$f" "$f.1"
  return 0
}
start() { # name pidfile-name command...
  local name="$1"; shift
  rotate "$name"
  nohup $NICE "$@" >> "$LOGS/$name.out" 2>&1 &
  echo $! > "$RUN/$name.pid"
}
wait_up() { for _ in $(seq 1 40); do up "$1" && return 0; sleep 0.25; done; return 1; }

# Which local tools does the gateway use? (docs/GATEWAY.md: each part can be local or a service)
uses() { "$BPY" -c "import json,os,sys; p=os.path.expanduser('$KH/gateway.json'); s=json.load(open(p)) if os.path.exists(p) else {}; print(s.get(sys.argv[1],{}).get('use',sys.argv[2]))" "$1" "$2"; }
STT_USE="$(uses stt local_whisper)"; TTS_USE="$(uses tts local_kokoro)"; EMB_USE="$(uses embeddings local)"

# Speech-to-text, local Whisper: the profile's model, or any model already downloaded.
if [[ "$STT_USE" != "local_whisper" ]]; then echo "whisper: not used (speech-to-text: $STT_USE)"
elif up http://127.0.0.1:8083/; then echo "whisper: already running"
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

if [[ "$TTS_USE" != "local_kokoro" ]]; then echo "kokoro voice: not used (voice: $TTS_USE)"
elif up http://127.0.0.1:8885/health; then echo "kokoro voice: already running"
elif [[ -x "$KH/kokoro/venv/bin/python" && -s "$KH/kokoro/voices-v1.0.bin" ]]; then
  start kokoro "$KH/kokoro/venv/bin/python" -I "$ROOT/services/kokoro_server.py" --models "$KH/kokoro"
  echo "kokoro voice: starting ($KINDRED_TTS_THREADS threads)"
else echo "kokoro voice: not set up (scripts/setup.sh); subtitles only"; fi

if [[ "$EMB_USE" != "local" ]]; then echo "embeddings: not local (embeddings: $EMB_USE)"
elif up http://127.0.0.1:8891/; then echo "embeddings: already running"
elif [[ -x "$KH/embed/venv/bin/python" ]]; then
  KINDRED_EMBED_THREADS=1 start embed "$KH/embed/venv/bin/python" -I "$ROOT/services/embed_server.py" --cache "$KH/embed/models"
  echo "embeddings: starting (local, for memory)"
else echo "embeddings: not set up (scripts/setup.sh); memory uses keyword search"; fi

if up http://127.0.0.1:11437/health; then echo "gateway: already running"
else start gateway "$BPY" -I "$ROOT/services/kindred_gateway.py" serve; echo "gateway: started"; fi

wait_up http://127.0.0.1:11437/health || echo "gateway did not come up: see $LOGS/gateway.out"

if up http://127.0.0.1:11440/api/settings; then echo "dashboard: already running (http://127.0.0.1:11440)"
else start dashboard "$BPY" -I "$ROOT/services/dashboard.py"; echo "dashboard: http://127.0.0.1:11440"; fi
grep -qE '^(GEMINI_API_KEY)=.+' "$KH/secrets.env" 2>/dev/null || [[ -n "${GEMINI_API_KEY:-}" ]] \
  || echo "note: no GEMINI_API_KEY in $KH/secrets.env (fine if you switched the gateway to another AI)"

cd "$ROOT/brain"
if [[ "${1:-}" == "--background" ]]; then
  if (exec 3<>/dev/tcp/127.0.0.1/47811) 2>/dev/null; then echo "brain: already running"
  else rotate brain; nohup "$BPY" -m kindred >> "$LOGS/brain.out" 2>&1 & echo $! > "$RUN/brain.pid"; echo "brain: started"; fi
else
  echo "brain: running here (Ctrl+C to stop)"
  exec "$BPY" -m kindred
fi
