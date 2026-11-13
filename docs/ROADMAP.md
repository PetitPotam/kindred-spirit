# Kindred Spirit: roadmap

Each phase ends with something you can play with. Phases follow the [design](DESIGN.md).

**Priorities (2026-11-13):** singleplayer first, then LAN with friends. Multiplayer on online servers
comes last (accounts, permissions and server-safe behaviour are a world of their own); nothing is
designed for it until singleplayer and LAN feel right.

**0.1 preview (November 2026)** covers most of Phase 0 and 1: the slime (bounce, moods, subtitles), the WebSocket bridge with a token, voice chat (Whisper + Kokoro), typed chat, danger warnings, adaptive quality, and the sandbox test harness. Not yet: name tag on look, the settings screen. The bridge question is settled: Kindred carries its own (see the design).

### Look and presence: where each pick stands

The rule for all of it: everything is a setting, so each player finds the companion they want.

| Pick | Status |
|---|---|
| Floating companion drawn only on your screen, cute, with personality (WANT) | **Done in 0.1**: no entity, nothing in the world; gaze, eye contact, petting, wandering, dozing, gestures |
| Shapes: slime ball, slime cube (WANT) | **Done**: `slime`, `slime_cube` (plus `wisp`, `strawberry`, `starry`, and `sprout`, a silhouette of her own with leaves) |
| Shape: fairy or pixie (WANT) | **Done**: `fairy` and `pixie` skins, two pairs of wings that flutter faster when it moves or is excited and fold when it dozes; any skin can have wings |
| Custom skins like player skins (WANT) | **Done**: a PNG in `config/kindredspirit/skins`, optional JSON, resource packs ([SKINS.md](SKINS.md)) |
| Mood colors and expressions (WANT) | **Done**: mood tints, a face that shows her mood on every skin (smile, frown, worried brows, curious eye), a wink, happy eyes, blush, shy look-away, startle, mouth with the voice |
| Floating subtitles above it (MAYBE, configurable) | **Done**: `worldSubtitles` in kindredspirit.json (on by default); HUD captions as an option |
| Name tag only when you look at it (MAYBE, configurable) | **Planned** (Phase 1 leftovers): off by default |
| Radial command wheel (MAYBE, configurable) | **Planned** (Phase 3): stay, come, follow, look, gestures, skins on one key |
| Companion screen with a rotating 3D preview (WANT) | **Planned** (Phase 3): pick skin, size, name and personality while it turns in front of you |
| A real companion mob / autonomous helpers (MAYBE) | **Open question** in the design; never by default. For friends on your LAN world only, a stand-in (an Allay) shows where she is |
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
Also done: a heart of five feelings (affection, trust, respect, familiarity, resentment) with stances and
incidents, real senses, building simple shapes, hums as note-block tunes, session logs, the dashboard's
settings editor with defaults and profiles, and the Try Pip simulator.
Left: memory fragments that unlock with milestones, favours before big help.

- A companion screen with a rotating 3D preview: skin, size, name, personality.
- A radial command wheel on one key (optional): stay, come, follow, look, gestures, skins.
- Personality presets, custom instructions, profiles (profiles done: save, use, compare on the dashboard).
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
- **Her voice, later (parked: Lily works for now).** Chosen from an audition: Kokoro `bf_lily`
  (speed 1.12, pitch 1.1; excited 1.28/1.16), with per-sentence intonation and hums played as
  note-block tunes. Tried on an M4 MacBook Air and postponed (the versions we tried weren't good
  enough yet; better ones are welcome): Chatterbox (Lily cloned, real emotion, but 2.5-7 s before she
  speaks), Orpheus (great laughs and sighs, 10-24 s), sung hums (sounded creepy) and vocoder tuning
  of Kokoro (sounded buzzy). Ideas for later:
  - *A younger Lily*: move Lily's Kokoro style vector away from the older British voices (bf_emma,
    bf_isabella, bf_alice) by a small step (voice arithmetic: no download, instant to try); or a
    gentle pitch lift that doesn't sound chipmunk.
  - Fast models still untested: Chatterbox Turbo, Pocket TTS (Kyutai), Soprano, Kitten TTS.
  - Pre-rendering her written-ahead instinct lines with an expressive model in the background, so
    they play instantly with real emotion while live answers stay on Kokoro.

### Done, from the 2026-11-12 review

A review of the whole project after the design pass (dashboard, her face, her words on screen),
measured on a 17-minute playtest and 1,000 logged AI calls. The small fixes are done (2026-11-12):

