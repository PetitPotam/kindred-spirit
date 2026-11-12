# Kindred Spirit: roadmap

Each phase ends with something you can play with. Phases follow the [design](DESIGN.md).

**0.1 preview (November 2026)** covers most of Phase 0 and 1: the slime (bounce, moods, subtitles), the WebSocket bridge with a token, voice chat (Whisper + Kokoro), typed chat, danger warnings, adaptive quality, and the sandbox test harness. Not yet: name tag on look, the settings screen. The bridge question is settled: Kindred carries its own (see the design).

### Look and presence: where each pick stands

The rule for all of it: everything is a setting, so each player finds the companion they want.

| Pick | Status |
|---|---|
| Floating companion drawn only on your screen, cute, with personality (WANT) | **Done in 0.1**: no entity, nothing in the world; gaze, eye contact, petting, wandering, dozing, gestures |
| Shapes: slime ball, slime cube (WANT) | **Done**: `slime`, `slime_cube` (plus `wisp`, `strawberry`, `starry`) |
| Shape: fairy or pixie (WANT) | **Done**: `fairy` and `pixie` skins, two pairs of wings that flutter faster when it moves or is excited and fold when it dozes; any skin can have wings |
| Custom skins like player skins (WANT) | **Done**: a PNG in `config/kindredspirit/skins`, optional JSON, resource packs ([SKINS.md](SKINS.md)) |
| Mood colors and expressions (WANT) | **Done**: mood tints, happy eyes, blush, shy look-away, startle, mouth with the voice |
| Floating subtitles above it (MAYBE, configurable) | **Done**: `worldSubtitles` in kindredspirit.json (on by default); HUD captions as an option |
| Name tag only when you look at it (MAYBE, configurable) | **Planned** (Phase 1 leftovers): off by default |
| Radial command wheel (MAYBE, configurable) | **Planned** (Phase 3): stay, come, follow, look, gestures, skins on one key |
| Companion screen with a rotating 3D preview (WANT) | **Planned** (Phase 3): pick skin, size, name and personality while it turns in front of you |
| A real companion mob / autonomous helpers (MAYBE) | **Open question** in the design; never by default |
| Everything configurable | **Mostly**: every look and liveliness behavior is a setting (config file, `/kindred skin`, `/kindred life` with 13 switches). Still to come: an in-game settings screen (Phase 1 leftover) |

## Phase 0: Spike, no Java (one or two evenings)
Prove the brain idea before writing a mod.
- Install MCPFabric (MIT) on Fabric 1.21.1 in a separate test setup; confirm its real tools (status, inventory, events, find blocks, give items, run commands).
- Brain v0 (Python): connect to MCPFabric, read a snapshot every few seconds, chat through the gateway (Gemini by default), reply in chat and with the Kokoro voice.
- Push-to-talk and the speech cleaner.
- One proactive alert: low health or a creeper behind you.

**Done when:** you can talk to it by voice in-game, ask "what's around me?", and it warns you about danger unprompted.

## Phase 1: The companion appears
- Fabric mod skeleton (1.21.1). Decide whether to keep MCPFabric as a dependency.
- Draw the slime ball beside you, client-side only, with bounce and mood colors.
- Subtitles, a name tag on look, and a settings screen (Mod Menu).
- Leftovers after 0.1: the name tag on look and the settings screen. (A switch for each liveliness
  behavior shipped as `/kindred life`.)
- Local WebSocket between the mod and the brain, with a token.

**Done when:** a cute slime follows you, talks and reacts, and your world files are untouched.

## Phase 2: Helper core (mostly done)

Done: find ores, locate any structure or biome, Pip leads the way there, push monsters away,
place a torch, give items (magic), time and weather (all-powerful); power modes and action style;
long-term memory with learning (reflection), recall (embeddings + keywords), named places, "what
it has found", a diary, reminders; every outside service through the gateway (docs/GATEWAY.md).
Left: highlight ores and mobs, light aura, enchanted gifts.

- Give items (enchanted included), locate structures and biomes, find ores.
- Waypoints: it floats toward where you need to go. Highlight ores and mobs. Light aura.
- Push monsters away when you're overwhelmed.
- Long-term memory, named places, "remembers what it has seen".
- Power modes (Advisor, All-powerful) and action style (Grounded radius, Magic).

## Phase 3: Its mind (and how you see it), in progress

