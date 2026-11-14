<div align="center">
  <img src="mod/src/main/resources/assets/kindredspirit/icon.png" width="112" alt="Pip, a little teal slime spirit, winking">

# Kindred Spirit

**A cute AI companion for Minecraft Java that floats beside you, talks with you by voice, and only changes your world when you ask.**

Minecraft 26.3 and 1.21.1 · Fabric · AGPL-3.0 · beta · her brain runs on macOS for now

[![CI](https://github.com/PetitPotam/kindred-spirit/actions/workflows/ci.yml/badge.svg)](https://github.com/PetitPotam/kindred-spirit/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/PetitPotam/kindred-spirit/badge)](https://scorecard.dev/viewer/?uri=github.com/PetitPotam/kindred-spirit)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/16677/badge)](https://www.bestpractices.dev/projects/16677)

<img src="docs/demo.gif" width="720" alt="Pip trying on skins: slime, soft cube, strawberry, wisp, starry orb, pixie and fairy">
</div>

Kindred Spirit is a little slime spirit (we call ours Pip) who keeps you company while you play.
Hold **V** and talk to it: it hears you, looks at your game (health, inventory, biome, time, what
you're looking at, monsters around you) and answers out loud. It also speaks up by itself when a
creeper sneaks behind you or your hearts run low.

- **Your world stays yours.** The mod is client-side only: no new blocks, items or mobs, nothing
  saved in your world. Add or remove it any time.
- **Bring your own AI.** Gemini with a free key by default, or another service with your key (OpenAI, Groq,
  Mistral, OpenRouter, Claude API), a model on your computer with Ollama, or an AI subscription you already have
  (Claude Code, Codex, Gemini CLI). Gemini is the one we've played with most; the others are less tried.
  Speech-to-text and voice run **locally**.
- **One app to set her up.** On a Mac, [Kindred Spirit Setup](#setup-macos) installs her brain, her voice and
  hearing, and Minecraft's side, explains every step, and updates them together.
- **Light on your computer.** It adapts to your frame rate and hardware (see [Performance](#performance)).
- **Made to be hacked on.** The mod is thin; the personality lives in a small Python "brain".

## Why I made Pip

I've always liked Minecraft, but mostly from the other side of the screen: I'd rather watch YouTubers,
speedrunners and streamers play it than play myself. I'm more of a PS5 gamer. I used to love playing games on a
computer, but I don't have a gaming PC or laptop any more, only my personal MacBook Air, and it had been a long time
since I'd played Minecraft. Then my brother asked me to play with him, so I did, on that MacBook Air.

That same day, Minecraft mod videos started showing up in my YouTube feed. I tried
[Verity](https://www.curseforge.com/minecraft/mc-mods/verity-je), and what stayed with me was its companion:
someone who is there with you while you play. I had an idea of what such a companion could be, looked for a mod
like it, and couldn't find one for Minecraft. So I started making Pip.

Pip makes my game more fun, more interesting, and less lonely. I'm not really a modder, and I don't claim to be:
this is a hobby I'm picking up. What I enjoy is understanding and building the AI architecture behind her, her
"brain", for something I knew I'd love to use. It feels magical to watch her come to life and talk with me, even
though there's still a lot of room to improve, and I'm having fun making her, and her AI, better along the way.

That's why Kindred Spirit is open source. Whether you're a modder, a hobbyist or just curious, you can share an
idea, help make the installation simpler, playtest and give feedback, or improve her in any way, so that anyone can
enjoy her the way I did, and the way my brothers and I did when we tested her together.

PetitPotam

Kindred Spirit was inspired by Verity's companion, nothing else: I didn't care about its horror or its story.
It isn't a fork: none of Verity's code or assets are used, and it's written from scratch for Fabric.

> **Status: beta.** It's playable and fun, and still young: some things haven't been tried by anyone on a real
> computer yet ([what](#what-hasnt-been-tried-yet)). Contribute, playtest and send feedback, however you like:
> see [helping](#helping) and the [design](docs/DESIGN.md).

## A note from me

Kindred Spirit is a hobby project. I make it because I enjoy it, and to share with my brothers. I'm enjoying the
process of it all, not the destination. I love building a repo that feels clean and cared for, and this is my way of
living the open source experience.

It's also how I learn. I'm exploring different AI models, including open ones, and how they work: memory, thinking,
knowledge and the systems around them. I chose Minecraft because it's a fun and easy way to start. It's simpler to
learn, and I enjoy it more because I get to play with what I build, instead of building an AI system around a serious
project that would be less rewarding.

I'm new to Java and Minecraft modding, and I'm learning as I go. I built it with AI, openly.

If you try it and like it, that makes me happy.

## What works today

| | |
|---|---|
| A slime ball drawn beside you | bounces and squishes, blinks, color follows its mood, mouth moves with its voice |
| Voice chat | hold **V**, speak, release; local Whisper hears you, local Kokoro answers |
| Typed chat | just type in the game's chat: in singleplayer everything goes to her; on a server, start with her name ("Pip, where are the cows?"). Or `/kindred <message>` (`/ks`). Set `chatMode` to `all`, `name` or `command` |
| In-game commands | `/kindred memory` (what she knows here), `memory worlds`, `memory import <world>` (bring what she knew about you from another world), `memory forget <words>`, `reset` (a brand-new companion for this world), and the gateway's special instructions: `persona`, `fact`, `hint`, `model` (`clear` removes), `instructions`, `pause`, `resume` |
| It understands your game | health, hunger, armor, effects, inventory, position, biome, time, weather, what you look at, nearby hostile mobs with direction |
| Real senses | she sees only what's in her line of sight from where she floats, hears by the game's own sound names ("zombie groans" behind a wall), feels rain, snow and the cold, watches what you do (placed, mined, crafted, ate), and finds the new more interesting than the familiar |
| Danger warnings | creeper within 8 blocks, lava or a big drop in the direction you're heading (also on the way she leads), health at 3 hearts or less: instant subtitle, voice right after, with cooldowns |
| Her glow | in the dark (night, caves) her soft light lights the way around her, in singleplayer: an invisible light that moves with her and is never left behind (`glow` in the mod's settings) |
| She has a heart | a whimsical character with a **bond meter**: kindness brings her closer and makes her open up, propose plans and play pranks; hitting her or being mean makes her keep her distance, sulk, or vanish for a while. She forgives quickly ([how](docs/HEART.md)) |
| She discovers her powers | she doesn't know what she can do until you ask. She answers at once ("I'll try!"), then the power slowly wakes up in the background: she senses something strange, maybe asks you a small favour, and then "I can sense diamonds now!" She remembers it after that |
| She helps | finds ores, animals ("where are the sheep?"), blocks, players and any structure or biome, and tells you which way; **leads the way** there, floating well ahead of you with an arrow and the distance at the top of the screen and a sparkle trail (she keeps ahead even when you sprint, follows a walking animal, and calls you back if you go the wrong way); pushes monsters away, places a torch, **chops a whole tree or mines a whole vein** you look at, with your own tool at its real speed, and **crafts** from your pockets (what drops goes in your inventory), **builds** with you: simple shapes (a pillar, corners, a wall, a floor, an outline), **any geometric shape at any size** (circles, stars, hearts, spirals, spheres, domes, round towers, cones, pyramids, a donut, an arch; hollow or solid, lying down or standing up), a crop farm, a nether or end portal, blueprints from a catalogue of 250, and **flattening land** around you with the ground that's there (**"undo that"** puts her newest build or flattening back exactly as it was, up to 16 back); magic style gives items and effects (haste, night vision, speed, healing, food...), all-powerful changes time and weather. When asked, as a standing request ("always protect me", "tell me when we're near diamonds"), or she offers if you asked before |
| It remembers and learns | who you are, what you like, your habits, your places, its own little personality, a diary of your sessions; reminders ("in 10 minutes", "at night", "next time we play") ([how](docs/MEMORY.md)) |
| It knows Minecraft | asked how something works, she answers from a local knowledge base of the Minecraft Wiki (current for your version) and learns pages she doesn't have yet in the background ([how](docs/KNOWLEDGE.md)) |
| Friends on LAN | one Pip, on the computer that runs her: friends with the mod see her exactly as you do, friends without it see a stand-in; everyone talks to her in chat; she finds, helps and stays with whoever you choose, and comes along when a friend hosts the world ([below](#friends-on-your-lan-world)) |
| Personality | greets you, small talk when it's been quiet a while (configurable), moods |
| Subtitles | above the slime, optional captions and a log in your chat (only on your screen) |
| It feels alive | looks where you look, looks back when you look at it, wanders around you when you stand still, dozes after a long quiet time, leans as it floats, blinks, its eyes move before its head, its face shows its mood (and it winks); hums little tunes with the game's note-block sounds; finds its way around walls and through doors instead of over the roof |
| You can direct it | say or type "stay here", "come here", "follow me", "look at me", "do a spin"; pet it by sneaking while looking at it |
| Skins | a slime, a soft cube, a fairy and a pixie with fluttering wings, a glowing wisp, a strawberry, a starry orb, Sprout with its leaves, or your own PNG ([how](docs/SKINS.md)) |
| Her dashboard | press **K** in the game: a page on your computer with her heart and mood, your conversations, what she remembers, the buildings she knows, every AI call, and all her settings, changed live ([below](#watching-her-think)) |
| Session logs | every play session gets a timeline and a summary in `~/.kindred-spirit/logs/sessions/`, shown on the dashboard, to see what went wrong |
| Blueprints | **builds whole buildings from files** where you look, its door toward you: "build us a cozy cottage for three" (one she makes up, a bed each), or any `.nbt`, `.schem` or `.litematic` in `config/kindredspirit/blueprints/` ("a circle to build on"), and the game's own village houses, shipwrecks, pillager watchtower, igloo and ruined portals ("a small desert house", "the plains smithy", "a shipwreck"), which the game copies for her when it starts, on every Minecraft version. The game describes every file (what it is, its category, size, materials, a top and a front picture); she finds the right one by what you ask, describes the two or three best and asks which when several fit, and checks before a big one. Magic builds it in seconds; grounded first tells you the materials. She never builds over what you built. Browse, add and remove them on the dashboard's **Blueprints** page |

Not yet: jobs on LAN ([#37](https://github.com/PetitPotam/kindred-spirit/issues/37)), repeating jobs
([#13](https://github.com/PetitPotam/kindred-spirit/issues/13)), an in-game settings screen. That's the [roadmap](docs/ROADMAP.md).

### What it may do: power and style

You decide how much it can do (`/kindred power`, `/kindred style`); the mod enforces it, not the AI.

| | grounded (only what really exists) | magic (things can appear) |
|---|---|---|
| **advisor** | talks, finds ores and animals, locates places, leads the way | same |
| **helper** (default) | + pushes monsters away, places one of *your* torches, chops, builds with your blocks | + gives items and effects, torches and blocks from thin air |
| **allpowerful** | + time and weather | + all of it |

Finding and guiding work everywhere; anything that changes the world works in singleplayer, when you
host LAN, and in a friend's LAN world whose game has Kindred (their game does it for her), done the
way a command would.

### Friends on your LAN world

One Pip, on your computer: your AI, her voice, her memory and her heart. Open your world to LAN and
friends join on the same Minecraft version as yours (26.3 or 1.21.1, with the matching Kindred jar):

- **With the mod (light mode):** they see her exactly as you do (her skin, face, moods, gestures and
  subtitles), drawn by their own game from what yours sends. No AI, Python or keys on their side.
  They talk to her in chat ("Pip, ..."); their talk key opens the chat with her name typed in, or uses
  their own speech-to-text if they've set up the brain. Her voice plays from your computer.
  (`sharedPip: "own"` in their settings gives them their own Pip instead.)
- **Without the mod:** they see a stand-in the plain game can draw (an Allay named after her that
  follows where she floats, hidden on your screen) and talk to her in chat the same way.

She answers them in chat as "[Pip] ...", knows who said what, and sees them in the world. You decide:

- **Who she stays with:** "Pip, stay with Robin" or `/kindred follow robin`; `/kindred follow me`
  brings her back.
- **Whether friends may ask for her powers** (`lanGuestPowers`, on by default): gifts, effects like
  haste or night vision, healing, finding, leading, protecting, within her power and style. Off: they
  only talk with her.

**A heart for each of them.** She has the same five feelings for each friend as for you (lighter:
she lives with you), moved by how they treat her: their words, their hits and pats (their game tells
yours who did it), kept across sessions. She's warm with the kind one and prickly with the one who's
mean to her. Their words don't change her bond with you, with one exception: when a friend hurts her
in front of you, she notices whether you stand up for her ("leave her alone" counts; saying nothing
costs a little trust). "From now on, do what Robin says" lets that friend ask her to follow them or
stay. The dashboard shows a card for each friend, and every session log says who asked for what.
`lanGuests: false` turns all of it off.

**When a friend hosts the world instead:** your Pip comes with you (her brain stays on your computer).
If their game has the mod, it shows her to everyone (an Allay for players without it), passes their
"Pip, ..." chat to your brain and her answers to their chat, and carries out her powers in their
world for you: protect, gifts, effects, chopping, building, time and weather (`lanVisitors` on their
side, on by default, lets them say no). Without the mod on the host's side, she's only with you:
she talks, sees, finds and leads, but can't change their world.

A friend setting up light mode on Windows: [PLAY-WITH-FRIENDS.md](docs/PLAY-WITH-FRIENDS.md) (Minecraft with
Fabric, Fabric API and the Kindred jar; building the jar needs Java 25). On a Mac, the Setup's **Minecraft** step
is all a friend needs.

### It shouldn't feel like a robot

Its movement is designed to feel like a small living thing, not a camera attachment:

- **Springs, never snaps.** Every movement eases in and settles: position, head, eyes. A change of mind
  curves instead of jerking.
- **It notices before it reacts.** A short, slightly random delay (0.1–0.35 s) before it turns to
  something, like a person noticing; threats get a faster reaction.
- **Eyes first, head after.** Its pupils jump to what caught its attention, and its head follows more slowly.
  Tiny eye flicks keep it from staring like a doll.
- **It keeps its spot.** Small turns of your head don't drag it around; it only floats back to your
  side once you've clearly turned away, and holds still while you look at it, so you can look it in the eyes.
- **Its own little life.** It drifts on smooth noise (never a visible loop), switches shoulders now and then,
  glances at animals and items, and wanders around you when you stand still. After a long quiet while it
  dozes ("z z z") and wakes with a little start when you move.
- **It stays out of your way.** It never parks in the middle of your view, and floats over walls instead of into them.

Gestures (nod, shake, spin, hop, wiggle, happy, shy, think, startle) are layered on top, and the AI can
add one to its replies when it fits ("[excited] {hop} Diamonds!").

**Every one of these is a switch**, so you can have anything from a calm companion that just floats
beside you to a curious one that wanders and plays. `/kindred life` lists them; change one in game
with `/kindred life <name> <value>` (saved right away), or `/kindred life reset`:

| Switch | Default | What it does |
|---|---|---|
| `wander` | on | wanders around you when you stand still |
| `drift` | 1 | gentle drifting beside you: 0 still, 1 normal, 2 lively |
| `switchSides` | on | switches shoulders now and then |
| `glances` | on | glances at animals, items and around (off: looks where you look) |
| `lookBack` | on | looks back at you when you look at it |
| `eyeContactReactions` | on | gets happy or shy when you hold its gaze |
| `petting` | on | sneak while looking at it to pet it |
| `watchThreats` | on | turns to watch nearby monsters |
| `moodGestures` | on | hops when excited, looks up while thinking |
| `aiGestures` | on | plays the gestures the AI adds to its replies |
| `dozeAfterSeconds` | 90 | dozes off after this many quiet seconds; 0 = never |
| `turnSlack` | 32 | degrees you can turn before it floats back to your side; 0 = always right at your side |
| `keepOutOfView` | on | never parks in the middle of your view |

## How it fits together

```
Minecraft 26.3 or 1.21.1 + Fabric
  └─ Kindred Spirit mod (Java, client only): draws Pip, reads the game, acts when allowed, mic and speaker
        │  WebSocket on 127.0.0.1:47811, with a token from ~/.kindred-spirit/token
  Kindred brain (Python): conversation, moods, danger rules, tools, memory and learning
        │  one address
  Kindred gateway :11437 — choose each part (docs/GATEWAY.md):
        ├─ AI              Gemini / Ollama / Groq / OpenAI / …
        ├─ speech-to-text  local Whisper / Groq / OpenAI
        ├─ voice           local Kokoro / OpenAI
        ├─ embeddings      local bge-small / Gemini / Ollama / OpenAI
        └─ memory          local SQLite / a gateway you deployed elsewhere
```

The whole picture (the three ways she thinks, how her character is put together, memory, guards,
and which AI model fits each job) is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Why a separate brain?** The mod only sees, draws and plays sound. Everything that makes the
companion *itself* is Python, which is quicker to change and easier to contribute to, and any AI
can sit behind the gateway.

**Why not build on MCPFabric?** [MCPFabric](https://github.com/denfry/mcpfabric) (MIT) is
excellent for letting AI agents *play* Minecraft: 70+ tools, many of them operator-level, over an
HTTP bridge plus a Node MCP server. Kindred needs a mod anyway to draw the companion, and what the
brain reads is a small snapshot; adding MCPFabric would mean two mods, Node, and an operator-level
bridge for a companion that by design never changes your world. So the mod carries its own small
bridge (~150 lines). MCPFabric stays the reference for later phases (actions, an MCP server for
outside agents), where we may interoperate or borrow MIT code with credit.

## Setup (macOS)

**Kindred Spirit Setup** is an app you download and open, with no terminal and nothing else to install by hand. It
opens a guide in your browser that explains each step, recommends a choice, tests it, and gives you a help prompt to
paste into any AI assistant if something goes wrong:

1. From the newest [release](https://github.com/PetitPotam/kindred-spirit/releases), download
   `Kindred-Spirit-Setup-<version>-macos-arm64.dmg` (Apple silicon: M1 and newer) or `...-macos-x86_64.dmg` (Intel).
   It needs macOS 12 or newer and about 3 GB of free space.
2. Drag it to Applications and open it. The first time, macOS says it can't check the app for malware, because the
   project doesn't pay for Apple's yearly developer membership: on macOS 15 or newer, press **Done**, then **System
   Settings → Privacy & Security → Open Anyway**; on macOS 12 to 14, Control-click the app → **Open**.
3. Follow the steps: your computer, her brain, her AI, her instincts, voice and hearing, Minecraft (a launcher
   profile for 26.3, recommended, or 1.21.1), saying hi to her in the game, her slow thinking, and whether she wakes
   when you log in.

Installed only the mod, from Modrinth say? In your own world, one chat message says that Pip needs her brain on
this computer, with links to the Setup and to playing with a friend who hosts her (`/kindred hint off` hides it).

Later, its **Updates** step installs a new version of her brain, the mod and the Setup together, keeps your settings
and memories, and can go back to the version before. Everything, step by step: **[docs/SETUP.md](docs/SETUP.md)**.

The Setup is attached to every release from the beta on. The first preview (0.2.0-preview) came before it: if the
newest release has no `Kindred-Spirit-Setup-...dmg`, use the manual setup below.

### What hasn't been tried yet

The Setup is built and tested on GitHub's Apple silicon and Intel Macs with every release, and was tried on an
Apple silicon Mac (how: [docs/TESTING-PLATFORMS.md](docs/TESTING-PLATFORMS.md)). Nobody has tried these yet, so
reports are very welcome:

- downloading the `.dmg` and getting past macOS's first-run warning, on macOS 15 or newer and on 12 to 14;
- a real Intel Mac;
- **Open Minecraft** with a real launcher and account, and whether macOS then asks for the microphone;
- the microphone test with a real microphone;
- her AI services with real keys through the Setup (its checks use a stand-in AI);
- updating from one real release to the next.

Not supported yet: hosting her brain on Windows ([#40](https://github.com/PetitPotam/kindred-spirit/issues/40)) or
Linux ([#81](https://github.com/PetitPotam/kindred-spirit/issues/81)) (friends on Windows can join a Mac host's
world), a signed and notarised app (that needs a paid Apple membership), and voices other than Kokoro, OpenAI's or
subtitles only.

### Manual setup (for contributors, or without the Setup)

The Setup app above is the easy way. This way takes a terminal and about 15–30 minutes, most of it downloads: you need
Minecraft Java Edition and [Homebrew](https://brew.sh), and the commands below install a JDK 25, Python 3.12 and
whisper.cpp, then build the mod with Gradle. For the AI, use what you already
have: a free [Gemini key](https://aistudio.google.com/apikey), your Claude subscription (Claude
Code), another AI's command-line tool you pay for (Codex, Gemini CLI, Cursor), an API key (OpenAI,
Claude API, Groq, OpenRouter, Mistral), or nothing at all with [Ollama](https://ollama.com) on your
computer.

```bash
brew install openjdk@25 python@3.12 whisper-cpp
git clone https://github.com/PetitPotam/kindred-spirit.git && cd kindred-spirit
scripts/setup.sh                 # the guide (below)
(cd mod && ./gradlew build)      # builds the mod: one jar per Minecraft version (26.3, 1.21.1)
python3 scripts/install_profile.py      # quit the Minecraft Launcher first
```

`setup.sh` prepares the brain, then a short guide asks what you have for each of the four parts:
**the AI** (how she thinks), **speech-to-text** (how she hears you), **the voice** (how she
speaks; or subtitles only) and **memory** (on your computer or your own deployed gateway). It
saves your choices (keys go in `~/.kindred-spirit/secrets.env`, readable only by you), installs
only the local tools you picked, starts everything and tests each part the way she uses it:

```
  ok   AI           Hello, friend, there!
  ok   voice        65 KB of WAV
  ok   speech->text heard: 'Testing 1 2 3.'
  ok   embeddings   384 numbers per text
  ok   memory       stored, found and removed a test memory
```

Anything that fails comes with how to fix it. Run the guide again any time to change your choices
(`brain/.venv/bin/python scripts/guide.py`), or just the test (`... scripts/guide.py --check`).
Without questions: `scripts/setup.sh --defaults` (Gemini, everything else local).

`install_profile.py` adds a **Kindred Spirit (Fabric 1.21.1)** profile with its **own game folder**
(`minecraft-kindred`), installs Fabric Loader and Fabric API, and backs up your launcher profiles.
Your other profiles, mods and worlds are untouched. For the newest Minecraft, `--minecraft 26.3` adds a
**Kindred Spirit (Fabric 26.3)** profile next to it, with its own folder (`minecraft-kindred-26.3`).

(The Setup's Minecraft step makes the same profiles, with 26.3 recommended.)

Then play: double-click **`scripts/play-mac.command`**. It starts everything and opens the launcher
**from Terminal**, which matters on macOS: the launcher has no microphone permission of its own,
so started from the Dock the game records silence. Pick the Kindred Spirit profile and press Play.

**Linux:** `scripts/setup.sh` and her brain pass GitHub's install checks on Ubuntu (without her voice), and a real
Minecraft client there says hi and she answers; nobody has played with her on Linux yet
([#81](https://github.com/PetitPotam/kindred-spirit/issues/81)). Hearing needs `whisper-server` from
[whisper.cpp](https://github.com/ggml-org/whisper.cpp).
**Windows:** friends joining a host's world are covered ([PLAY-WITH-FRIENDS.md](docs/PLAY-WITH-FRIENDS.md)); hosting
her brain there works with three PowerShell scripts ([docs/HOSTING-WINDOWS.md](docs/HOSTING-WINDOWS.md)) or with
Docker ([docker/README.md](docker/README.md)), for technical players for now.

### Controls

| | |
|---|---|
| **V** (hold) | talk; release to send (change it in Controls → Kindred Spirit) |
| **K** | open her dashboard in your browser (on the computer where her brain runs) |
| **H** | stop her, everything at once: talking, leading, a build or blueprint halfway, a job ("undo that" then puts back what she changed) |
| **J** · `/kindred settings` | her settings, in the game: the dashboard's settings and profiles, each with its explanation and default; also from Mod Menu |
| just type in chat | talk to her (on a server, start with her name); or `/kindred <text>`, `/ks <text>` |
| `/kindred status` | brain connection, skin, mode, quality level, mood |
| `/kindred reconnect` | after restarting the brain |
| `/kindred sleep` / `/kindred wake` | put her to sleep (her brain, voice and hearing stop, to save your computer's power) and wake her up; her dashboard has the same buttons, and "Stop everything" |
| `/kindred hint off` / `on` | the "Pip needs her brain on this computer" message, shown once per game in your own world when her brain isn't set up here |
| `/kindred skin <name>` · `/kindred skins` · `/kindred skins reload` | change its look, list skins, reload your skins folder |
| `/kindred mode follow\|stay\|come` | follow you (default), wait here, come close for a moment |
| `/kindred follow <player>` · `/kindred follow me` | on LAN: float beside a friend, or come back to you |
| `/kindred heart` · `/kindred heart fresh` | how she feels about you (five feelings, open hurts), or a fresh start for her heart here |
| `/kindred side left\|right\|above\|auto` | which side it floats on |
| `/kindred look me\|there\|ahead\|up\|down\|around` | where to look for a few seconds |
| `/kindred emote <name>` | nod, shake, spin, hop, wiggle, happy, shy, think, tease (a wink), doze |
| `/kindred life` · `/kindred life <name> <value>` · `/kindred life reset` | its liveliness switches (see above) |
| `/kindred power advisor\|helper\|allpowerful` · `/kindred style grounded\|magic` | what it may do (see above) |
| sneak while looking at it | pet it |

Mostly, you just talk to her, and discover what she can do along the way (that's the point, so
this list is for the curious): "stay here", "come here", "look at me", "do a spin", "any diamonds
near me?", "where are the sheep? lead the way", "where's the nearest village? take me there", "push them away", "always protect me",
"this is my base", "remind me in 10 minutes to check the furnace", "put my block back".

## Watching her think

Her brain comes with a dashboard at **http://127.0.0.1:11440** (press **K** in the game to open it, or open Kindred
Spirit Setup once she's set up; `scripts/start.sh` starts it in the manual setup): her heart and mood live,
friends in your world (whom she stays with, what they may ask), powers waking up, what she says and
does, every AI call with its tokens and cost, speech and voice timings, her memories per world (with a
search that shows what she'd recall), past play sessions (replay what she said), **Try Pip** (talk to
her without the game), and **every setting** with its default, profiles to save and compare, and the
gateway's special instructions. Changes apply live. See [docs/DASHBOARD.md](docs/DASHBOARD.md).

## Settings

- **Brain:** `~/.kindred-spirit/brain.toml` (name, personality, model, voice, chattiness, alerts).
- **Mod:** `config/kindredspirit.json` in the profile's game folder (`minecraft-kindred` for 1.21.1,
  `minecraft-kindred-26.3` for 26.3, next to your `minecraft` folder) (skin, quality, subtitles, captions, position, size,
  volume, the guide arrow and sparkle trail (`guideArrow`, `guideTrail`), friends on LAN (`lanGuests`,
  `lanGuestPowers`, `lanVisitors`, `sharedPip`, `follow`), her HUD with the game's hidden (`hudWithHiddenGui`, for
  filming), and the liveliness switches under `"life"`).
- **Everything above** is also editable on the dashboard's Settings page, live, with each default and profiles.
- **AI, speech-to-text, voice, embeddings, memory storage:** all chosen in the gateway, live, no
  restart. The guide: **[docs/GATEWAY.md](docs/GATEWAY.md)**.
  ```bash
  G="brain/.venv/bin/python services/kindred_gateway.py"
  $G check                      # tests every part
  $G use ai ollama              # or gemini, groq, openai, openrouter, mistral
  $G use stt groq               # or local_whisper, openai
  $G persona "Speaks like a pirate."
  ```
  Keys go in `~/.kindred-spirit/secrets.env` (readable only by you).
- **Memory:** each world has its own companion by default; `scripts/memory.sh` shows what she remembers, `worlds` and `import` bring memories from one world to another, `reset` starts over ([how it works](docs/MEMORY.md)).
- **What she knows about Minecraft:** a local knowledge base (recipes, mobs, biomes, redstone, farming, build guides) you fill yourself from the Minecraft Wiki and your own notes: `python3 services/knowledge/kb.py crawl minecraft-wiki --category Mobs --limit 50` ([docs/KNOWLEDGE.md](docs/KNOWLEDGE.md)). She uses it when you ask how something works, and learns missing pages in the background.
- **Her heart** (discovering her powers, bond, pride, play-fights, her mood, animals, pranks, mischief when angry, vanishing...): `[heart]` in brain.toml ([docs/HEART.md](docs/HEART.md)).
- **Her voice:** set in the gateway: Kokoro's British `bf_lily` by default (a little faster and higher, each
  sentence said a bit differently), with moods (excited, calm, sad, whisper); `$G voice bf_emma` or a blend
  like `bf_lily*0.7+bf_emma*0.3` to change it: [docs/GATEWAY.md](docs/GATEWAY.md#her-voice).
- Looks: `skin` in kindredspirit.json, or `/kindred skin <name>`. Make your own: [docs/SKINS.md](docs/SKINS.md).

## Performance

Built for laptops from the start (developed on a fanless MacBook Air M4):

- **The slime adapts to your frame rate.** `quality = "auto"` steps down to a simpler mesh without the
  glassy shell (and sends game snapshots less often, scans a smaller area) when the game drops below
  30 FPS for 3 seconds, and climbs back after 15 good seconds. With Fast graphics it never goes above
  medium. Or set `low`, `medium` or `high` yourself.
- **Nothing heavy on the game's threads.** Meshes are built once; drawing a frame allocates nothing.
  Network, JSON, the mic and playback each run on their own threads.
- **The helpers adapt to your hardware.** `python -m kindred.hardware` picks the Whisper model
  (large-v3-turbo, small or base) and thread counts from your memory and cores; all helpers run at
  low CPU priority so Minecraft wins when both want the CPU.
- **Fast replies.** Speech-to-text ~0.8 s for a short question (Whisper tuned for push-to-talk
  clips), voice streamed sentence by sentence with Kokoro's int8 model: about **3.4 s from releasing V
  to hearing the answer** on an M4 Air with Gemini Flash-Lite. Danger warnings appear instantly.

## Testing without breaking your game

Three levels, from fastest to most real:

1. **Automated tests, no game, no key, no network:** `cd mod && ./gradlew test` (Java logic) and
   `brain/.venv/bin/python -m pytest brain/tests` (brain, including an end-to-end test of the
   WebSocket protocol with stand-in AI and voice services).
2. **A fake game against your real setup:** with the brain running,
   ```bash
   cd brain
   .venv/bin/python tools/fake_game.py chat "what should I build?" --play
   .venv/bin/python tools/fake_game.py creeper --play
   .venv/bin/python tools/fake_game.py speak "what's around me?"   # Kokoro asks, Whisper hears
   ```
3. **A sandbox Minecraft:** `cd mod && ./gradlew :26.3:runClient -PdevScript=devscripts/smoke-test.txt` starts a
   throwaway dev game (its own folder, `mod/versions/26.3/run`; `:1.21.1:runClient` for the older game), creates
   a test world, talks to the companion, spawns a frozen creeper behind you, drops your health and takes
   screenshots in `mod/versions/26.3/run/screenshots`.
   `devscripts/life-test.txt` does the same for its liveliness and every skin (eye contact, petting,
   gestures, stay and come, watching a creeper).

4. **Install checks on every system:** `scripts/test-install.sh all` installs and starts her in a throwaway folder
   on moved ports (the Setup app, her brain, Minecraft's side, and a real Minecraft client that says hi), the same
   checks GitHub runs on clean macOS (Apple silicon and Intel), Linux and Windows machines with a stand-in AI. What
   is checked where: [docs/TESTING-PLATFORMS.md](docs/TESTING-PLATFORMS.md).

The demo video is made the same way: the sandbox films itself from a script and an editing script
adds titles, captions and music. See [demo/README.md](demo/README.md).

Only then install into your launcher.

## Privacy

By default everything runs on your computer except the AI you choose. When you talk to it, the
gateway sends your words, a short text description of your game, and the few memories that matter
for that message to that provider. With Ollama nothing leaves your machine. Your voice stays on
your machine with local Whisper, and your memories in `~/.kindred-spirit/memory/` (or on a gateway
you deploy yourself). On Gemini's free tier, Google may use what's sent to improve its products; a paid key, or
Ollama on your own computer, avoids that. Her words come from that AI, and can be wrong.
The bridge listens on 127.0.0.1 only and needs a token. Her dashboard and the Setup's page listen on 127.0.0.1 too,
answer only when opened at your computer's own address (so a website can't reach them by pointing its name at your
computer), and accept changes only from their own page (so another website can't change your settings). The mod talks only to her brain on your computer (and, on LAN, to the host's game), and uses your microphone only while you hold the talk key.

## Helping

Contribute, playtest and send feedback, however you like: any help is appreciated. A few ways in:

- **Play and tell us how it went,** especially on an Intel Mac or with the Setup's first-run warning
  ([what hasn't been tried yet](#what-hasnt-been-tried-yet)). An [issue](https://github.com/PetitPotam/kindred-spirit/issues)
  with the Setup's "Copy a help prompt" text, or the terminal output, helps most.
- **A first contribution:** issues labelled
  [good first issue](https://github.com/PetitPotam/kindred-spirit/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22),
  and small pieces in [docs/GOOD_FIRST_ISSUES.md](docs/GOOD_FIRST_ISSUES.md), each with where to start.
- **Bigger plans** are in the [roadmap](docs/ROADMAP.md) and on the project's issues.

Start with [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

Kindred Spirit stands on the work of many others: [Fabric](https://fabricmc.net),
[whisper.cpp](https://github.com/ggml-org/whisper.cpp) and OpenAI's Whisper,
[Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) via [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx),
[BAAI's bge-small](https://huggingface.co/BAAI/bge-small-en-v1.5) via [fastembed](https://github.com/qdrant/fastembed),
[websockets](https://github.com/python-websockets/websockets), the [Minecraft Wiki](https://minecraft.wiki) contributors
(CC BY-NC-SA 3.0) and [minecraft-data](https://github.com/PrismarineJS/minecraft-data), research on language agents
(Generative Agents, Talker-Reasoner, CoALA, MemGPT, MineCollab and [Mindcraft](https://github.com/mindcraft-bots/mindcraft)),
design notes from [MCPFabric](https://github.com/denfry/mcpfabric), and the idea of a companion who is always there
from [Verity JE](https://www.curseforge.com/minecraft/mc-mods/verity-je). Every library, model, dataset, service
and source, with its licence: **[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)**.

**Made with AI, openly:** this project is written with [Claude Code](https://www.anthropic.com/claude-code)
(Anthropic), mostly by Claude Opus 5.5, directed, playtested and reviewed by its author; Pip's words come
from the AI service you choose (Gemini by default, or another, or a local model), and her slower thinking after a session
can use Claude if you set it up. Details: [how this project was made](THIRD_PARTY_NOTICES.md#how-this-project-was-made-with-ai-openly).

## Licence

Copyright © 2026 PetitPotam ([github.com/PetitPotam](https://github.com/PetitPotam)).

- **The code** is free software under the **[GNU Affero General Public License v3.0](LICENSE)**
  (AGPL-3.0-only): use it, study it, change it and share it; if you share a changed version, or run one
  for others over a network, share its source under the same licence.
- **Additional permission** (AGPL section 7): you may combine Kindred Spirit with Minecraft, the Fabric
  loader and Fabric API, and distribute the result, even though Minecraft itself isn't free software. The
  exact words are in **[NOTICE](NOTICE)**, beside the licence.
- **Pip's name, character and art** have their own, simple rules: anything kind is welcome, nothing
  lewd or hateful. See **[TRADEMARKS.md](TRADEMARKS.md)**.
- **Contributing** needs a signed [Contributor License Agreement](CLA.md); see [CONTRIBUTING.md](CONTRIBUTING.md).

Not an official Minecraft product; not approved by or associated with Mojang or Microsoft.
