#!/bin/bash
# Playtest the newest code without making a release (#185): build the mod for every Minecraft version from this
# checkout, put the matching jar in each Kindred profile, and run her brain and services from this checkout instead
# of the copy the Setup installed. One command puts the installed version back.
#
#   scripts/play-latest.sh            main, updated from GitHub
#   scripts/play-latest.sh 184        pull request #184 (to try it before merging)
#   scripts/play-latest.sh branch batch/2026-11-14-polish   a local branch (where it's open, as it is)
#   scripts/play-latest.sh here       this checkout as it is (your branch, uncommitted changes included)
#   scripts/play-latest.sh --back     back to the version the Setup installed (its jars, its brain)
#   scripts/play-latest.sh --status   which one is in use
#
# Close Minecraft first: a running game keeps its mod until it restarts. Your settings and memories
# (~/.kindred-spirit) are shared by both, so nothing is lost either way. The mod built here is named
# <version>-dev.<commit> (the logs and the dashboard show it), so it's never mistaken for a release.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KH="${KINDRED_HOME:-$HOME/.kindred-spirit}"
INSTALLED="${KINDRED_APP_DIR:-$HOME/Library/Application Support/Kindred Spirit}/current"
MARK="$KH/playing-from"
what="${1:-main}"

say() { printf '%s\n' "$*"; }
die() { printf 'play-latest: %s\n' "$*" >&2; exit 1; }

profiles() { # each Kindred profile's game folder (minecraft-kindred = 1.21.1, minecraft-kindred-<version>)
  local base
  base="$(dirname "${KINDRED_MINECRAFT_DIR:-$HOME/Library/Application Support/minecraft}")"
  for d in "$base"/minecraft-kindred "$base"/minecraft-kindred-* "$base"/.minecraft-kindred "$base"/.minecraft-kindred-*; do
    [[ -d "$d/mods" ]] && echo "$d"
  done
  return 0
}
mc_of() { local n; n="$(basename "$1")"; n="${n#.}"; [[ "$n" == minecraft-kindred ]] && echo 1.21.1 || echo "${n#minecraft-kindred-}"; }

game_running() { ps -ax -o command | grep -v grep | grep -i java | grep -qiE "knot|net\.minecraft\.client"; }

put_jars() { # $1: the folder with kindred-spirit-<v>+<mc>.jar files; $2: the version (any, if empty: one per Minecraft)
  local from="$1" want="${2:-}" put=0
  while read -r game; do
    local mc jar
    mc="$(mc_of "$game")"
    if [[ -n "$want" ]]; then jar="$from/kindred-spirit-$want+$mc.jar"; [[ -f "$jar" ]] || jar=""
    else jar="$(ls "$from"/kindred-spirit-*+"$mc".jar 2>/dev/null | grep -v -- -sources | head -1 || true)"; fi
    if [[ -z "$jar" ]]; then say "  $(basename "$game"): no jar for Minecraft $mc here, left as it was"; continue; fi
    rm -f "$game"/mods/kindred-spirit-*.jar
    cp "$jar" "$game/mods/"
    say "  $(basename "$game") (Minecraft $mc): $(basename "$jar")"
    put=$((put + 1))
  done < <(profiles)
  [[ $put -gt 0 ]] || die "no Kindred profile found to put the mod in (install one with the Setup first)"
}

java_home() {
  [[ -n "${JAVA_HOME:-}" ]] && { echo "$JAVA_HOME"; return; }
  /usr/libexec/java_home -v 25 2>/dev/null && return
  for d in /opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home /usr/local/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home; do
    [[ -d "$d" ]] && { echo "$d"; return; }
  done
  die "no JDK 25 found (brew install openjdk@25)"
}

