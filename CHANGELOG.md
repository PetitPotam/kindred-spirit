# Changelog

Everything players or contributors will notice, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (see [docs/MAINTAINING.md](docs/MAINTAINING.md#versions)).

Add a line under **Unreleased** in the same pull request as the change. `scripts/release.sh` turns
Unreleased into the new version's section.

## [Unreleased]

### Added
- **Any shape, any size:** "a hollow sphere of glass, radius 4", "a star of gold 15 wide", "a stepped pyramid",
  "a heart standing up like a sign": circles, rings, ovals, triangles, stars, hearts, crosses, spirals, diamonds,
  polygons, spheres, domes, cylinders, cones, pyramids, a torus, arches, ramps, cubes; hollow or solid.
- **Flatten land:** "flatten everything within 10 blocks of me", or a size in front of you: hills and trees go,
  dips are filled with the ground that's there (grass on dirt, sand on sandstone), or with a block you name for a
  floor; never what someone built, never water. When a blueprint has no room, she offers to flatten a spot or to
  find open ground nearby.
- "What can you build?" is answered from what she really has; blueprint words are heard better ("chip rack" is a
  shipwreck); a task kept while she was busy is built where you looked when you asked.
- **Busy hands:** while she builds or works, a new task is kept and done right after ("Ship's first! I'll put
  the bell down the second I'm done"); "stop" or "do this first" switches. Her task and its progress show at
  the top right (`showTask` in kindredspirit.json).
- **Hush her:** "shh", "stop talking", "be quiet" (or "stop" / "enough" while she talks), or a quick tap on the
  talk key, stop her at once; the rest is dropped. Hushed twice, she keeps it short for a while.
- **Your bed:** "lead me to my spawn point / my bed" goes to where you come back to life.
- **"In the middle of what you just built":** "put a bell in the middle of the farm".
- A crop farm (tilled ground, water, crops planted), a working end portal, and "find a flat field" that
  leads you to the flattest open ground nearby.
- Builds from blueprints: Minecraft's own structures and CC0 circles, from your local blueprints folder.
- Friends on LAN: one shared Pip everyone sees and talks to, a visiting Pip, and host controls.
- Jobs, crafting help and trading help; a heart for each person she meets; places she remembers.
- Contributor guide for AI agents (`AGENTS.md`), issue forms, CI for the mod, the brain and the Windows
  update script, release automation, and a Contributor License Agreement.

### Fixed (from the 2026-11-13 playtest)
- Big blueprints: she asks once, then builds on your yes (or "the upright one"), instead of asking again and again
  or saying "coming up!" without building.
- Thanks and praise no longer make her redo the last build; a power that's not for the moment isn't "forgotten".
- "Give me back my stuff" fetches your real things, no copies; seeds in your hand aren't used as building
  blocks; room for a big build is looked for nearby and big enough; corrections during a lead aren't refused.

### Changed
- The licence is now the **GNU AGPL-3.0** (it was MIT), with a Minecraft linking permission; Pip's name,
  character and art have their own rules in `TRADEMARKS.md`.
- The Windows update script matches GitHub exactly (fetch and reset) instead of pulling.

## Before the changelog

The first preview: Pip talks with you by voice and chat, sees your game, warns you of danger, has a
heart and a memory, local voice and hearing, skins, a dashboard, and powers you discover together.
See the [README](README.md) for everything she does.
