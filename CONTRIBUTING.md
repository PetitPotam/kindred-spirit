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
mod/        Fabric mod (Java 21 target, built with JDK 25, Mojang names). Thin: sees, draws, plays sound.
  src/main/java/dev/kindredspirit/
    KindredSpiritClient.java   wiring: keys, events, commands, brain messages, HUD
    BrainLink.java             WebSocket to the brain (reconnects, never blocks the game)
    Snapshot.java              what the brain is told about the game
    Companion.java             feeds the game into its life; mood color, subtitle, mouth, skin
    life/Behavior.java         its "life": where it floats, what it looks at, eye contact, petting,
                               wandering, dozing (pure Java, unit-tested without the game)
    life/Emote.java            gestures: nod, spin, hop, shy... as eased curves over time
    skin/                      skins: JSON + PNG from the mod, resource packs, or config/kindredspirit/skins
    act/                       what it may do (Abilities: power and style) and doing it (Actions)
    render/                    draws the companion from its skin and life (shapes built once, no model files)
    audio/                     push-to-talk recording and voice playback
    util/                      plain Java with unit tests (WAV, quality, directions, mesh...)
    DevScript.java             scripted sandbox tests
  devscripts/                  test scripts for ./gradlew runClient
brain/      Python 3.11+ "brain"
  kindred/server.py            WebSocket server and the conversation flow
  kindred/mind.py              prompt, the tool loop, reflection (learning)
  kindred/memory.py            what to keep, recall for each message, reminders
  kindred/tools.py             the tools the AI may use (filtered by power and style)
  kindred/alerts.py            danger rules (add new alerts here)
  kindred/describe.py          snapshot -> text for the AI
  kindred/hardware.py          picks settings for this computer
  tests/                       pytest, no game or network needed
  tools/fake_game.py           pretend to be Minecraft against the real services
services/   the gateway (AI, speech-to-text, voice, embeddings, memory store) and local tools
            (Kokoro voice, local embeddings, memory_store.py)
scripts/    setup, start/stop, launcher profile installer
docs/       design, roadmap, good first issues
```

The protocol between mod and brain is documented at the top of `brain/kindred/server.py`.

## Getting set up

```bash
scripts/setup.sh                      # brain venv + local voice
cd mod && ./gradlew build             # needs JDK 25 to build (the mod targets Java 21); Gradle comes with the wrapper
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
- **A new gesture:** add it to `life/Emote.java` (a curve that starts and ends at rest; the test
  `gesturesStartAndEndSoftly` checks it), to `GESTURES` in `brain/kindred/mind.py` so the AI can use it,
  and a phrase for it in `brain/kindred/intents.py`.
- **A new skin:** see [docs/SKINS.md](docs/SKINS.md); built-in ones live in
  `mod/src/main/resources/assets/kindredspirit/skins/`.
- **Something it can be asked to do** ("go to sleep", "hide"): a rule in `brain/kindred/intents.py`.
- **A new mood:** add it to `util/Mood.java` (color, bounce) and to `MOODS` in `brain/kindred/mind.py`.
- **Something new in the snapshot:** `Snapshot.java` (keep it cheap: it runs on the game thread),
  then describe it in `brain/kindred/describe.py` so the AI can use it.
- **Another provider** (AI, speech-to-text, voice, embeddings): usually nothing to code, see
  [docs/GATEWAY.md](docs/GATEWAY.md). Special handling goes in `services/kindred_gateway.py`.
- **A new action:** an `Ability` in `act/Abilities.java` (with its power/style rule and a test), the
  doing in `act/Actions.java`, and its tool description in `brain/kindred/tools.py`. If players ask for
  it in a recognizable way, add a phrase to `ACTION_HINTS` in `intents.py` so the AI must really do it.

## Reporting bugs

Include your OS and hardware, Minecraft and Fabric versions, `minecraft-kindred/logs/latest.log`
and `~/.kindred-spirit/logs/brain.log`. Remove any API keys before pasting.
