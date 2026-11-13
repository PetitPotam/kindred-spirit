# Changelog

Everything players or contributors will notice, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (see [docs/MAINTAINING.md](docs/MAINTAINING.md#versions)).

Add a line under **Unreleased** in the same pull request as the change. `scripts/release.sh` turns
Unreleased into the new version's section.

## [Unreleased]

The beta: Pip on the newest Minecraft, and a Mac app that sets her up for you. Her brain runs on the host's Mac;
friends on LAN need only the mod.

### New
- **Kindred Spirit Setup for macOS**, attached to every release for Apple silicon and Intel Macs: a downloaded app,
  no terminal. It carries its own Python and opens a guide in your browser where each step explains itself,
  recommends a choice, has **Test it**, and a **Copy a help prompt** button for any AI assistant (keys, e-mail
  addresses and your user name taken out). The steps: your computer, her brain, her AI, her instincts, voice and
  hearing, Minecraft, saying hi to her, her slow thinking, and waking her when you log in (#82, #93).
  - **Her AI:** Gemini with a free key by default (with a guided way to get one), another service with your key
    (OpenAI, Groq, Mistral, OpenRouter, Claude API), Ollama on your Mac, or Claude Code, Codex or Gemini CLI; for her
    slow thinking, the same, another one, or off. Each choice is tried with a real call; keys stay in
    `~/.kindred-spirit/secrets.env` (#94).
  - **Her models, sized for your Mac:** instincts (bge-small), voice (Kokoro, with **Hear it** for each voice) and
    hearing (Whisper, with a microphone test), downloaded with progress, a SHA-256 check and resume. The app brings
    its own whisper-server: no Homebrew needed (#95).
  - **Minecraft:** a Kindred Spirit launcher profile for 26.3 (recommended) or 1.21.1, with Fabric Loader, Fabric API
    and the matching mod in a game folder of its own, or the mod in another launcher's mods folder; then **Say hi to
    her** checks the whole chain, from the game to her answer (#96).
  - **Updates:** it checks GitHub Releases, shows what's new, and updates her brain, the mod and the Setup together,
    keeping your settings and memories; **Go back** returns to the version before (#97).
  - **Her dashboard is part of it:** once she's set up, opening the Setup wakes her and opens her dashboard; and, if
    you choose, she wakes when you log in (#111).
- **Minecraft 26.3**, the newest release, next to 1.21.1: one jar for each, built from the same code and tested for
  every version. The Setup, `install_profile.py --minecraft 26.3` and Update Pip (`-Minecraft <version>`) pick the
  right one (#41).
- **Press K** in the game to open her dashboard in your browser, on the computer where her brain runs (change the key
  in Controls → Kindred Spirit). On a friend's computer with only the mod, it says the dashboard is on the host's
  (#107).
- **Installed only the mod?** In your own world, one chat message now says that Pip needs her brain on this computer,
  with links to the Setup and to playing with a friend who hosts her, and **Don't show again**
  (`/kindred hint off`). Mod Menu's description and links say the same (#92). Its Setup link, and Mod Menu's homepage,
  open the website's Download page (#146).

### Fixed
- `/kindred reset` also forgets the places she noticed on her own (your bed, builds, where you died), so the new
  companion really starts fresh (#121).
- Stopping her (`scripts/stop.sh`, the Setup's Stop, an update's restart) waits until her helpers have really exited,
  so starting again never finds a port still taken.
- Friends building the mod on Windows need Java 25, not Java 21: the guides say so, and Update Pip checks Java first
  and says what to install (#109).
- The game tells her brain the mod's real version, not always 0.1.0 (#114).
- The 1.21.1 jar asks for exactly 1.21.1, not any 1.21.x, which it never ran on.

### Good to know
- Hosting her brain is macOS only for now: Windows (#40) and Linux (#81) are planned. Friends on Windows join a Mac
  host's world with the mod.
- The app isn't signed by Apple (that needs a paid membership): the first time, macOS warns you, and docs/SETUP.md
  shows how to open it anyway.
- Tested on GitHub's Apple silicon and Intel Macs with every release, with a stand-in AI. Nobody has tried yet: the
  first-run warning on a real download, a real Intel Mac, **Open Minecraft** with a real launcher and the
  microphone question, real AI keys through the Setup, and updating from one real release to the next. Reports are
  very welcome.
- On 26.3, her Minecraft knowledge base still assumes 1.21.1 (what came after it is treated as newer than your
  game) unless you set its version (docs/KNOWLEDGE.md).
- Recording demo videos works on 1.21.1 only for now.

### For contributors
- Install checks on every system, on GitHub's clean machines with no AI key: the Setup on Apple silicon and Intel
  Macs, her brain and Minecraft's side on macOS and Linux, a friend's install on Windows, and a real Minecraft client
  on Linux that says hi and hears her answer, for each Minecraft version (#104, #105). `scripts/test-install.sh` runs
  them locally, and in Docker for Linux (docs/TESTING-PLATFORMS.md).
- The mod builds with a JDK 25 into one jar per Minecraft version (Stonecutter); the sandbox game is
  `./gradlew :26.3:runClient` (or `:1.21.1:runClient`), in `mod/versions/<version>/run/`.
- Releases build and smoke-test the Setup for both Mac chips from the release's own jars and attach it with a SHA-256
  and a note saying what was tested where; they upload each jar to Modrinth and CurseForge for its own Minecraft
  once those projects are live (#98).
- CodeQL and OpenSSF Scorecard check the repository, and docs/MAINTAINING.md explains every check (#124).
- New issues get their area label automatically, and a bug report missing the computer and the logs gets a friendly
  request for them; GitHub Copilot follows the project's rules and review checklist (#126).
- Every change, release and website update reaches `main` through a pull request whose CI passed; a release is a
  "Release X" pull request, then its tag. One convention for branches, titles and issue links (CONTRIBUTING.md),
  checked on every pull request.
- The README and guides describe the Setup, 26.3, the K key and what hasn't been tried yet (#145).
- THIRD_PARTY_NOTICES.md names the AI the player chooses and the libraries inside the Setup's Python, and says
  which commits carry an AI co-author line; docs/SETUP.md lists the steps in the Setup's own order (#157).
- Filming tools for the demo video (#144): the setting `hudWithHiddenGui` (off) and the dev-script step
  `ownhud on|off` keep her own HUD with F1; a recording's start event has the computer's clock (`wall`), `fps` and
  `size`, and a friend's line to her on LAN is recorded with `from`; `-PplayerName=` names the dev player and
  `-PguestVideoSize=` sizes the guest's window; the dashboard reads another game's settings with `KINDRED_MOD_CONFIG`;
  session logs follow `KINDRED_HOME`.

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
