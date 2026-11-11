# Contributing to Kindred Spirit

Thanks for wanting to help! Kindred Spirit is young, and small contributions shape it a lot.
You don't need to know Minecraft modding: half of the project is Python.

## Ground rules

- **Your world stays yours.** The mod must not register blocks, items, entities or world
  generation, and must not write to world saves. Anything that changes the world is a feature the
  player asked for, done the way a player or command would, and it can be switched off.
- **Light by default.** It runs beside a game, often on a laptop: nothing heavy on the render
  thread, no allocations per frame in hot paths, and new background work should be adjustable.
- **Cozy.** No horror, romance or creepy behaviour from the companion.
- **Be kind** in issues and reviews. We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

## Layout

```
mod/        Fabric mod (Java 21, Mojang names). Thin: sees, draws, plays sound.
  src/main/java/dev/kindredspirit/
    KindredSpiritClient.java   wiring: keys, events, commands, brain messages, HUD
    BrainLink.java             WebSocket to the brain (reconnects, never blocks the game)
    Snapshot.java              what the brain is told about the game
    Companion.java             position, mood, bounce, blink: the animation state
    render/CompanionRenderer   draws the slime (one precomputed sphere, no model files)
    audio/                     push-to-talk recording and voice playback
    util/                      plain Java with unit tests (WAV, quality, directions, mesh...)
    DevScript.java             scripted sandbox tests
  devscripts/                  test scripts for ./gradlew runClient
brain/      Python 3.11+ "brain"
  kindred/server.py            WebSocket server and the conversation flow
  kindred/mind.py              prompt, short memory, AI calls
  kindred/alerts.py            danger rules (add new alerts here)
  kindred/describe.py          snapshot -> text for the AI
  kindred/hardware.py          picks settings for this computer
  tests/                       pytest, no game or network needed
  tools/fake_game.py           pretend to be Minecraft against the real services
services/   local helpers: AI gateway, speech cleaner, Kokoro voice
scripts/    setup, start/stop, launcher profile installer
docs/       design, roadmap, good first issues
```

The protocol between mod and brain is documented at the top of `brain/kindred/server.py`.

## Getting set up

```bash
scripts/setup.sh                      # brain venv + local voice
cd mod && ./gradlew build             # needs a JDK 21+; Gradle comes with the wrapper
```

## Before you open a pull request

1. `cd mod && ./gradlew build` (compiles and runs the Java tests)
2. `brain/.venv/bin/python -m pytest brain/tests`
3. If you touched what you see or hear: try it in the sandbox,
   `cd mod && ./gradlew runClient -PdevScript=devscripts/smoke-test.txt`, and attach a screenshot.
4. Keep changes focused; explain *why* in the description.

CI runs steps 1 and 2 on every pull request.

## Common tasks

- **A new danger alert** (drowning, lava, falling...): add a rule in `brain/kindred/alerts.py`, a test
  in `brain/tests/test_alerts.py`, and if the mod doesn't send what you need yet, add it in
  `Snapshot.java`.
- **A new mood:** add it to `util/Mood.java` (color, bounce) and to `MOODS` in `brain/kindred/mind.py`.
- **Something new in the snapshot:** `Snapshot.java` (keep it cheap: it runs on the game thread),
  then describe it in `brain/kindred/describe.py` so the AI can use it.
- **Another AI provider:** usually nothing to code: add it to `upstreams` in
  `~/.kindred-spirit/gateway.json`. If it needs special handling, that goes in `services/kindred_gateway.py`.

## Reporting bugs

Include your OS and hardware, Minecraft and Fabric versions, `minecraft-kindred/logs/latest.log`
and `~/.kindred-spirit/logs/brain.log`. Remove any API keys before pasting.
