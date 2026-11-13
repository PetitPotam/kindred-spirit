# Changelog

Everything players or contributors will notice, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (see [docs/MAINTAINING.md](docs/MAINTAINING.md#versions)).

Add a line under **Unreleased** in the same pull request as the change. `scripts/release.sh` turns
Unreleased into the new version's section.

## [Unreleased]

### Added
- A crop farm (tilled ground, water, crops planted), a working end portal, and "find a flat field" that
  leads you to the flattest open ground nearby.
- Builds from blueprints: Minecraft's own structures and CC0 circles, from your local blueprints folder.
- Friends on LAN: one shared Pip everyone sees and talks to, a visiting Pip, and host controls.
- Jobs, crafting help and trading help; a heart for each person she meets; places she remembers.
- Contributor guide for AI agents (`AGENTS.md`), issue forms, CI for the mod, the brain and the Windows
  update script, release automation, and a Contributor License Agreement.

### Changed
- The licence is now the **GNU AGPL-3.0** (it was MIT), with a Minecraft linking permission; Pip's name,
  character and art have their own rules in `TRADEMARKS.md`.
- The Windows update script matches GitHub exactly (fetch and reset) instead of pulling.

## Before the changelog

The first preview: Pip talks with you by voice and chat, sees your game, warns you of danger, has a
heart and a memory, local voice and hearing, skins, a dashboard, and powers you discover together.
See the [README](README.md) for everything she does.
