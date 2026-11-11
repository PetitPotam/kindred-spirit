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

## Phase 2: Helper core
- Give items (enchanted included), locate structures and biomes, find ores.
- Waypoints: it floats toward where you need to go. Highlight ores and mobs. Light aura.
- Push monsters away when you're overwhelmed.
- Long-term memory, named places, "remembers what it has seen".
- Power modes (Advisor, All-powerful) and action style (Grounded radius, Magic).

## Phase 3: Its mind (and how you see it)
- A companion screen with a rotating 3D preview: skin, size, name, personality.
- A radial command wheel on one key (optional): stay, come, follow, look, gestures, skins.
- Personality presets, custom instructions, profiles.
- Bond meter, earning trust from zero.
- Grow-together mode with amnesia and memory fragments.
- Wants and favors: compromise, argue, explain.
- Every alert type with its own switch, the chattiness slider, quiet mode, welcome back, small talk.

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
- Installer and setup guide, including for your friends.
- More skins and shapes (little star, cube robot) and skin packs. (Ball, cube, wisp, fairy and custom PNG skins shipped in 0.1.)
- Servers: allowlist, server-safe behaviour, seed finder (cubiomes).
- Publish on GitHub and Modrinth as **Kindred Spirit** (slug `kindred-spirit` is free as of 2026-11-11).
