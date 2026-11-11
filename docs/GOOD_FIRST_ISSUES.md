# Good first issues

Small, self-contained pieces taken from the [roadmap](ROADMAP.md). Each one says where to start.
Comment on (or open) the matching GitHub issue before starting, so two people don't build the same thing.

## Mod (Java)

1. **Settings screen with Mod Menu.** Edit `kindredspirit.json` in game: quality, subtitles,
   captions, size, position, volume. Start: `KindredConfig.java`; add Mod Menu as an optional dependency.
2. **Name tag when you look at it.** Show the companion's name above it only while your crosshair
   is on it. Start: `render/CompanionRenderer.java` (a ray-sphere test against the camera ray).
3. **Hide behind you at night / doze when you're AFK.** New idle animations from the design.
   Start: `Companion.update`.
4. **Glow in the dark.** Make the slime a gentle light source on screen when the area is dark
   (visual only). Start: the light value in `CompanionRenderer.render`.
5. **Don't float inside walls.** Nudge the target position out of solid blocks. Start: `Companion.update`.
6. **Other shapes:** a slime cube, a wisp, a little star. Start: `CompanionRenderer` (keep the
   mesh-built-once rule) and a `shape` setting.
7. **Custom skin PNG** from the config folder, like player skins. Start: `CompanionRenderer.WHITE`.

## Brain (Python)

8. **More danger alerts,** each with a switch and a test: drowning (air low), on fire, falling into
   the void, a skeleton aiming, many mobs at once. Start: `brain/kindred/alerts.py`.
9. **Simple commands without the AI:** "where am I", "status", "be quiet". Instant and free.
   Start: `Brain.answer` in `brain/kindred/server.py`.
10. **Quiet mode and a chattiness slider** (emergencies only ↔ keeps me company).
    Start: `small_talk_loop` and `[behaviour]` in `config.py`.
11. **Welcome back:** when you return after a long time, it remembers how long it's been.
    Start: `on_event("join")`, store the last session time in `~/.kindred-spirit/`.
12. **Let the AI phrase the warnings** (optional setting) while keeping the instant template as a fallback.

## Setup and docs

13. **Windows start script** (PowerShell): the same steps as `scripts/start.sh` and `setup.sh`.
14. **Linux check:** run the setup on a Linux distro, fix what breaks, document it.
15. **A guide for running fully local with Ollama:** which small model works well, how fast it is.
16. **Record the demo GIF** for the README (see the comment at the top of `README.md`).