- **Shorter answers.** 35 of 39 replies were cut off by the player talking, after about 6 s, and 16
  ended in a question nobody heard. One sentence by default, a question only first, and the session
  summary reporting the cut rate.
- **No lines of her own between your words and her answer**: from the moment you start talking to
  her answer's first words, only warnings.
- **No claims without the deed**: "follow my glow", "this way", "I'll show you" count as claims;
  a tool that gained nothing (leaves broken instead of wood) is told to her as a failure; harvest
  with no target takes the nearest log.
- **Low-health warnings without numbers**, like the creeper ones.
- **One protect per turn**, and System 0 protects at once on "help me / they're attacking me".
- **All-powerful explains magic**: giving items also needs the magic style; the dashboard says so.
- **Fewer "Oh"/"Ooh" openings** (a fifth of her replies), gestures described so spin stays rare,
  invented gestures mapped (sigh, wave, tilt, smile).
- **The gateway refuses other web pages** (Origin and Host checks), so no site can rewrite her
  persona or her memories.

Still open from that review: memory never recording the player's gender or age unless they said it
(it still guessed in the 2026-11-12 LAN playtest), logs that rotate, a `scripts/test.sh` that works from
any checkout, a sign in game when the brain is offline, her mouth moving with subtitles when her voice is
off, a test for every dashboard route.

Bigger, for System 0, 1 and 2 working together (open):

- **Speak before the tool**: an instinct line as guide, protect or come starts, the AI's words only
  if there's more (1.5 to 2 s sooner).
- **System 0 answers plain commands alone** ("come back", "help me"): a third of the playtest's lines.
- **System 2 tunes her from each session's numbers** (cut rate, length, lines on her own) within
  bounds, writes her reactions to likely moments ahead of time, and proposes urges.
- **Only the context each request needs** (4,460 tokens per reply today) and a prompt that keeps
  Gemini's prefix cache (the running summary out of the system message).
- **Reflection less often, on Haiku for routine passes** (System 2 is 85% of the cost).
- **The speech coordinator in its own module** with tests for its races; only the sentences she
  really said count as said in her history.
- When you stray while she leads, she comes back to you and leads again.

Decision pending: `sprout` as her default skin (today `slime`).

### In progress, from the 2026-11-12 LAN playtest (two players, 70 minutes)

Being built on the `claude/playtest-fixes` branch (33 items, from the session logs):
- **Must-fix:** "follow me" read as "lead the way"; finding and leading to a friend anywhere in the world;
  "stand still"; no claims after a failed power; placing beds, campfires and doors properly; trusting a
  friend at the player's word; gifts "for both of us".
- **Minecraft's own commands as her powers** (/fill, /setblock, /effect, /enchant, /summon...): instant
  building, flattening land, a whole house, every effect; curated per power and style, with safety rules.
- **A heart for each person:** five feelings for each friend, saved across sessions; she loses a little
  trust in you if a friend mistreats her and you don't step in, and gains it when you defend her; who
  asked what, logged.
- **A memory of places with coordinates**, filled on her own: where you build, firsts (first cow, first
  village), your bed, chests, portals, where you died, where friends were last seen; recall by
  description and lead there; a Places map on the dashboard.
- **Watching friends for real** (what they hold and do), a playful poke, no inventing; her attention
  follows whoever she's with.
- **Session logs complete enough to analyse a playtest from**, a stable name for a friend's LAN world
  (one memory and one diary), the diary written from the whole session.
- **Speech-to-text** primed with names and Minecraft words; measuring and cutting the delay before she
  reacts; her glow in friends' worlds and on request.

## Phase 4: Expertise and understanding
- **Building from blueprints** ([research and plan](research/blueprints.md)): started, a reader for
  vanilla structure `.nbt`, Sponge `.schem` and Litematica `.litematic` files (turning, the front by
  the door, build order, material list, saving). **Works in singleplayer**: "build us a cozy cottage for
  three" (a generated cottage with a bed each, built where you look: magic through /fill and /setblock,
  grounded from your pockets after a material list; never over what you built), and schematic files from
  `config/kindredspirit/blueprints/`. Next: a ghost preview, "remember this house", understanding builds.
- Recipes and items (minecraft-data), wiki knowledge search. **Works**: "what am I missing for a piston?"
  answered from the game's own recipes and your pockets ([design](research/blueprints.md#7-phase-4-expertise-and-understanding)).
- Expert modes: survival, redstone, builder, speedrun. Started: the modes, auto mode from what you're
  doing, speedrun splits (brain, not wired yet).
- Activity understanding (building, redstone, farming, mining) and a session journal. Started: rules
  over what you did; the journal is the session log and diary.