case "$what" in
  --status)
    [[ -f "$MARK" ]] && say "Playing from the checkout: $(cat "$MARK")" || say "Playing the version the Setup installed ($(cat "$INSTALLED/VERSION" 2>/dev/null || echo "none"))."
    exit 0 ;;
  --back)
    game_running && die "close Minecraft first"
    [[ -d "$INSTALLED" ]] || die "no installed version at $INSTALLED (install with the Setup)"
    say "Back to the version the Setup installed ($(cat "$INSTALLED/VERSION")):"
    bash "$ROOT/scripts/stop.sh" || true
    put_jars "$INSTALLED/mods" "$(cat "$INSTALLED/VERSION")"
    (cd "$INSTALLED/kindred" && KINDRED_PYTHON="$INSTALLED/python/bin/python3" KINDRED_HOME="$KH" \
      bash scripts/start.sh --background) || die "the installed version didn't start (open the Setup app: Wake her up)"
    rm -f "$MARK"
    say "Done: play as usual. (Back to the checkout: scripts/play-latest.sh)"
    exit 0 ;;
  -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
esac

game_running && die "close Minecraft first"
cd "$ROOT"
# Where to build: never by switching this checkout's branch (someone may be working in it). main and pull requests are
# built in a separate play copy (a git worktree in ~/.kindred-spirit/play-checkout); a branch that's open in a worktree
# (this checkout included) is built right there, as it is; another branch goes to the play copy too.
PLAY="$KH/play-checkout"
play_copy() { # $1: what to check out there (a commit, detached)
  if [[ ! -d "$PLAY/.git" && ! -f "$PLAY/.git" ]]; then
    git worktree add -q --detach "$PLAY" "$1" || die "couldn't make the play copy in $PLAY"
  else
    (cd "$PLAY" && git checkout -q --detach "$1") || die "couldn't check out $1 in $PLAY"
  fi
  TARGET="$PLAY"
}
worktree_of() { # the worktree that has branch $1 checked out, if any
  git worktree list --porcelain | awk -v b="refs/heads/$1" '/^worktree /{w=substr($0,10)} $0=="branch "b{print w; exit}'
}
label=""
case "$what" in
  main)
    git fetch -q origin main || die "couldn't get main from GitHub"
    play_copy origin/main; label="main" ;;
  here)
    TARGET="$ROOT"; label="$(git branch --show-current) (as it is)" ;;
  branch)
    name="${2:-}"; [[ -n "$name" ]] || die "which branch? scripts/play-latest.sh branch <name>"
    git rev-parse -q --verify "refs/heads/$name" >/dev/null || die "no local branch named $name"
    wt="$(worktree_of "$name")"
    if [[ -n "$wt" ]]; then TARGET="$wt"; else play_copy "$name"; fi
    label="$name" ;;
  *)
    if [[ "$what" =~ ^[0-9]+$ ]]; then
      git fetch -q origin "pull/$what/head:refs/remotes/origin/pr/$what" --force || die "couldn't get pull request #$what"
      play_copy "origin/pr/$what"; label="pull request #$what"
    else
      die "unknown: $what (main, a pull request number, branch <name>, here, --back or --status)"
    fi ;;
esac
cd "$TARGET"
sha="$(git rev-parse --short HEAD)"
base="$(grep '^mod_version=' mod/gradle.properties | cut -d= -f2)"
version="$base-dev.$sha"
say "Building $label ($sha) as $version, for every Minecraft version..."
(cd mod && JAVA_HOME="$(java_home)" ./gradlew build -x test -q -Pmod_version="$version") || die "the mod didn't build"
PY="$ROOT/brain/.venv/bin/python"  # (one Python for every copy: this checkout's)
"$PY" -m pip install -q -r "$TARGET/brain/requirements.txt" 2>/dev/null || true
say "The mod in each Kindred profile:"
put_jars "$TARGET/mod/build/libs" "$version"  # (exactly this build: the folder also keeps older versions' jars)
ls "$TARGET"/mod/build/libs/kindred-spirit-*-dev.*.jar 2>/dev/null | grep -v "$sha" | xargs rm -f 2>/dev/null || true
say "Her brain and services from $label:"
bash "$ROOT/scripts/stop.sh" || true
KINDRED_PYTHON="$PY" bash "$TARGET/scripts/start.sh" --background || die "her brain didn't start (scripts/start.sh says why)"
printf '%s %s (%s), %s\n' "$label" "$sha" "$version" "$(date '+%Y-%m-%d %H:%M')" > "$MARK"
say ""
say "Ready: open Minecraft and play the Kindred Spirit profile. In game, /kindred status shows mod $version."
say "Back to the installed version: scripts/play-latest.sh --back"
