#!/bin/sh
# A release goes through a pull request, like every change (docs/MAINTAINING.md). Two steps:
#   scripts/release.sh 0.3.0        prepare it: a release/0.3.0 branch with the version (mod/gradle.properties) and
#                                   the changelog's Unreleased turned into 0.3.0, pushed, and its pull request opened.
#                                   Merge it (squash) once CI passes.
#   scripts/release.sh tag 0.3.0    after the merge: tag the merged "Release 0.3.0" commit on main and push the tag.
#                                   The tag makes the GitHub release and the Modrinth upload (.github/workflows/release.yml),
#                                   which refuses a tag that isn't on main.
# Versions: X.Y.Z, or X.Y.Z-something for a pre-release (0.3.0-beta.1).
set -eu
cd "$(dirname "$0")/.."
valid() { echo "$1" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$' || { echo "Not a version: $1 (X.Y.Z[-pre])"; exit 1; }; }

case "${1:-}" in -h|--help|"") sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0;; esac

java_home() { # a JDK 25 builds the mod: JAVA_HOME, else where macOS or Homebrew put it (as scripts/test.sh looks)
  [ -n "${JAVA_HOME:-}" ] && { echo "$JAVA_HOME"; return; }
  /usr/libexec/java_home -v 25 2>/dev/null && return
  for d in /opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home /usr/local/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home \
           /usr/lib/jvm/temurin-25-jdk-amd64 /usr/lib/jvm/java-25-openjdk-amd64; do
    [ -d "$d" ] && { echo "$d"; return; }
  done
}

if [ "${1:-}" = tag ]; then
  v="${2:-}"; valid "$v"
  git fetch -q origin main --tags
  git rev-parse -q --verify "refs/tags/v$v" >/dev/null && { echo "v$v already exists."; exit 1; }
  commit=$(git log origin/main --format=%H --grep="^Release $v\b" -1)
  [ -n "$commit" ] || { echo "No merged 'Release $v' commit on main yet: merge its pull request first."; exit 1; }
  [ "$(git show "$commit:mod/gradle.properties" | sed -n 's/^mod_version=//p')" = "$v" ] \
    || { echo "The 'Release $v' commit doesn't set mod_version=$v."; exit 1; }
  git tag -a "v$v" "$commit" -m "Kindred Spirit $v"
  git push -q origin "v$v"
  echo "Tagged v$v on $(git rev-parse --short "$commit") and pushed it: the release workflow takes it from here."
  exit 0
fi

v="${1:-}"; valid "$v"
[ "$(git branch --show-current)" = main ] || { echo "Start from main."; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "Commit or remove your changes first."; exit 1; }
git fetch -q origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || { echo "main isn't the same as GitHub's: pull first."; exit 1; }
awk '/^## \[Unreleased\]/{on=1;next} on&&/^## /{exit} on&&/[^[:space:]]/{n++} END{exit n?0:1}' CHANGELOG.md \
  || { echo "CHANGELOG.md has nothing under Unreleased."; exit 1; }

JAVA_HOME=$(java_home || true)
[ -n "$JAVA_HOME" ] || { echo "No JDK 25 found to build the mod: install one (brew install openjdk@25) or set JAVA_HOME."; exit 1; }
export JAVA_HOME
# the build and its tests first, on main as it is: if they fail, nothing has changed yet
(cd mod && ./gradlew build --no-daemon -q) || { echo "The build or its tests failed on main: nothing was changed."; exit 1; }

git switch -q -c "release/$v"
sed -i.bak "s/^mod_version=.*/mod_version=$v/" mod/gradle.properties && rm mod/gradle.properties.bak
sed -i.bak "s/^## \[Unreleased\]$/## [Unreleased]\\
\\
## [$v] - $(date +%Y-%m-%d)/" CHANGELOG.md && rm CHANGELOG.md.bak
git add mod/gradle.properties CHANGELOG.md
git commit -q -m "Release $v"
git push -q -u origin "release/$v"
notes=$(awk -v v="$v" '$0 ~ "^## \\[" v "\\]" {on=1; next} on && /^## / {exit} on' CHANGELOG.md)
gh pr create --title "Release $v" --body "The version and the changelog for $v. When CI passes, squash-merge it, then:

    scripts/release.sh tag $v

$notes" >/dev/null
echo "Release $v is a pull request now: $(gh pr view --json url -q .url). Merge it when CI passes, then: scripts/release.sh tag $v"
