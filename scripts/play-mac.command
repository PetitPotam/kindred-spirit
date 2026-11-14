#!/bin/bash
# macOS: double-click to play. Starts her (the version in use), then opens the Minecraft Launcher FROM THIS
# TERMINAL. That matters: the launcher has no microphone permission of its own, so started from the Dock the game
# records silence; started from Terminal it uses Terminal's permission. Keep this window open while you play.
#
# Which version (#188): the checkout when scripts/play-latest.sh switched to it (~/.kindred-spirit/playing-from),
# otherwise the copy the Setup installed, otherwise this checkout. `--dry-run` only says which, and starts nothing.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
KH="${KINDRED_HOME:-$HOME/.kindred-spirit}"
INSTALLED="${KINDRED_APP_DIR:-$HOME/Library/Application Support/Kindred Spirit}/current"

if [[ -f "$KH/playing-from" ]]; then
  which="the checkout: $(cat "$KH/playing-from")"
  start() { bash "$ROOT/scripts/start.sh" --background; }
elif [[ -x "$INSTALLED/python/bin/python3" && -f "$INSTALLED/kindred/scripts/start.sh" ]]; then
  which="the version the Setup installed ($(cat "$INSTALLED/VERSION" 2>/dev/null || echo "?"))"
  start() { (cd "$INSTALLED/kindred" && KINDRED_PYTHON="$INSTALLED/python/bin/python3" KINDRED_HOME="$KH" \
             bash scripts/start.sh --background); }
else
  which="this checkout (no Setup installed)"
  start() { bash "$ROOT/scripts/start.sh" --background; }
fi

profiles() { # the Kindred profiles' names, as the launcher shows them
  local base n
  base="$(dirname "${KINDRED_MINECRAFT_DIR:-$HOME/Library/Application Support/minecraft}")"
  for d in "$base"/minecraft-kindred "$base"/minecraft-kindred-*; do
    [[ -d "$d/mods" ]] || continue
    n="$(basename "$d")"
    [[ "$n" == minecraft-kindred ]] && echo "Kindred Spirit (Fabric 1.21.1)" || echo "Kindred Spirit (Fabric ${n#minecraft-kindred-})"
  done
}

echo "Playing $which."
if [[ "${1:-}" == --dry-run ]]; then
  exit 0
fi
start
echo
names="$(profiles | sed 's/^/  /')"
echo "Opening the Minecraft Launcher: pick a Kindred Spirit profile and press Play."
[[ -n "$names" ]] && echo "$names"
echo "In game: hold V to talk, or just type in chat (on a server: start with her name). K opens her dashboard."
echo "Switch versions: scripts/play-latest.sh (the newest code) or scripts/play-latest.sh --back (the installed one)."
/Applications/Minecraft.app/Contents/MacOS/launcher >/dev/null 2>&1
