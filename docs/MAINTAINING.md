# Maintaining Kindred Spirit

How changes get in, how versions are made, and what to do when lots of people show up at once.
For contributors: [CONTRIBUTING.md](../CONTRIBUTING.md). For AI agents: [AGENTS.md](../AGENTS.md).

## How a change gets in

1. **An issue first** for anything bigger than a small fix, so nobody builds something that won't be
   merged. Issues are triaged on the project board (below).
2. **A branch and a pull request, for everyone.** Contributors work on a fork; the maintainer and AI agents on a
   branch (`fix/...`, `feature/...`, `docs/...`, `release/...`). **Nobody pushes to `main` directly**, the maintainer
   included: no change to the mod, the brain, the website or the version reaches `main` (and so no release and no
   website deploy happens) without a pull request whose CI passed. Enforced by `.githooks/pre-push` on the
   maintainer's computer now (`git config core.hooksPath .githooks`, done by `scripts/setup.sh`), and by GitHub's
   ruleset once the repository is public (no bypass).
3. **Checks that must pass before merging:**
   - **CI passed** (`.github/workflows/ci.yml`): the mod builds and its tests pass, the brain's tests
     pass on Python 3.11 and 3.12, the Windows update script parses, and the pull request follows the
     conventions in CONTRIBUTING.md (a title over 72 characters fails; a branch name off the pattern or no
     linked issue only warns);
   - **CLA** (`.github/workflows/cla.yml`): every contributor has signed [CLA.md](../CLA.md);
   - a review is **not** required: the maintainer (and agents working for the maintainer) merge their own pull
     requests once CI passes; contributors' pull requests are reviewed by the maintainer before merging
     (`.github/CODEOWNERS` asks for it);
   - the branch up to date with `main`.
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

A release is a pull request too, in two steps:

```bash
scripts/release.sh 0.3.0        # on an up-to-date main: opens the "Release 0.3.0" pull request
scripts/release.sh tag 0.3.0    # after that pull request is merged: tags it on main and pushes the tag
```

The first step makes a `release/0.3.0` branch that sets `mod_version` and turns "Unreleased" into the version's
changelog section, builds it, pushes it and opens its pull request. Merge it once CI passes. The second tags the
merged commit on `main`; the tag runs `.github/workflows/release.yml`, which refuses a tag that isn't on `main`,
builds the jar again, makes the GitHub release with that changelog section, and uploads it to Modrinth and CurseForge. A version with a `-` (0.3.0-beta.1)
is marked as a pre-release.

The same run builds **Kindred Spirit Setup** on GitHub's Apple silicon and Intel Macs from the release's own mod
files. It installs and starts each one in a throwaway home (`setup/smoke_test.py`), attaches the `.dmg` files with
their `.sha256` to the release, and adds a short "Kindred Spirit Setup" section to its notes saying what was tested
where. docs/SETUP.md is the player's guide; setup/README.md says how it's built.

**Modrinth.** The same tag also publishes the version on Modrinth, once the project exists there: create it on
modrinth.com (it starts as a **draft**, visible only to you and members you add; after Modrinth's review you can
keep it **private** or **unlisted**, or list it), then add its ID as the Actions variable `MODRINTH_PROJECT_ID` and
a personal access token (with permission to create versions) as the Actions secret `MODRINTH_TOKEN`. Without them
the step is skipped. The page should say that the mod needs Pip's brain running on the host's computer.
**Modrinth's content rules** (modrinth.com/legal/rules) matter here: the project must carry the "Contains
AI-generated content" disclosure (set on modrinth.com, in the project's settings); no icon or image derived from AI
output (Pip's icon is drawn by a program written with Claude: the owner chose to keep it, and the page says how it
was made, so moderators can judge); a page that says plainly what data goes where; and a
project whose contents are primarily AI output may not be published publicly, which Modrinth's moderators judge
from an honest description (docs/modrinth.md says who did what). Never describe the AI's part as smaller than it is.
`scripts/modrinth.sh` creates the draft and keeps its page in step with [docs/modrinth.md](modrinth.md)
(`create`, `update-page`, `show`), with a token kept in the macOS Keychain (service `kindred-modrinth`): one that
can only create, read and write projects and versions, never move money or delete anything.

