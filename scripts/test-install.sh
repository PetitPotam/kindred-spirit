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
#   scripts/test-install.sh client      a real Minecraft client (the dev client, ./gradlew :<version>:runClient, for
#                                       every version in mod/versions/ or only $KINDRED_MINECRAFT) with Fabric,
#                                       Fabric API and the mod opens a world, says hi, and she answers through her
#                                       brain. Uses the default places (~/.kindred-spirit, port 47811), so it runs
#                                       only on a clean machine (CI, a VM, Docker) with KINDRED_TEST_CLEAN_MACHINE=1,
#                                       and refuses if a Pip is set up here. Linux needs xvfb. Not part of "all".
#   scripts/test-install.sh all         every check that applies to this system (not "client")
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
  for p in ${PIDS[@]+"${PIDS[@]}"}; do kill "$p" 2>/dev/null; done
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
  # her live dashboard, as the player opens it: the page and what its main tabs read
  local what path want
  while IFS='|' read -r what path want; do
    if grep -qF "$want" <<<"$(curl -s --max-time 10 "http://127.0.0.1:$DASH$path")"; then ok "dashboard: $what ($path)"
    else bad "dashboard: $what ($path) didn't answer as expected"; fi
  done <<'PAGES'
the page|/|Kindred Dashboard
settings|/api/settings|"gateway"
live (her heart and mood)|/api/live|"health"
sessions|/api/sessions|"sessions"
blueprints|/api/blueprints|{
the Setup steps|/setup|Kindred Spirit Setup
PAGES
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
  local models=(); [[ -n "${KINDRED_TEST_MODELS:-}" ]] && models=(--models)  # downloads her models too (CI)
  if "$py" "$ROOT/setup/smoke_test.py" ${models[@]+"${models[@]}"} "$WORK"/dist/*.dmg > "$WORK/smoke.log" 2>&1; then
    ok "installed and started from the .dmg (setup/smoke_test.py${models:+ --models: her instincts, voice and hearing too})"
    grep -E "^-- (instincts|voice|hearing|\"Hear)" "$WORK/smoke.log" | sed 's/^--/      /'
  else
    bad "setup/smoke_test.py failed: $(grep -E "AssertionError|still running|Error|FAILED" "$WORK/smoke.log" | tail -1)"
    cat "$WORK/smoke.log"
  fi
  [[ -n "${KINDRED_KEEP_DMG:-}" ]] && cp "$WORK"/dist/* "$KINDRED_KEEP_DMG"/ 2>/dev/null
  return 0
}

check_client() {
  step "A real Minecraft client reaches her brain (#105)"
  if [[ -e "$HOME/.kindred-spirit" || -z "${KINDRED_TEST_CLEAN_MACHINE:-}" ]]; then
    bad "this check uses the real ~/.kindred-spirit and port 47811: run it on a clean machine with KINDRED_TEST_CLEAN_MACHINE=1 (CI does)"
    return
  fi
  for p in 11437 11440 47811 $AI; do free_port $p || { bad "port $p is in use"; return; }; done
  KH="$HOME/.kindred-spirit"; mkdir -p "$KH"
  printf '{"upstream": "fake", "upstreams": {"fake": {"base": "http://127.0.0.1:%d/v1", "key": "", "model": "fake"}},\n "stt": {"use": "none"}, "tts": {"use": "none"}, "embeddings": {"use": "none"}}\n' $AI > "$KH/gateway.json"
  local py="${KINDRED_PYTHON:-}"
  if [[ -z "$py" ]]; then
    bash "$ROOT/scripts/setup.sh" --no-voice > "$WORK/setup.log" 2>&1 || { bad "scripts/setup.sh failed"; tail -30 "$WORK/setup.log"; return; }
    py="$ROOT/brain/.venv/bin/python"; export KINDRED_PYTHON="$py"
  fi
  "$py" -I "$ROOT/brain/tools/fake_ai.py" --port $AI > "$WORK/fake_ai.log" 2>&1 & PIDS+=($!); disown
  bash "$ROOT/scripts/start.sh" --background > "$WORK/start.log" 2>&1
  local t
  for t in $(seq 1 60); do ! free_port 47811 && break; sleep 0.5; done
  if free_port 47811; then bad "her brain didn't start"; cat "$WORK/start.log"; return; fi
  ok "her brain, the gateway and a stand-in AI are running"
  # every Minecraft version the mod is built for (mod/versions/), or only KINDRED_MINECRAFT (e.g. 26.3)
  local mc versions="${KINDRED_MINECRAFT:-$(ls "$ROOT/mod/versions")}"
  for mc in $versions; do client_run "$mc" "$KH/logs/brain.log"; done
  bash "$ROOT/scripts/stop.sh" >/dev/null 2>&1
  return 0
}

# One Minecraft version's dev client (./gradlew :<version>:runClient): open a world, say hi, check she answered.
client_run() {
  local mc="$1" brainlog="$2" runDir="$ROOT/mod/versions/$1/run"
  step "Minecraft $mc"
  # (the time stops with doDaylightCycle up to 1.21.x and advance_time after; the other line only prints an error)
  printf '%s\n' "# scripts/test-install.sh client: open a world, say hi, wait for her answer, take a picture, quit" \
    "world kindred-ci" "wait 300" "cmd gamerule doDaylightCycle false" "cmd gamerule advance_time false" "cmd time set 1000" \
    "chat Hi Pip, are you there?" "waitsay 1200" "wait 60" "screenshot ci-answer" "wait 20" "quit" > "$WORK/client.txt"
  local answered_before=0
  answered_before=$(grep -c "you: Hi Pip.*test answer" "$brainlog" 2>/dev/null) || answered_before=0
  # Minecraft's assets first, with a second try: Loom's parallel download sometimes trips over its own .part files
  ( cd "$ROOT/mod" && { ./gradlew ":$mc:downloadAssets" --no-daemon -q || ./gradlew ":$mc:downloadAssets" --no-daemon -q; } ) \
    > "$WORK/assets-$mc.log" 2>&1 || { bad "Minecraft $mc's assets didn't download:"; tail -20 "$WORK/assets-$mc.log"; return; }
  local run=(./gradlew ":$mc:runClient" --no-daemon --console=plain "-PdevScript=$WORK/client.txt")
  if [[ "$(uname -s)" == Linux ]]; then
    # 26.x opens its window with SDL and asks for an sRGB-capable OpenGL 3.3 framebuffer, which Xvfb's GLX visuals
    # don't offer ("Couldn't find matching GLX visual"); through EGL, Mesa has one. (1.21.x uses GLFW: no effect.)
    run=(env SDL_VIDEO_FORCE_EGL=1 "${run[@]}")
    [[ -z "${DISPLAY:-}" ]] && run=(xvfb-run -a -s "-screen 0 1280x720x24" "${run[@]}")
  fi
  local limit="${KINDRED_CLIENT_MINUTES:-12}"
  ( cd "$ROOT/mod" && "${run[@]}" ) > "$WORK/client-$mc.log" 2>&1 &
  local pid=$! waited=0 code
  # each game gets its own time limit, so a game that hangs fails fast and says which Minecraft it was
  local game="$runDir/logs/latest.log" nobackend=""
  rm -f "$game"
  while kill -0 "$pid" 2>/dev/null && (( waited < limit * 60 )); do
    sleep 5; waited=$((waited + 5))
    # no graphics backend at all: the game shows an error box nobody can close here, so stop now and say why
    if grep -q "Failed to create backend Vulkan" "$game" 2>/dev/null && ! grep -q "Backend: \|Using backend\|Created device" "$game" 2>/dev/null \
        && grep -q "Failed to create backend OpenGL" "$game" 2>/dev/null; then nobackend=1; break; fi
  done
  if [[ -n "$nobackend" ]]; then
    bad "Minecraft $mc found no graphics it can use here (OpenGL and Vulkan both failed):"
    grep -A2 "Failed to create backend" "$game" | head -12
    pkill -f "kindredspirit.devScript=$WORK/client.txt"; sleep 10
    pkill -9 -f "kindredspirit.devScript=$WORK/client.txt"; kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
    return 0
  fi
  if kill -0 "$pid" 2>/dev/null; then
    bad "Minecraft $mc didn't finish in $limit minutes; where its threads were, the end of its log and Gradle's:"
    local gpid
    for gpid in $(pgrep -f "kindredspirit.devScript=$WORK/client.txt"); do
      jcmd "$gpid" Thread.print 2>/dev/null | grep -A 25 -E '^"(Render thread|main|Server thread)"' | head -90
    done
    tail -60 "$game" 2>/dev/null; tail -30 "$WORK/client-$mc.log"
    pkill -f "kindredspirit.devScript=$WORK/client.txt"; sleep 10
    pkill -9 -f "kindredspirit.devScript=$WORK/client.txt"; kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
    return 0
  fi
  wait "$pid"; code=$?
  if [[ $code == 0 ]]; then ok "the game started and quit by itself"; else bad "the game exited with $code:"; tail -40 "$WORK/client-$mc.log"; tail -40 "$game" 2>/dev/null; fi
  grep -q "kindredspirit" "$game" 2>/dev/null && ok "Fabric loaded the mod (with Fabric API)" || bad "the mod isn't in the game's log"
  if ls "$runDir"/crash-reports/*.txt >/dev/null 2>&1; then bad "the game crashed:"; tail -40 "$(ls -t "$runDir"/crash-reports/*.txt | head -1)"; fi
  grep -q "game connected" "$brainlog" 2>/dev/null && ok "the game connected to her brain" || bad "the game never connected to her brain"
  grep -q "mod .* on Minecraft $mc" "$brainlog" 2>/dev/null && ok "$(grep -o "mod .* on Minecraft $mc.*" "$brainlog" | tail -1)" \
    || bad "her brain didn't hear from Minecraft $mc"
  local answered=0
  answered=$(grep -c "you: Hi Pip.*test answer" "$brainlog" 2>/dev/null) || answered=0
  if (( answered > answered_before )); then ok "she answered in the game: $(grep -o 'you: Hi Pip.*' "$brainlog" | tail -1)"
  else bad "she didn't answer the hi:"; tail -30 "$brainlog" 2>/dev/null; fi
  if [[ -n "${KINDRED_KEEP_SCREENSHOT:-}" ]]; then
    mkdir -p "$KINDRED_KEEP_SCREENSHOT/$mc"
    cp "$runDir"/screenshots/ci-answer*.png "$WORK/client-$mc.log" "$game" "$KINDRED_KEEP_SCREENSHOT/$mc"/ 2>/dev/null
  fi
  return 0
}

case "${1:-all}" in
  brain) check_brain ;;
  minecraft) check_minecraft ;;
  setup-app) check_setup_app ;;
  client) check_client ;;
  all) check_brain; check_minecraft; check_setup_app ;;
  *) sed -n '2,20p' "$0"; exit 2 ;;
esac
if [[ "$(uname -s)" == Linux ]]; then
  unsupported "On Linux the brain installs with scripts/setup.sh (checked above when asked); her voice and hearing, and a Setup app, are #81"
fi
step "$([[ $FAILED == 0 ]] && echo "All checks passed" || echo "Some checks FAILED")"
exit $FAILED
