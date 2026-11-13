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
- **Kindred Spirit Setup** for macOS, first part: an app (in a .dmg) that carries its own Python, her brain, the
  gateway and the dashboard, and opens a guided page in your browser. Each step explains itself, recommends a
  default, has a "Test it" button and a "Copy a help prompt" button for any AI assistant. The steps so far: your
  computer, installing her brain, waking her up. Choosing her AI, her models and Minecraft come next (#82).
- Releases are uploaded to CurseForge too, from the same GitHub release, once the project exists there (its page is
  in docs/curseforge.md).

### Changed
- Every change, release and website update reaches `main` through a pull request whose CI passed (no direct pushes,
  for anyone); a release is a "Release X" pull request, then its tag.
- One convention for branches, pull request titles and issue links (CONTRIBUTING.md), checked on every pull request.

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
