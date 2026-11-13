# Copilot instructions

The instructions for every AI agent in this repository are in [AGENTS.md](../AGENTS.md) at the root; read and follow them, especially "Rules for every change", before suggesting or making changes.

## When you review a pull request

Check it against these rules, from AGENTS.md, and say which ones it breaks (with the line), not just style:

1. **One change per pull request**, on a branch `type/issue-short-name`, a title that says what changes for the player (no `feat:` prefixes, at most 72 characters), `Fixes #<number>` in the description.
2. **Tests with every behaviour change:** Java tests in `mod/src/test`, Python tests in `brain/tests`.
3. **A line under "Unreleased" in CHANGELOG.md**, and the docs updated where players or contributors will notice.
4. **No secrets or personal data:** no API keys, tokens, `.env` contents, real names, player names, e-mail addresses or home-folder paths in code, tests, logs, docs or screenshots. Tests use made-up names ("Robin", "riverrobin").
5. **The player's world stays theirs:** the mod registers no blocks, items, entities or world generation and writes nothing to world saves; anything that changes the world is something the player asked for, and can be switched off.
6. **Light on the game:** nothing heavy on the render or game thread, no allocations per frame in hot paths, network and AI calls never block the game.
7. **Pip stays in character:** cozy, cheeky, kind, for players of all ages; no sexual content, cruelty or horror (docs/HEART.md, TRADEMARKS.md).
8. **The protocol** between the mod and the brain (top of `brain/kindred/server.py`) changes on both sides in the same pull request, marked **Breaking** in the changelog.
9. **Licences:** no code copied from elsewhere unless its licence is compatible and named in THIRD_PARTY_NOTICES.md; new dependencies say why.
10. **The pull request says which AI tools made the change.**

Be kind and specific: contributors range from first-timers to experienced modders.

## When you answer questions about the code

Start from [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md). The mod (Java, `mod/`) draws Pip and acts in the game; her brain (Python, `brain/`) decides what she says and does; `services/` holds the gateway, voice and dashboard; `setup/` is the Setup app. Minecraft versions are built with Stonecutter (`mod/versions/`).
