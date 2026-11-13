# Maintaining Kindred Spirit

How changes get in, how versions are made, and what to do when lots of people show up at once.
For contributors: [CONTRIBUTING.md](../CONTRIBUTING.md). For AI agents: [AGENTS.md](../AGENTS.md).

## How a change gets in

1. **An issue first** for anything bigger than a small fix, so nobody builds something that won't be
   merged. Issues are triaged on the project board (below).
2. **A branch and a pull request.** Contributors work on a fork; the maintainer on a branch
   (`fix/...`, `feature/...`). Nobody pushes to `main` directly (the ruleset enforces it once it's on;
   the maintainer can bypass it in an emergency).
3. **Checks that must pass before merging:**
   - **CI passed** (`.github/workflows/ci.yml`): the mod builds and its tests pass, the brain's tests
     pass on Python 3.11 and 3.12, and the Windows update script parses;
   - **CLA** (`.github/workflows/cla.yml`): every contributor has signed [CLA.md](../CLA.md);
   - **a review by the maintainer** (`.github/CODEOWNERS`);
   - conversations resolved, branch up to date with `main`.
4. **Squash and merge.** One pull request becomes one commit on `main`, titled with the pull request's
   title (what changes for the player). The branch is deleted after merging.
5. **The changelog** line goes in with the change, under "Unreleased" in [CHANGELOG.md](../CHANGELOG.md).

What a reviewer checks, besides the code: the world is never changed unless the player asked; nothing
heavy on the game thread; no API keys, personal data or real player names; Pip stays in character
(cozy, cheeky, kind: see [HEART.md](HEART.md) and [TRADEMARKS.md](../TRADEMARKS.md)); tests for new
behaviour; docs updated.

## Versions

[Semantic Versioning](https://semver.org/), with the Minecraft version as build metadata in the jar's name:
`kindred-spirit-0.2.0+1.21.1.jar`.

| Change | Version |
|---|---|
| A fix, nothing new to learn | patch: 0.2.0 → 0.2.1 |
| Something new (a power, a setting, a build) | minor: 0.2.1 → 0.3.0 |
| Something that breaks existing setups (config, protocol between mod and brain, memory format) | minor while we're in 0.x, major from 1.0 on; always marked **Breaking** in the changelog |
| A test version | pre-release: 0.3.0-beta.1 |

The mod and the brain are released together with one version: a jar only works with a brain of the same
release (the protocol between them is at the top of `brain/kindred/server.py`).

**A new Minecraft version** is its own minor release: update `minecraft_version`, `fabric_version` and
`loader_version` in `mod/gradle.properties`, fix what breaks, play it in the sandbox, and say so in the
changelog. Dependabot never does this automatically.

## Making a release

```bash
scripts/release.sh 0.2.0        # on an up-to-date main, nothing uncommitted
git push origin main v0.2.0
```

The script sets `mod_version`, turns "Unreleased" into the version's changelog section, builds, commits
"Release 0.2.0" and tags `v0.2.0`. Pushing the tag runs `.github/workflows/release.yml`: it builds the
jar again and makes the GitHub release with that changelog section. A version with a `-` (0.3.0-beta.1)
is marked as a pre-release.

After a release, friends who play with the host update with **Update Pip** (`scripts/update-pip-windows.cmd`).

**An urgent fix:** a `fix/...` branch from `main`, a pull request, merge, then a patch release.

## Labels and the project board

The board is the GitHub project **Kindred Spirit** (set up by `scripts/github-setup.sh`), with every
issue and pull request on it: *Triage → To do → In progress → In review → Done*.

| Label | Meaning |
|---|---|
| `needs-triage` | new; the maintainer hasn't looked yet (issue forms add it) |
| `bug`, `idea`, `content` | the kind of issue (`content`: a blueprint or skin to share) |
| `mod`, `brain`, `services`, `docs`, `ci` | which part (pull requests are labelled automatically) |
| `lan` | about playing with friends |
| `priority: high`, `priority: low` | after triage |
| `good first issue`, `help wanted` | a good place to start / help welcome |
| `needs-info` | waiting for the author: reminded after 21 days, closed 14 days later |
| `breaking` | breaks existing setups (see Versions) |
| `duplicate`, `wontfix`, `question` | the usual |
| `skip-changelog` | left out of the release notes |

**Triage**, ideally within a few days: reproduce or ask (`needs-info`), label, set a priority, close
duplicates with a link, and mark easy ones `good first issue` with a hint of where to start.

## If lots of people show up at once

The setup above is made for it: issue forms ask for versions and logs up front, blank issues are off,
`needs-info` issues close on their own, pull requests are labelled and checked automatically, and
nothing merges without CI, the CLA and a review. Beyond that:

- **Pin an issue** for the problem everyone hits ("Pip doesn't answer: check your AI key"), and close
  duplicates with a link to it.
- **Turn on Discussions** for questions and showing off, so issues stay for bugs and ideas.
- **Saved replies** in GitHub for the answers you write ten times.
- **First-time contributors' workflows need approval** (Settings → Actions → General): keep it on.
- **Big pull requests nobody discussed:** thank, and ask for an issue first. It's fine to say no.
- **Security reports** come privately ([SECURITY.md](../SECURITY.md)); fix them before talking about them.
- **Releases stay boring:** small, often, with a clear changelog. Never release on a Friday night.

## The repository's settings (what `scripts/github-setup.sh` does)

- Merging: squash only, the pull request title as the commit title, branches deleted after merge,
  "update branch" suggested.
- A ruleset on `main`: pull requests only, the **CI passed** and **CLA** checks, one approving review,
  conversations resolved, no force-pushes, no deletion; the maintainer can bypass it.
  (GitHub only enforces rulesets on a private repository with a paid plan; on the free plan they apply
  once the repository is public.)
- Dependabot alerts and security updates, private vulnerability reporting.
- The labels above, and the project board linked to the repository.
