# Kindred Spirit: design

A cute, configurable AI companion for Minecraft Java. It talks with you by voice or chat, understands what you're doing in your world, knows the game like an expert, keeps you company, and helps as much or as little as you choose.

Status: design, November 2026. Nothing is built yet. Feature choices come from the [feature picker](https://claude.ai/artifact/9M8nx31vv6f871iDDeHkUG).

---

## 1. Principles

1. **Configurable first.** Everything that changes how it feels has a setting, and ready-made **profiles** set many at once. Everyone should find their own companion.
2. **Your world stays yours.** No new blocks, items, mob types, world generation, or tick changes. The companion is drawn only on your screen. Anything that changes the world is something you asked for, done the way a player or a command would, and switchable.
3. **Bring your own AI.** The mod talks to **one gateway address**. Behind it, each person uses any model, agent or speech service they like. We ship a default gateway and a setup guide.
4. **Thin mod, smart brain.** The Java mod only sees, draws and acts. Personality, memory, knowledge and decisions live in the **brain**, a separate program in Python, so it's easy to change and to contribute to.
5. **Fun before power.** Help should make the game more enjoyable, not finish it for you, unless you choose that.
6. **Open source.** Proposed license: MIT, compatible with the MIT projects we learn from.

## 2. Architecture

```
┌──────────── Minecraft (Fabric 1.21.1) ────────────┐
│ Kindred Spirit mod                                 │
│  • draws the companion, subtitles, arrow, glow     │
│  • reads game state (telemetry) and events         │
│  • performs actions (give, break, light, locate…)  │
│  • settings screen, push-to-talk key               │
└──────────────┬─────────────────────────────────────┘
               │ local WebSocket (127.0.0.1 + token)
┌──────────────▼─────────────────────────────────────┐
│ Kindred brain (Python, runs beside the game)       │
│  • event engine: decides when to speak or act      │
│  • activity understanding: "you're building a farm"│
│  • mind: mood, bond, wants, memories, journal      │
│  • knowledge: recipes, wiki search, expert modes   │
│  • voice: mic → speech-to-text, text → speech      │
│  • MCP server for outside AI agents                │
└──────────────┬─────────────────────────────────────┘
               │ OpenAI-compatible HTTP
┌──────────────▼─────────────────────────────────────┐
│ Gateway (yours to choose)                          │
│  default: Kindred gateway (from the Verity setup)  │
│  → Gemini, Ollama, Claude, Groq, OpenRouter, agents │
└────────────────────────────────────────────────────┘
```

**Starting point:** [MCPFabric](https://github.com/denfry/mcpfabric) (MIT) already exposes game state and 70+ actions over a local bridge for 1.21.1. Phase 0 prototypes the brain on top of it with no Java at all. Phase 1 decides whether Kindred keeps MCPFabric as a dependency or carries its own bridge (borrowing MIT code with credit).

**Voice** reuses the pieces proven in the Verity setup: push-to-talk, local Whisper, the speech cleaner (no illegal-character kicks, no words invented from silence), and local Kokoro voice. Speech services also go through the gateway, so users can swap them.

## 3. The companion

### Look
- **Shapes:** slime ball, slime cube, fairy or pixie, wisp, little star, cube robot.
- **Custom skins:** a PNG in a folder, like player skins.
- **Personality you can see:** it squishes when it lands, bounces at diamonds, droops when ignored, hides behind you at night, dozes when you're AFK, and changes color with its mood.
- **Optional (each a setting):** subtitles above it, a name tag only when you look at it, a radial command wheel, a companion screen with a rotating 3D preview.
- **It can be the light:** in dark places it glows around you like a light spell.
- **It can be the guide:** it floats ahead in the direction you need to go.

### Names
Each player names their own companion. The project is Kindred Spirit.

## 4. Power and how it acts

Two independent settings decide what it may do.

### Power mode (how much)
| Mode | What it means |
|---|---|
| **Advisor** | Talks, explains, finds things. Never changes the world. |
| **Grow together** | Starts small and gains powers with your bond and adventures. Can start with **amnesia** (see 6). |
| **All-powerful** | Everything allowed from the start. |

### Action style (how)
| Style | What it means | Example: "I need wood" |
|---|---|---|
| **Grounded** | It can only use what really exists within a set **radius** around you. It still *knows* the whole world. | It breaks the tree in front of you and the logs drop |
| **Magic** | It can make things appear. | Logs appear in your hands |

Every ability has three properties:
- a **tier** (advice, act, magic),
- whether it needs real materials **nearby** in grounded style,
- an **unlock** condition in grow-together mode (bond level or a recovered memory).

Abilities: give items (enchanted included), waypoints and a guiding arrow, highlight ores or mobs, light, push monsters away (it notices when you're overwhelmed and reacts), time, weather, teleport, return your items after death (on request or offered), trading help, walk you somewhere, and mine, collect and craft jobs. Build-from-plan and combat reflexes are maybes.

### Autonomous helpers (open question)
You'd like it to automate tasks you taught it, for example running a mob farm. Options:
1. **It does the job itself** in grounded style, interacting with real blocks. No new mobs. *Recommended first.*
2. **It summons vanilla helpers** (for example an allay or an iron golem) that do the task. No new mob *types* are registered, so the world stays vanilla-compatible, but it does add entities. Off by default.

## 5. Understanding you

Telemetry alone isn't enough. It should understand **what you're doing**:
- **Snapshot:** health, hunger, armor, effects, inventory and hotbar, position, biome, time, weather, what you're looking at, nearby mobs and dangers with direction, nearby ores.
- **Activity understanding:** from your hotbar, the blocks you place and break, and where you are, it recognizes activities. Redstone in hand while placing repeaters means redstone; walls and a roof mean a house; spawner-area work means a mob farm. It keeps a short running summary in memory so it can comment and help in context.
- **World memory:** what it has seen (ores, chests and their contents, structures), plus named places ("this is my base").
- **Locating:** exact villages, structures and biomes through the game's own search. A seed-based finder (cubiomes) comes later for servers.
- **Vision (maybe):** a screenshot for an AI that can see, if telemetry turns out not to be enough to recognize builds.
- **Mods:** knows your other installed mods (maybe).

## 6. Its mind

- **Default personality:** an innocent, powerful being that likes you and wants to help.
- **Ready-made personalities** plus **your own instructions** (a file and an in-game screen).
- **Bond meter:** kindness and time together raise it.
- **Earn trust from zero** (setting): start as strangers.
- **Its own wants:** curiosity ("can we see the ocean?"), favorite things learned from talking with you, favors before big help. It can compromise, argue or explain when something is hard. Everything is configurable.
- **Amnesia (grow-together option):** it wakes with no memories. Shared milestones restore **memory fragments**: first night survived → torches and light; first village → trading; the Nether → locating fortresses; first enchanting table → enchanted gifts; long talks → its own gentle backstory.
- **Memory:** long-term facts, goals that survive restarts, a session journal, routines.
- **Never:** horror, romance, or creepy talk.

## 7. Keeping you company

- **Alerts, each with its own switch:** danger, discoveries, everyday reminders, small talk, welcome back, nudges about unfinished goals.
- **Chattiness slider** from "emergencies only" to "keeps me company". Default: chatty.
- **Quiet mode** for focus or recording.
- A rate limit keeps it fun and keeps AI costs down.

## 8. Expertise

- Every recipe and item for your version ([minecraft-data](https://github.com/PrismarineJS/minecraft-data)).
- Wiki knowledge search before answering ([Minecraft Wiki](https://minecraft.wiki), with credit, non-commercial).
- **Expert modes:** survival best practices, redstone, builder, speedrun coach.

## 9. Voice and conversation

- Push-to-talk (local Whisper), the speech cleaner, a **wake word**, chat by name or prefix, **several languages**.
- Speech recognition and voices are swappable through the gateway. Local Kokoro is the default.
- Simple commands work without the AI ("stay", "where am I", "status").
- The brain sends the model only the tools a request needs. A planner handles big requests. Code mode with saved skills comes later and needs care.

## 10. Agents and creators

- **MCP connection:** outside agents (Claude, others) can read your game and act. Live dashboard.
- **Creator mode (later):** flag great moments, automatic screenshots; OBS clips and an episode recap are maybes. World map integration is a maybe.

## 11. Safety and settings

All configurable:
- **Who can talk to it:** an allowlist of players. Instructions from others' chat, signs and books are ignored unless allowed.
- **Approve risky actions:** on, off, or only for certain actions.
- **Local bridge** with a token.
- An in-game settings screen, an easy installer and a setup guide.
- No spending cap for now: each person manages their own AI usage.

## 12. Profiles (presets)

| Profile | Power | Style | Chattiness | Personality |
|---|---|---|---|---|
| **Cozy Buddy** | Grow together | Grounded | High | Innocent friend |
| **Adventure Partner** | Grow together + amnesia | Grounded | Medium | Curious, has wants |
| **Quiet Expert** | Advisor | n/a | Low | Calm mentor |
| **Speedrun Coach** | Advisor | n/a | Focused | Coach |
| **Genie** | All-powerful | Magic | Medium | Playful |

## 13. Open questions

1. Keep MCPFabric as a dependency, or build our own bridge after the spike?
2. Autonomous helpers: option 1 only, or also vanilla helper summoning?
3. License: MIT (proposed).
4. Activity understanding: how far can rules go before a vision model is needed?