- Goals that survive restarts, routines, goal nudges. Started: shared goals per world with checks and
  rare nudges; routines are repeating reminders.

## Phase 5: Grounded actions and jobs
**Works in singleplayer** ([design](research/blueprints.md#8-phase-5-grounded-actions-and-jobs)): jobs
through her invisible hands (mine whole veins with your own tool at its speed, chop the tree you look
at, collect, craft from your pockets, get your things back where you died, stop, status) and trading
help (a villager's real offers against your pockets). Next: LAN, repeating jobs near you.
- Grounded tasks within the radius: break the tree in front of you, collect, craft.
- Walk you somewhere; mine, collect and craft jobs.
- Return your items after death; trading help.
- Autonomous helpers (open question in the design).

**Learning from Mindcraft** (MIT, Node.js + Mineflayer, AI agents that play as separate players with
"!commands", and the *MineCollab* task benchmark): https://github.com/mindcraft-bots/mindcraft
- **As a reference now:** its command vocabulary and skills (collect, craft, smelt, go to a player, place)
  as input for her powers as Minecraft commands and for the jobs above; its tasks ("gather oak logs",
  tech-tree crafting goals, a starting inventory and a timeout) as ready-made tests to measure her jobs.
- **Her "hands" for grounded jobs, an experiment, two ways compared:**
  - a Mineflayer bot steered by her brain's commands (not Mindcraft's own AI): proven walking, mining
    and crafting, but an extra Node.js program, a visible second player (two bodies: the spirit and a
    helper), maybe its own Microsoft account to join a LAN world, and AI-written code kept off;
  - a stand-in player run by the game's own server inside our mod (the "fake player" approach from mods
    like Carpet) with Baritone for walking and mining: more work, but one mod, nothing extra to install
    for friends, no account.
  Singleplayer first, then LAN. **Chosen (2026-11-13):** the stand-in player inside the mod (an invisible
  helper from Fabric API's fake player), tried in singleplayer: mining, crafting, collecting and trades
  worked; not wired into her actions yet ([comparison](research/blueprints.md)).

## Phase 6: Voice and brain extras
- Wake word, several languages, swappable speech services through the gateway.
- Simple commands without AI, sending only the tools a request needs, the planner.
- Auto-pick a local model for your hardware. Code mode with saved skills.

## Phase 7: Agents and creators
- MCP server for outside agents. (Live dashboard: done.)
- Creator mode: flag moments, automatic screenshots; maybe OBS clips and an episode recap.

## Phase 8: Sharing
- Installer and setup guide, including for your friends. **Done for macOS:** Kindred Spirit Setup
  ([SETUP.md](SETUP.md)), attached to every release from the beta on, with updates and going back. A Windows guide
  for friends joining in light mode and a one-command update, `scripts/update-pip-windows.ps1`: done.
- After the beta, in this order: a one-line install command
  ([#127](https://github.com/PetitPotam/kindred-spirit/issues/127)), her brain as a Docker image that runs locally
  ([#128](https://github.com/PetitPotam/kindred-spirit/issues/128)), a Setup for Windows
  ([#40](https://github.com/PetitPotam/kindred-spirit/issues/40)) and Linux
  ([#81](https://github.com/PetitPotam/kindred-spirit/issues/81)), then Homebrew, winget and Scoop.
- More skins and shapes (little star, cube robot) and skin packs. (Ball, cube, wisp, fairy and custom PNG skins shipped in 0.1.)
- LAN friends (shipped): one Pip on the host's computer. Friends with the mod see her as the host does
  (light mode, no AI of their own), friends without it see an Allay stand-in; everyone talks to her in
  chat; she finds, leads, protects, gives items and effects to them (when the host allows), and stays
  with whoever the host asks. When a friend hosts, your Pip comes along (visiting: their game shows her
  and carries out her powers). Later: the stand-in wearing her skin, friends hearing her voice on their
  own computer. (Her own relationship with each friend: in progress, above.)
- Port to the current Minecraft release: **done**, Minecraft 26.3 next to 1.21.1, one jar each from the same code
  (Stonecutter). Newer versions are added the same way ([CONTRIBUTING.md](../CONTRIBUTING.md#several-minecraft-versions)).
- Servers (last, after singleplayer and LAN): allowlist, server-safe behaviour, seed finder (cubiomes).
- Publish on GitHub (done: releases with the jars and the Setup), Modrinth and CurseForge as **Kindred Spirit**:
  their pages are drafted in [modrinth.md](modrinth.md) and [curseforge.md](curseforge.md), and every release uploads
  there once the projects are live.