**CurseForge.** The same tag uploads the same jar, with the same notes, to CurseForge once the project exists there:
the GitHub release stays the one source of truth. The owner creates the project at authors.curseforge.com (Minecraft,
Mods) with the fields and text in [docs/curseforge.md](curseforge.md); then the Actions variable
`CURSEFORGE_PROJECT_ID` (the project's numeric ID, shown on its page) and the Actions secret `CURSEFORGE_TOKEN` (an
API token from the CurseForge account settings, set with `gh secret set CURSEFORGE_TOKEN`, which hides what you type)
turn the upload on. Without the variable the step is skipped. Each file is tagged Minecraft 1.21.1, Fabric, Client and
Java 21, with Fabric API as a required dependency (the CurseForge app installs it too). Things to know:
- **Moderation:** a new project goes to CurseForge's moderators with its first file, and every file is reviewed
  ("Under review") before players see it. If they ask for changes or reject it, answer or appeal in the project's
  messages: never delete it and upload it again. Changing what the project is (its visibility, deleting it) is done on
  the website by the owner.
- **Their rules** (the moderation policies, checked 2026-11-13): no rule against AI-written code or a mod with AI
  features; an AI-generated or AI-edited showcase image needs a visible disclaimer (Pip's pictures are taken in the
  game, so none is needed); "external download links for files are not allowed", so the page points to the setup
  guide for the brain but never offers files from elsewhere; English first; a one-sentence summary; a 400 x 400
  logo; links to other sites at the bottom of the description; every file with a changelog. Keep the page as honest
  about AI as Modrinth's: never describe the AI's part as smaller than it is.
- **The CurseForge app** shows a project only once it has at least one "Release" file: preview, alpha and beta versions
  are on the website but not in the app.

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
| `versions` | another Minecraft version or mod loader (see "A new Minecraft version" above) |
| `priority: high`, `priority: low` | after triage |
| `good first issue`, `help wanted` | a good place to start / help welcome |
| `needs-info` | waiting for the author: reminded after 21 days, closed 14 days later |
| `breaking` | breaks existing setups (see Versions) |
| `duplicate`, `wontfix`, `question` | the usual |
| `skip-changelog` | left out of the release notes |

**The board stays alive:** every bug, idea or feature that comes up (a playtest, a review, a
conversation) becomes an issue with labels and a milestone, and lands on the board; pull requests say
`Fixes #<number>`, so issues close themselves when merged. The milestones are the roadmap, in order:
*Singleplayer polish*, *LAN with friends*, *First public release*, *Later: online servers*.

**Internal notes stay private.** Issues here become public with the repository. What only the maintainer
should see (legal questions, account and security settings, launch checklists, anything about the maintainer)
goes to the private repository **PetitPotam/kindred-spirit-internal**, which shares the same (private) board.

**Triage**, ideally within a few days: reproduce or ask (`needs-info`), label, set a priority, close
duplicates with a link, and mark easy ones `good first issue` with a hint of where to start.

## If lots of people show up at once

The setup above is made for it: issue forms ask for versions and logs up front, blank issues are off,
`needs-info` issues close on their own, pull requests are labelled and checked automatically, and
nothing merges without CI, the CLA and a review. Beyond that:

- **Pin an issue** for the problem everyone hits ("Pip doesn't answer: check your AI key"), and close
  duplicates with a link to it.
- **Discussions** are on (Q&A, Ideas, Show and tell...): point questions there, so issues stay for bugs and
  planned work; a good idea from a discussion becomes an issue.
- **Saved replies** in GitHub for the answers you write ten times.
- **First-time contributors' workflows need approval** (Settings → Actions → General): keep it on.
- **Big pull requests nobody discussed:** thank, and ask for an issue first. It's fine to say no.
- **Security reports** come privately ([SECURITY.md](../SECURITY.md)); fix them before talking about them.
- **Releases stay boring:** small, often, with a clear changelog. Never release on a Friday night.

## The repository's settings (what `scripts/github-setup.sh` does)

- Merging: squash only, the pull request title as the commit title, branches deleted after merge,
  "update branch" suggested.
- A ruleset on `main`: pull requests only (squash), the **CI passed** check up to date with `main`, no approval
  required, no force-pushes, no deletion, and no bypass for anyone.
  (GitHub only enforces rulesets on a private repository with a paid plan; on the free plan they apply
  once the repository is public.)
- Dependabot alerts and security updates, private vulnerability reporting.
- The labels above, and the project board linked to the repository.