Done: her personality (whimsical, curious, her own little world), the bond meter with what raises
and lowers it, earning trust from a starting bond, discovering her powers (amnesia), standing
requests and offers, curiosity about advancements, items, biomes, mining and building, proposing
little goals when close, pranks, mischief when angry, vanishing when mistreated ([HEART.md](HEART.md)).
Left: memory fragments that unlock with milestones, favours before big help, profiles.

- A companion screen with a rotating 3D preview: skin, size, name, personality.
- A radial command wheel on one key (optional): stay, come, follow, look, gestures, skins.
- Personality presets, custom instructions, profiles.
- Bond meter, earning trust from zero.
- Grow-together mode with amnesia and memory fragments.
- Wants and favors: compromise, argue, explain.
- Every alert type with its own switch, the chattiness slider, quiet mode, welcome back, small talk.

### Next: a living creature, not a chatbot (see [ARCHITECTURE.md](ARCHITECTURE.md))

Done first: her character rewritten as an ancient spirit with a child's heart (tendencies and
examples instead of rules), System 2's self-portrait of who she's become lately, a bench to compare
her voice across prompts and models, and her conversation on Gemini 3 Flash.

- **Real senses** (done: sight from where she floats, hearing by the game's sound names, feeling
  rain, snow and temperature, watching what you do, new vs familiar). Before, she "knew" every animal
  in a 32-block bubble. Now: what's in her view
  and line of sight, with new or moving things standing out (and getting boring once familiar);
  sounds she hears, from the names the game gives them for subtitles ("Zombie groans" behind a
  wall); what she feels (rain, darkness, heat); a log of what you do (placed, mined, crafted, ate).
  The mod turns raw game data into "what she noticed"; the AI only sees that.
- **Building with you** (done: pillar, corners, wall, floor, outline; from your own blocks in grounded
  style, a few per second, never inside you or an animal, at most 256 blocks). Next: more shapes
  (stairs, an arch, a roof) and building from a little sketch she remembers.
- **Seeking.** Asked to find something beyond her senses, she reaches out with effort: a gesture, a
  moment, then an answer whose precision fades with distance. Within what the game has loaded,
  real animals and blocks; beyond it, where such things live (biomes, structures, located in
  singleplayer), narrowing to the real thing as you get closer. Her reach grows as she rediscovers
  her powers, and asking again and again tires her.
- **Her own urges.** System 2 proposes small impulses from what she noticed and who she's become
  (pick you a flower, boop a sheep, copy what you just did, dance to a music disc or note blocks,
  collect something shiny); her body carries them out, rarely and at the right moment, gated by
  your bond and her mood.
- **Humming and songs.** Tiny tunes she makes up (notes plus syllables), played with the game's own
  note-block sounds; one can get stuck in her head for a day and change a little.
- **Learning from your reactions** (like Black & White's creature): what you laugh at, answer or pet
  makes her do it a bit more; what you ignore or stop, a bit less. A small learner on your own play.
- **An expressive voice.** Kokoro can't do emotion. Audition Kokoro blends for an ageless sound now;
  then try an expressive model (Chatterbox, Qwen3-TTS, Orpheus) for her answers, keeping Kokoro for
  instant reactions.

## Phase 4: Expertise and understanding
- Recipes and items (minecraft-data), wiki knowledge search.
- Expert modes: survival, redstone, builder, speedrun.
- Activity understanding (building, redstone, farming, mining) and a session journal.
- Goals that survive restarts, routines, goal nudges.

## Phase 5: Grounded actions and jobs
- Grounded tasks within the radius: break the tree in front of you, collect, craft.
- Walk you somewhere; mine, collect and craft jobs.
- Return your items after death; trading help.
- Autonomous helpers (open question in the design).

## Phase 6: Voice and brain extras
- Wake word, several languages, swappable speech services through the gateway.
- Simple commands without AI, sending only the tools a request needs, the planner.
- Auto-pick a local model for your hardware. Code mode with saved skills.

## Phase 7: Agents and creators
- MCP server for outside agents, live dashboard.
- Creator mode: flag moments, automatic screenshots; maybe OBS clips and an episode recap.

## Phase 8: Sharing
- Installer and setup guide, including for your brothers.
- More skins and shapes (little star, cube robot) and skin packs. (Ball, cube, wisp, fairy and custom PNG skins shipped in 0.1.)
- Servers: allowlist, server-safe behaviour, seed finder (cubiomes).
- Publish on GitHub and Modrinth as **Kindred Spirit** (slug `kindred-spirit` is free as of 2026-11-11).
