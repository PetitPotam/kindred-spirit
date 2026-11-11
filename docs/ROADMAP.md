# Kindred Spirit: roadmap

Each phase ends with something you can play with. Phases follow the [design](DESIGN.md).

## Phase 0: Spike, no Java (one or two evenings)
Prove the brain idea before writing a mod.
- Install MCPFabric (MIT) on Fabric 1.21.1 in a separate test setup; confirm its real tools (status, inventory, events, find blocks, give items, run commands).
- Brain v0 (Python): connect to MCPFabric, read a snapshot every few seconds, chat through the gateway (Gemini by default), reply in chat and with the Kokoro voice.
- Push-to-talk and the speech cleaner from the Verity setup.
- One proactive alert: low health or a creeper behind you.

**Done when:** you can talk to it by voice in-game, ask "what's around me?", and it warns you about danger unprompted.

## Phase 1: The companion appears
- Fabric mod skeleton (1.21.1). Decide whether to keep MCPFabric as a dependency.
- Draw the slime ball beside you, client-side only, with bounce and mood colors.
- Subtitles, a name tag on look, and a settings screen (Mod Menu).
- Local WebSocket between the mod and the brain, with a token.

**Done when:** a cute slime follows you, talks and reacts, and your world files are untouched.

## Phase 2: Helper core
- Give items (enchanted included), locate structures and biomes, find ores.
- Waypoints: it floats toward where you need to go. Highlight ores and mobs. Light aura.
- Push monsters away when you're overwhelmed.
- Long-term memory, named places, "remembers what it has seen".
- Power modes (Advisor, All-powerful) and action style (Grounded radius, Magic).

## Phase 3: Its mind
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
- Other skins and shapes (fairy, cube, wisp), custom skin PNGs.
- Servers: allowlist, server-safe behaviour, seed finder (cubiomes).
- Publish on GitHub and Modrinth as **Kindred Spirit** (slug `kindred-spirit` is free as of 2026-11-11).
