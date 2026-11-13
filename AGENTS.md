# Instructions for AI coding agents

This file is for AI agents (Codex, Claude Code, Copilot, Cursor, Gemini CLI, Jules...) working in this
repository. `CLAUDE.md`, `GEMINI.md` and `.github/copilot-instructions.md` point here. Humans: see
[CONTRIBUTING.md](CONTRIBUTING.md).

Kindred Spirit is a Minecraft Java 1.21.1 Fabric mod (`mod/`, Java) with a companion called Pip, whose
"brain" (`brain/`, Python), gateway, voice and dashboard (`services/`) run on the computer of whoever
hosts her. How it fits together: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Which task are you here for?**
- Setting up someone's Windows PC so they can play with a friend's Pip: go to
  [Setting up a friend's Windows PC](#setting-up-a-friends-windows-pc). Change nothing else.
- Changing the code or the docs: read [the rules](#rules-for-every-change) first, then
  [working on the code](#working-on-the-code).

## Rules for every change

These are not optional. A pull request that breaks one of them is closed.

1. **Ask before you act outside the working copy.** Never push, open or merge pull requests, publish
   releases, create tags, change repository settings or post comments unless your human asked for that
   exact thing. Never push to `main`: work on a branch (`fix/...`, `feature/...`) and open a pull request.
2. **Never rewrite history** (`push --force`, `rebase` of pushed commits, `reset --hard` of someone's work,
   `filter-branch`) and never delete branches, tags or files you didn't create, unless your human asked.
3. **No secrets, no personal data.** No API keys, tokens, `.env` contents, real names, real player names,
   e-mail addresses or home-folder paths in code, tests, logs, docs, screenshots or commit messages. Use
   made-up names in tests and examples (the tests use "riverrobin" and "Robin" for a friend on LAN). Keys
   live in `~/.kindred-spirit/`, never in the repository.
4. **The player's world stays theirs.** The mod must not register blocks, items, entities or world
   generation, nor write to world saves. Anything that changes the world is something the player asked
   for, done the way a player or a command would, and it can be switched off.
5. **Light on the game.** Nothing heavy on the render or game thread; no allocations per frame in hot
   paths; network and AI calls never block the game.
6. **Pip stays in character:** cozy, cheeky, kind, for players of all ages. No sexual content, cruelty
   or horror ([TRADEMARKS.md](TRADEMARKS.md), [docs/HEART.md](docs/HEART.md)).
7. **Tests with every behaviour change.** Java tests in `mod/src/test`, Python tests in `brain/tests`.
   Both suites must pass before you say you're done. If you couldn't run something, say so.
8. **Keep the licence intact.** The code is AGPL-3.0 (copyright PetitPotam). Don't add code copied from
   elsewhere unless its licence is compatible and you name the source and licence in the pull request
   and in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Don't add dependencies without saying why.
   Contributions need the [CLA](CLA.md), signed by the human who submits them.
9. **Say you're an AI.** The pull request says which AI tools made the change (the template asks).
10. **One change per pull request**, small and focused, with a title that says what changes for the
    player, a line under "Unreleased" in [CHANGELOG.md](CHANGELOG.md), and docs updated where players or
    contributors will notice. The full process: [docs/MAINTAINING.md](docs/MAINTAINING.md).
11. **Commit messages** explain *why*, not just what: a short title line, then the reason and what was
    checked.
12. **Work is tracked in issues** and on the project board "Kindred Spirit" (milestones: Singleplayer polish,
    LAN with friends, First public release, Later: online servers). Before starting, look for the issue;
    a bug, idea or feature you notice along the way gets an issue (with your human's OK) with labels and a
    milestone, not a TODO in the code. Pull requests say `Fixes #<number>` so the issue closes when merged.

## Working on the code

- **All tests at once:** `scripts/test.sh` (or `scripts/test.sh brain` / `mod`), from any folder or worktree.
- **Mod:** `cd mod && ./gradlew build` (builds and runs the Java tests; needs a JDK 25 to run Gradle, the
  mod targets Java 21).
- **Brain:** `scripts/setup.sh` once, then `cd brain && .venv/bin/python -m pytest -q`.
- **Sandbox checks:** a dev client driven by a script, `cd mod && ./gradlew runClient
  -PdevScript=devscripts/<script>.txt` (the scripts in `mod/devscripts/` show the steps available).
- **Layout and common tasks** (a new alert, gesture, skin, action, provider): [CONTRIBUTING.md](CONTRIBUTING.md).
- **The protocol** between the mod and the brain is at the top of `brain/kindred/server.py`. Changing it
  is a breaking change: both sides in the same pull request, marked **Breaking** in the changelog.
- **Evals** for her answers: `brain/evals/` and `scripts/eval.sh`.

## Setting up a friend's Windows PC

To play with the host's Pip, the friend needs **no brain, no Python, no AI keys**: only Minecraft 1.21.1
with Fabric, Fabric API, and the Kindred mod jar built from this repository. The full guide for the
person is [docs/PLAY-WITH-FRIENDS.md](docs/PLAY-WITH-FRIENDS.md); the steps for you:

1. **Java 21 JDK** (to build the mod). Check `java -version`; if missing or older than 21, install
   Eclipse Temurin 21 (e.g. `winget install EclipseAdoptium.Temurin.21.JDK`), then open a new terminal.
2. **Build the mod** from the repository root, in PowerShell:
   ```powershell
   git pull
   cd mod
   .\gradlew.bat build
   ```
   The jar is `mod\build\libs\kindred-spirit-<version>+1.21.1.jar` (not the `-sources` one). The first
   build downloads Gradle and Minecraft's files: a few minutes. Tests run as part of the build.
3. **Minecraft 1.21.1 with Fabric** (the person clicks through these; guide them):
   - Minecraft Launcher → Installations → New installation → version **release 1.21.1** → start once.
   - Fabric installer for Windows from https://fabricmc.net/use/installer/ → Client, Minecraft 1.21.1,
     newest loader, "Create profile" ticked → Install.
4. **Mods folder** `%APPDATA%\.minecraft\mods` (create it if needed), containing exactly:
   - Fabric API for 1.21.1 (`fabric-api-0.116.x+1.21.1.jar`, from
     https://modrinth.com/mod/fabric-api/versions?g=1.21.1);
   - the Kindred jar from step 2 (replace any older Kindred jar).
5. They start the **fabric-loader-1.21.1** installation and join the host's LAN world from Multiplayer.

**Steps 2 and 4 in one command** (after Git, Java 21 and Fabric are set up), and the way to update
whenever the host pushes changes (Minecraft closed):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\update-pip-windows.ps1
```

It gets the latest version from GitHub, builds the mod (tests skipped), replaces the Kindred jar in
`%APPDATA%\.minecraft\mods`, and downloads Fabric API for 1.21.1 from Modrinth if it's missing.
`scripts\update-pip-windows.cmd` does the same on a double-click; a desktop shortcut to it is handy. Keep
their Kindred jar the same version as the host's: update after every push. In game they talk to Pip in
chat: "Pip, ...".

If `git pull` refuses because the history on GitHub was rewritten, the friend's copy is only for playing:
`git fetch origin` then `git reset --hard origin/main` puts it right (the update script does this already).

Don't set up `brain/` or `services/` on the friend's PC unless they explicitly want their own Pip (the
brain's scripts are written for macOS). Never commit or push from the friend's machine unless asked.
