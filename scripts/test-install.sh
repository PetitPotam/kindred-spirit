#!/bin/bash
# Checks that Kindred Spirit installs and runs on this computer, the way a player's would, without touching
# your own Pip: a throwaway home for her settings and for Minecraft, and moved ports. No AI key is needed: a
# stand-in AI (brain/tools/fake_ai.py) answers. Used by .github/workflows/platforms.yml and docs/TESTING-PLATFORMS.md.
#
#   scripts/test-install.sh brain       her brain's install (scripts/setup.sh --no-voice), then start it and check
#                                       that the gateway, the brain and the dashboard answer, and that she answers a
#                                       chat from a pretend game (brain/tools/fake_game.py) through the whole chain
#   scripts/test-install.sh minecraft   Minecraft's side (scripts/install_profile.py) into a throwaway Minecraft
#                                       folder: Fabric Loader, Fabric API, the mod and the launcher profile
#   scripts/test-install.sh setup-app   macOS: build Kindred Spirit Setup for this Mac's chip and run its smoke
#                                       test (setup/smoke_test.py)
#   scripts/test-install.sh all         every check that applies to this system
#
# KINDRED_PYTHON=/path/to/python skips setup.sh in "brain" and uses that Python (a brain venv you already have),
# so a local run doesn't create brain/.venv. Needs: bash, curl, Python 3.11+; Java (17+) and network for
# "minecraft"; macOS for "setup-app". Ports used: 11537 gateway, 11540 dashboard, 47911 brain, 11599 stand-in AI.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/kindred-test-XXXXXX")"
GW=11537; DASH=11540; BRAIN=47911; AI=11599
FAILED=0; PIDS=()

step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok() { printf '  \033[32mok\033[0m   %s\n' "$*"; }
bad() { printf '  \033[31mFAIL\033[0m %s\n' "$*"; FAILED=1; [[ -n "${GITHUB_ACTIONS:-}" ]] && echo "::error::$*"; return 0; }
unsupported() { # said out loud, never skipped silently
  printf '  \033[33mnot yet supported\033[0m %s\n' "$*"; [[ -n "${GITHUB_ACTIONS:-}" ]] && echo "::notice title=Not yet supported::$*"; return 0
}
up() { curl -s -o /dev/null --max-time 3 "$1"; }
free_port() { ! (exec 3<>/dev/tcp/127.0.0.1/"$1") 2>/dev/null; }
host_python() {
  for c in python3.13 python3.12 python3.11 python3; do
    command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' && { command -v "$c"; return; }
  done
}

cleanup() {
  [[ -n "${KH:-}" && -d "${KH:-}/run" ]] && HOME="$WORK/home" KINDRED_HOME="$KH" bash "$ROOT/scripts/stop.sh" >/dev/null 2>&1
  for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done
  if [[ $FAILED == 0 ]]; then rm -rf "$WORK"; else echo "  (kept for a look: $WORK)"; fi
}
trap cleanup EXIT

check_brain() {
  step "Her brain on $(uname -s) $(uname -m)"
  for p in $GW $DASH $BRAIN $AI; do free_port $p || { bad "port $p is in use: stop what uses it first"; return; }; done
  KH="$WORK/home/.kindred-spirit"; mkdir -p "$KH"
  # HOME too: a few files (her session logs) follow the home folder rather than KINDRED_HOME
  local real_home="$HOME"
  export HOME="$WORK/home" KINDRED_HOME="$KH" KINDRED_GATEWAY_PORT=$GW KINDRED_DASHBOARD_PORT=$DASH
  # her brain and the gateway on the test's ports, with the stand-in AI and nothing that needs a download
  printf '[server]\nport = %d\n\n[gateway]\nurl = "http://127.0.0.1:%d/v1"\n' $BRAIN $GW > "$KH/brain.toml"
  cat > "$KH/gateway.json" <<EOF
{"upstream": "fake", "upstreams": {"fake": {"base": "http://127.0.0.1:$AI/v1", "key": "", "model": "fake"}},
 "stt": {"use": "none"}, "tts": {"use": "none"}, "embeddings": {"use": "none"}}
EOF
  local py
  if [[ -n "${KINDRED_PYTHON:-}" ]]; then
    py="$KINDRED_PYTHON"; ok "using $py (setup.sh skipped)"
  else
    if bash "$ROOT/scripts/setup.sh" --no-voice > "$WORK/setup.log" 2>&1; then ok "scripts/setup.sh --no-voice"
    else bad "scripts/setup.sh --no-voice failed:"; tail -30 "$WORK/setup.log"; return; fi
    py="$ROOT/brain/.venv/bin/python"; export KINDRED_PYTHON="$py"
    [[ -f "$KH/secrets.env" && "$(stat -c %a "$KH/secrets.env" 2>/dev/null || stat -f %Lp "$KH/secrets.env")" == 600 ]] \
      && ok "secrets.env made, readable only by you" || bad "secrets.env missing or readable by others"
  fi
  "$py" -I "$ROOT/brain/tools/fake_ai.py" --port $AI > "$WORK/fake_ai.log" 2>&1 & PIDS+=($!); disown
  if bash "$ROOT/scripts/start.sh" --background > "$WORK/start.log" 2>&1; then ok "scripts/start.sh --background"
  else bad "scripts/start.sh failed:"; cat "$WORK/start.log"; fi
  local t
  for t in $(seq 1 60); do up "http://127.0.0.1:$GW/health" && ! free_port $BRAIN && up "http://127.0.0.1:$DASH/api/setup/hello" && break; sleep 0.5; done
  up "http://127.0.0.1:$GW/health" && ok "gateway answers (:$GW/health)" || bad "gateway doesn't answer"
  free_port $BRAIN && bad "her brain isn't listening on :$BRAIN" || ok "her brain listens (:$BRAIN)"
  up "http://127.0.0.1:$DASH/api/setup/hello" && ok "dashboard answers (:$DASH)" || bad "dashboard doesn't answer"
  local said
  said="$(cd "$ROOT/brain" && "$py" tools/fake_game.py chat "Hi Pip, are you there?" --quiet --wait 40 2>&1)"
  if grep -q "SAY .*test answer" <<<"$said"; then ok "she answered a pretend game: $(grep -o 'SAY.*' <<<"$said" | head -1)"
  else bad "no answer to a pretend game's chat:"; echo "$said" | tail -10; fi
  if [[ $FAILED == 1 ]]; then
    for f in gateway brain dashboard; do [[ -f "$KH/logs/$f.out" ]] && { echo "--- $f.out"; tail -25 "$KH/logs/$f.out"; }; done
  fi
  bash "$ROOT/scripts/stop.sh" >/dev/null 2>&1
  unset KINDRED_HOME KINDRED_GATEWAY_PORT KINDRED_DASHBOARD_PORT
  export HOME="$real_home"
}

