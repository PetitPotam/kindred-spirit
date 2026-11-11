# Good first issues

Small, self-contained pieces taken from the [roadmap](ROADMAP.md). Each one says where to start.
Comment on (or open) the matching GitHub issue before starting, so two people don't build the same thing.

## Mod (Java)

1. **Settings screen with Mod Menu.** Edit `kindredspirit.json` in game: skin, quality, subtitles,
   captions, size, position, volume, and the liveliness switches (`LifeSwitches.java` already reads and
   writes them by name). Start: `KindredConfig.java`; add Mod Menu as an optional dependency.
2. **Name tag when you look at it.** Show the companion's name above it only while your crosshair
   is on it. Start: `render/CompanionRenderer.java` (a ray-sphere test against the camera ray).
3. **Hide behind you at night,** peeking out at noises. Start: `life/Behavior.java` (a new follow slot
   when it's dark and hostiles are near).
4. **Glow in the dark.** Make the slime a gentle light source on screen when the area is dark
   (visual only). Start: the light value in `CompanionRenderer.render`.
5. **Find a way around walls** instead of only floating over them (a short path search). Start:
   `avoidWalls` in `life/Behavior.java`.
6. **More shapes:** a little star, a cube robot, a bat-winged night skin. Start: `render/ShapeMesh.java`
   (shapes are built once from the same sphere, so textures wrap the same way) and `Skin.Shape`.
7. **More skins** (and a skin pack as a resource pack): see [SKINS.md](SKINS.md). Pure art, no code.
8. **A sparkle trail for wisps** as they float (client-side particles, a setting to turn it off).
9. **More gestures and phrases:** "wave", "hide behind me", "celebrate". Start: `life/Emote.java`
    and `brain/kindred/intents.py`.

## Brain (Python)

10. **More danger alerts,** each with a switch and a test: drowning (air low), on fire, falling into
   the void, a skeleton aiming, many mobs at once. Start: `brain/kindred/alerts.py`.
11. **More simple commands without the AI:** "where am I", "status", "be quiet". Instant and free, like "stay here" already is.
   Start: `brain/kindred/intents.py` and `Brain.answer` in `brain/kindred/server.py`.
12. **Quiet mode and a chattiness slider** (emergencies only ↔ keeps me company).
    Start: `small_talk_loop` and `[behaviour]` in `config.py`.
13. **Welcome back:** when you return after a long time, it remembers how long it's been.
    Start: `on_event("join")`, store the last session time in `~/.kindred-spirit/`.
14. **Let the AI phrase the warnings** (optional setting) while keeping the instant template as a fallback.

## Setup and docs

15. **Windows start script** (PowerShell): the same steps as `scripts/start.sh` and `setup.sh`.
16. **Linux check:** run the setup on a Linux distro, fix what breaks, document it.
17. **A guide for running fully local with Ollama:** which small model works well, how fast it is.
18. **Record the demo GIF** for the README (see the comment at the top of `README.md`).
