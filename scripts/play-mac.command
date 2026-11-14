#!/bin/bash
# macOS: double-click to play. Starts her (the version in use), then opens the Minecraft Launcher FROM THIS
# TERMINAL. That matters: the launcher has no microphone permission of its own, so started from the Dock the game
# records silence; started from Terminal it uses Terminal's permission. Keep this window open while you play.
#
# Which version (#188, #190): it asks (the installed release, the newest code, or a pull request), the one in use
# being the default (Enter, or after 10 seconds); switching builds and installs the matching mod and brain with
# scripts/play-latest.sh. `--dry-run` only says which is in use and starts nothing; `--no-menu` doesn't ask.
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

choose() { # asks which Pip to play; switches with play-latest.sh, then starts again without asking
  local now installed_v choice pr
  installed_v="$(cat "$INSTALLED/VERSION" 2>/dev/null || echo "?")"
  [[ -f "$KH/playing-from" ]] && now=2 || now=1
  echo "Which Pip do you want to play?"
  echo "  1) The installed release ($installed_v)$([[ $now == 1 ]] && echo "      <- you're on this")"
  echo "  2) The newest code from GitHub (builds the mod first, about 2 minutes)$([[ $now == 2 ]] && echo "  <- you're on this: $(cat "$KH/playing-from")")"
  echo "  3) A pull request, to try it before it's merged"
  printf 'Press Enter (or wait 10 seconds) to keep %s: ' "$now"
  read -r -t 10 choice || true
  echo
  choice="${choice:-$now}"
  case "$choice" in
    1) [[ $now == 2 ]] && { bash "$ROOT/scripts/play-latest.sh" --back || return 1; } ;;
    2) bash "$ROOT/scripts/play-latest.sh" main || return 1 ;;
    3) printf 'Pull request number: '; read -r pr
       [[ "$pr" =~ ^[0-9]+$ ]] || { echo "Not a number: keeping what you're on."; return 0; }
       bash "$ROOT/scripts/play-latest.sh" "$pr" || return 1 ;;
    *) echo "Keeping what you're on." ;;
  esac
  return 0
}

profiles() { # the Kindred profiles' names, as the launcher shows them
  local base n
  base="$(dirname "${KINDRED_MINECRAFT_DIR:-$HOME/Library/Application Support/minecraft}")"
  for d in "$base"/minecraft-kindred "$base"/minecraft-kindred-*; do
    [[ -d "$d/mods" ]] || continue
    n="$(basename "$d")"
    [[ "$n" == minecraft-kindred ]] && echo "Kindred Spirit (Fabric 1.21.1)" || echo "Kindred Spirit (Fabric ${n#minecraft-kindred-})"
  done
}

if [[ "${1:-}" == --dry-run ]]; then
  echo "Playing $which."
  exit 0
fi
if [[ "${1:-}" != --no-menu && -t 0 && -x "$INSTALLED/python/bin/python3" ]]; then
  if choose; then
    exec "$0" --no-menu  # (again, for the version now in use)
  fi
  echo "Couldn't switch (see above): playing what you're on."
fi
echo "Playing $which."
start
echo
names="$(profiles | sed 's/^/  /')"
echo "Opening the Minecraft Launcher: pick a Kindred Spirit profile and press Play."
[[ -n "$names" ]] && echo "$names"
echo "In game: hold V to talk, or just type in chat (on a server: start with her name). K opens her dashboard."
echo "Switch versions: scripts/play-latest.sh (the newest code) or scripts/play-latest.sh --back (the installed one)."
[[ -n "${KINDRED_NO_LAUNCHER:-}" ]] || /Applications/Minecraft.app/Contents/MacOS/launcher >/dev/null 2>&1  # (tests skip it)