check_minecraft() {
  step "Minecraft's side (Fabric Loader, Fabric API, the mod, the launcher profile)"
  local jar
  jar="$(ls "$ROOT"/mod/build/libs/kindred-spirit-*.jar 2>/dev/null | grep -v -- -sources | head -1)"
  if [[ -z "$jar" ]]; then
    (cd "$ROOT/mod" && ./gradlew build -x test --quiet --no-daemon) > "$WORK/gradle.log" 2>&1 \
      && ok "built the mod" || { bad "the mod didn't build:"; tail -30 "$WORK/gradle.log"; return; }
  fi
  local home="$WORK/mc-home" mc
  case "$(uname -s)" in Darwin) mc="$home/Library/Application Support/minecraft" ;; *) mc="$home/.minecraft" ;; esac
  mkdir -p "$mc"; echo '{"profiles": {}}' > "$mc/launcher_profiles.json"  # as the launcher leaves it after its first start
  local py; py="$(host_python)"
  if HOME="$home" "$py" "$ROOT/scripts/install_profile.py" > "$WORK/profile.log" 2>&1; then ok "scripts/install_profile.py"
  else bad "scripts/install_profile.py failed:"; tail -20 "$WORK/profile.log"; return; fi
  local game; game="$(sed -n 's/^Profile game folder: *//p' "$WORK/profile.log")"
  ls "$mc"/versions/fabric-loader-*-1.21.1/*.json >/dev/null 2>&1 && ok "Fabric Loader installed" || bad "no Fabric Loader version"
  ls "$game"/mods/fabric-api-*.jar >/dev/null 2>&1 && ok "Fabric API in the profile's mods" || bad "no Fabric API in $game/mods"
  ls "$game"/mods/kindred-spirit-*.jar >/dev/null 2>&1 && ok "the Kindred jar in the profile's mods" || bad "no Kindred jar in $game/mods"
  "$py" -c 'import json,sys; p=json.load(open(sys.argv[1]))["profiles"]["kindred-spirit"]; assert p["gameDir"] and p["lastVersionId"].startswith("fabric-loader-")' \
    "$mc/launcher_profiles.json" 2>/dev/null && ok "launcher profile \"Kindred Spirit (Fabric 1.21.1)\"" || bad "no launcher profile"
}

check_setup_app() {
  step "Kindred Spirit Setup (macOS app)"
  [[ "$(uname -s)" == Darwin ]] || { unsupported "Kindred Spirit Setup is macOS-only so far (Windows: #40, Linux: #81)"; return; }
  local arch py; arch="$(uname -m)"; [[ "$arch" == arm64 ]] || arch=x86_64; py="$(host_python)"
  if "$py" "$ROOT/setup/build.py" --arch "$arch" --out "$WORK/dist" > "$WORK/build.log" 2>&1; then ok "built: $(tail -1 "$WORK/build.log" | sed 's/.*done: //')"
  else bad "setup/build.py failed:"; tail -30 "$WORK/build.log"; return; fi
  if "$py" "$ROOT/setup/smoke_test.py" "$WORK"/dist/*.dmg > "$WORK/smoke.log" 2>&1; then ok "installed and started from the .dmg (setup/smoke_test.py)"
  else bad "setup/smoke_test.py failed:"; cat "$WORK/smoke.log"; fi
  [[ -n "${KINDRED_KEEP_DMG:-}" ]] && cp "$WORK"/dist/* "$KINDRED_KEEP_DMG"/ 2>/dev/null
  return 0
}

case "${1:-all}" in
  brain) check_brain ;;
  minecraft) check_minecraft ;;
  setup-app) check_setup_app ;;
  all) check_brain; check_minecraft; check_setup_app ;;
  *) sed -n '2,20p' "$0"; exit 2 ;;
esac
if [[ "$(uname -s)" == Linux ]]; then
  unsupported "On Linux the brain installs with scripts/setup.sh (checked above when asked); her voice and hearing, and a Setup app, are #81"
fi
step "$([[ $FAILED == 0 ]] && echo "All checks passed" || echo "Some checks FAILED")"
exit $FAILED
