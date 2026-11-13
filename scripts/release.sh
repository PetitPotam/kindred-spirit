#!/bin/sh
# Make a release: scripts/release.sh 0.2.0 (or 0.2.0-beta.1).
# Sets the version in mod/gradle.properties, turns "Unreleased" in CHANGELOG.md into this version's
# section, commits, and tags v<version>. Pushing the tag makes the GitHub release (.github/workflows/release.yml).
# Run it on an up-to-date main with nothing uncommitted. See docs/MAINTAINING.md.
set -eu
cd "$(dirname "$0")/.."
v="${1:-}"
echo "$v" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$' || { echo "usage: scripts/release.sh X.Y.Z[-pre.N]"; exit 1; }
[ "$(git branch --show-current)" = main ] || { echo "Releases are made from main."; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "Commit or remove your changes first."; exit 1; }
git fetch -q origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || { echo "main isn't the same as GitHub's: pull or push first."; exit 1; }
git rev-parse -q --verify "refs/tags/v$v" >/dev/null && { echo "v$v already exists."; exit 1; }
awk '/^## \[Unreleased\]/{on=1;next} on&&/^## /{exit} on&&/[^[:space:]]/{n++} END{exit n?0:1}' CHANGELOG.md \
  || { echo "CHANGELOG.md has nothing under Unreleased."; exit 1; }

today=$(date +%Y-%m-%d)
sed -i.bak "s/^mod_version=.*/mod_version=$v/" mod/gradle.properties && rm mod/gradle.properties.bak
sed -i.bak "s/^## \[Unreleased\]$/## [Unreleased]\\
\\
## [$v] - $today/" CHANGELOG.md && rm CHANGELOG.md.bak

(cd mod && ./gradlew build --no-daemon -q)
git add mod/gradle.properties CHANGELOG.md
git commit -q -m "Release $v"
git tag -a "v$v" -m "Kindred Spirit $v"
echo "Ready: commit 'Release $v' and tag v$v. Publish with:"
echo "  git push origin main v$v"
