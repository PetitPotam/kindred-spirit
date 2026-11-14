#!/bin/bash
# Run every test: the mod's (Gradle, JUnit) and the brain's (pytest). Works from any folder and in any checkout or
# git worktree (a worktree without its own brain/.venv uses the main checkout's).
#   scripts/test.sh          both
#   scripts/test.sh brain    only the brain's (fast, no Java)
#   scripts/test.sh mod      only the mod's
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
what="${1:-all}"
fail=0

python() { # the brain's venv: this checkout's, else the main checkout's (worktrees share it), else python3
  local main
  main="$(cd "$ROOT" && git rev-parse --path-format=absolute --git-common-dir 2>/dev/null | sed 's#/\.git$##')"
  for p in "$ROOT/brain/.venv/bin/python" "$main/brain/.venv/bin/python"; do [[ -x "$p" ]] && { echo "$p"; return; }; done
  command -v python3
}

java_home() { # a JDK 25 runs Gradle (it builds the mod for every Minecraft version)
  [[ -n "${JAVA_HOME:-}" ]] && { echo "$JAVA_HOME"; return; }
  /usr/libexec/java_home -v 25 2>/dev/null && return
  for d in /opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home /usr/local/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home \
           /usr/lib/jvm/temurin-25-jdk-amd64 /usr/lib/jvm/java-25-openjdk-amd64; do
    [[ -d "$d" ]] && { echo "$d"; return; }
  done
}

if [[ "$what" == all || "$what" == brain ]]; then
  echo "== brain (ruff, then pytest)"
  if "$(python)" -m ruff --version >/dev/null 2>&1; then
    (cd "$ROOT" && "$(python)" -m ruff check brain services scripts setup demo) || fail=1
  else
    echo "  (ruff not installed: brain/.venv/bin/pip install -r brain/requirements-dev.txt)"
  fi
  (cd "$ROOT/brain" && "$(python)" -m pytest -q -p no:cacheprovider) || fail=1
fi
if [[ "$what" == all || "$what" == mod ]]; then
  echo "== mod (gradle build)"
  jh="$(java_home)"
  [[ -z "$jh" ]] && { echo "No JDK 25 found: install one (brew install openjdk@25) or set JAVA_HOME."; exit 1; }
  (cd "$ROOT/mod" && JAVA_HOME="$jh" ./gradlew build --no-daemon -q) || fail=1
fi
[[ $fail == 0 ]] && echo "All tests passed." || echo "Some tests failed (see above)."
exit $fail
