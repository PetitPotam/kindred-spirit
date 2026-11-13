#!/bin/bash
# Kindred Spirit Setup, macOS: what runs when you open the app (Contents/MacOS/kindred-setup).
#
# It starts the Setup with the app's own Python (Contents/Resources/payload) and opens it in your browser
# (http://127.0.0.1:11441, a page on this computer only): the guided steps the first time, and once she's set up,
# her dashboard (waking her first if she isn't running). If the Setup is already open, it just does that again.
# The Setup quits by itself a while after its page is closed (or with "Close the Setup").
#
# For tests: KINDRED_HOME, KINDRED_APP_DIR, KINDRED_SETUP_PORT (and the other KINDRED_*_PORT variables) keep a test
# away from the Pip you play with; KINDRED_SETUP_NO_BROWSER=1 doesn't open the browser.
set -u
HERE="$(cd "$(dirname "$0")/../Resources/payload" && pwd)"
PY="$HERE/python/bin/python3"
VERSION="$(cat "$HERE/VERSION" 2>/dev/null)"
PORT="${KINDRED_SETUP_PORT:-11441}"
URL="http://127.0.0.1:$PORT/open"
KH="${KINDRED_HOME:-$HOME/.kindred-spirit}"
LOG="$KH/logs/setup.out"
mkdir -p "$KH/logs"
[[ -f "$LOG" ]] && [[ $(wc -c < "$LOG") -gt 2000000 ]] && mv -f "$LOG" "$LOG.1"

hello() { /usr/bin/curl -s --max-time 2 "http://127.0.0.1:$PORT/api/setup/hello"; }
show() { [[ -n "${KINDRED_SETUP_NO_BROWSER:-}" ]] || /usr/bin/open "$URL"; }

answer="$(hello)"
if [[ "$answer" == *'"setup": true'* ]]; then
  if [[ "$answer" == *"\"version\": \"$VERSION\""* ]]; then show; exit 0; fi
  # another version of the Setup is open: this one takes over
  /usr/bin/curl -s --max-time 3 -X POST "http://127.0.0.1:$PORT/api/setup/quit" >/dev/null
  sleep 1
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') Kindred Spirit Setup $VERSION starting" >> "$LOG"
KINDRED_SETUP_PAYLOAD="$HERE" nohup "$PY" -I -B "$HERE/kindred/services/dashboard.py" --setup >> "$LOG" 2>&1 &
disown 2>/dev/null
for _ in $(seq 1 80); do
  if [[ "$(hello)" == *'"setup": true'* ]]; then show; exit 0; fi
  sleep 0.25
done

/usr/bin/osascript -e "display alert \"Kindred Spirit Setup couldn't start\" message \"Its log is in your home folder: .kindred-spirit/logs/setup.out. The guide (docs/SETUP.md on the project's GitHub page) says what to try, and how to ask an AI assistant for help with that log.\" as critical" >/dev/null 2>&1
exit 1
