# Changelog

Everything players or contributors will notice, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (see [docs/MAINTAINING.md](docs/MAINTAINING.md#versions)).

Add a line under **Unreleased** in the same pull request as the change. `scripts/release.sh` turns
Unreleased into the new version's section.

## [Unreleased]

### Added
- Install checks on every system, on GitHub's clean machines and with no AI key: the Setup app on Apple silicon and
  Intel Macs, her brain and Minecraft's side on macOS and Linux, a friend's install on Windows
  (`.github/workflows/platforms.yml`, `scripts/test-install.sh`, docs/TESTING-PLATFORMS.md). Also runs locally, and
  in Docker for Linux.
- A real Minecraft client in those checks (Linux, and an experiment on macOS): it loads Fabric, Fabric API and the mod,
  says hi, and her brain answers (#105).
- **Kindred Spirit Setup** for macOS, first part: an app (in a .dmg) that carries its own Python, her brain, the
  gateway and the dashboard, and opens a guided page in your browser. Each step explains itself, recommends a
  default, has a "Test it" button and a "Copy a help prompt" button for any AI assistant. The steps so far: your
  computer, installing her brain, waking her up. Choosing her AI, her models and Minecraft come next (#82).
- **K** in the game opens her dashboard in your browser, on the computer where her brain runs (change the key in
  Controls → Kindred Spirit). On a friend's computer with only the mod, it says the dashboard is on the host's (#107).
- Releases are uploaded to CurseForge too, from the same GitHub release, once the project exists there (its page is
  in docs/curseforge.md).
- Her live dashboard is part of the Setup: once she's set up, opening Kindred Spirit Setup wakes her and opens her
  dashboard; an "Open her dashboard" button in the steps; and, if you choose it, she wakes when you log in (#111).
- The Setup chooses her AI: for her conversation (System 1), Gemini's free key by default with a guided way to get
  one, another service with your key, Ollama on your Mac, or Claude Code, Codex or Gemini CLI; for her slow thinking
  (System 2), the same, another one, or off. Each choice is tested with a real call; keys stay in secrets.env (#94).
- The Setup downloads her local models, sized for the computer, with progress, a SHA-256 check and resume: her
  instincts (bge-small), her voice (Kokoro, with a preview of each voice) and her hearing (Whisper, with a microphone
  test). The Setup app now carries its own whisper-server, so hearing needs no Homebrew (#95).
- The Setup installs Minecraft's side: a Kindred Spirit launcher profile for the newest Minecraft (or another one
  the mod supports) with Fabric Loader, Fabric API and the matching mod, or the mod into another launcher's mods
  folder; then "Say hi to her" checks the whole chain from the game to her answer (#96).
- Every release now carries Kindred Spirit Setup for macOS (Apple silicon and Intel), built and smoke-tested by CI
  from the release's own mod files, with a SHA-256 for each file and a note saying what was tested where (#98).
- **Minecraft 26.3**, the newest release, next to 1.21.1: one jar for each, built from the same code (with
  Stonecutter) and tested in CI for every version; releases upload each jar to Modrinth and CurseForge for its own
  Minecraft. Friends pick theirs with `update-pip-windows.ps1 -Minecraft <version>` (it keeps the one they have),
  and `install_profile.py --minecraft 26.3` adds a profile of its own. Recording demo videos works on 1.21.1 only
  for now (#41).
- The Setup updates everything together: it checks GitHub Releases, shows what's new, installs the new version of
  her brain, the matching mod and the Setup itself, keeps your settings and memories, and can go back (#97).

### Fixed
- `/kindred reset` now also forgets the places she noticed on her own (your bed, builds, where you died), so the
  new companion really starts fresh (#121).
- Stopping her (`scripts/stop.sh`, the Setup's Stop, an update's restart) waits until her helpers have really exited,
  and forces one that doesn't, so starting again never finds a port still taken (whisper-server is slow to let go).
- Friends building the mod on Windows need Java 25, not Java 21 (the build tool requires it): the guides say so, and
  Update Pip checks Java first and says what to install (#109).

### Changed
- Every change, release and website update reaches `main` through a pull request whose CI passed (no direct pushes,
  for anyone); a release is a "Release X" pull request, then its tag.
- One convention for branches, pull request titles and issue links (CONTRIBUTING.md), checked on every pull request.
- Building the mod needs a JDK 25 (it already did) and makes one jar per Minecraft version; the sandbox game is
  `./gradlew :26.3:runClient` (or `:1.21.1:runClient`), in `mod/versions/<version>/run/`. The 1.21.1 jar now asks for
  exactly 1.21.1, not any 1.21.x, which it never ran on. The mod tells her brain the real Minecraft version.

## [0.2.0-preview] - 2026-11-13

The first preview of Kindred Spirit. Pip is a little spirit who floats beside you in Minecraft 1.21.1 (Fabric),
talks with you by voice or chat, and helps you play. Her brain runs on the host's computer (macOS for now) with
your own AI key; friends on LAN need only the mod.

### What's in it
- **Talking:** hold V to speak, or type in chat. Short answers in her own voice, with local voice and hearing. Say
  "shh" and she stops.
- **Her senses:** what's in her line of sight, the sounds around you, your health and surroundings. She warns you
  about creepers, lava, big drops and low health.
- **Helping:** she finds ores, animals, structures and biomes and leads you there, pushes monsters away, chops and
  mines, crafts from your pockets, brings your things back after you die, and helps with villager trades.
- **Building:** shapes at any size (circles, stars, hearts, spheres, domes, towers, pyramids...), crop farms, nether
  and end portals, flattened land, and whole buildings from a catalogue of blueprints. Ask for something while
  she's busy and she'll do it next, with her progress on screen.
- **A heart:** a bond that grows with kindness, with moods, sulks, pranks and making up, powers she discovers with
  you, and a first meeting of her own.
- **Memory:** your name, what you like, your places (your bed, your builds, where you died), and a diary of your
  sessions.
- **Friends on LAN:** one shared Pip on the host's computer, seen and heard by everyone with the mod.
- **Skins and settings:** a slime, a cube, a fairy, a sprout, a wisp, a starry orb, or your own PNG; how much she
  may do, and how chatty she is.

### Good to know
- On multiplayer servers you don't host, she doesn't look through blocks for ores or anything else (no x-ray).
- Free software under the GNU AGPL-3.0.
