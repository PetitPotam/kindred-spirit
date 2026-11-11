<div align="center">
  <img src="mod/src/main/resources/assets/kindredspirit/icon.png" width="112" alt="Pip, a green slime ball with a smile">

# Kindred Spirit

**A cute AI companion for Minecraft Java that floats beside you, talks with you by voice, and never touches your world.**

Minecraft 1.21.1 · Fabric · MIT · early preview

<!-- DEMO GIF: record ~15 s (talk to it, it answers; a creeper sneaks up; it warns you), save as docs/demo.gif -->
<img src="docs/demo.gif" width="720" alt="Demo: talking to Pip, then Pip warning about a creeper">
</div>

Kindred Spirit is a little slime spirit (we call ours Pip) who keeps you company while you play.
Hold **V** and talk to it: it hears you, looks at your game (health, inventory, biome, time, what
you're looking at, monsters around you) and answers out loud. It also speaks up by itself when a
creeper sneaks behind you or your hearts run low.

- **Your world stays yours.** The mod is client-side only: no new blocks, items or mobs, nothing
  saved in your world. Add or remove it any time.
- **Bring your own AI.** One OpenAI-compatible address: Gemini by default; the gateway also has
  presets for Ollama, Groq, OpenAI, OpenRouter and Mistral (only Gemini is tested so far).
  Speech-to-text and voice run **locally**.
- **Light on your computer.** It adapts to your frame rate and hardware (see [Performance](#performance)).
- **Made to be hacked on.** The mod is thin; the personality lives in a small Python "brain".

## Where it comes from

Kindred Spirit was inspired by [Verity JE](https://www.curseforge.com/minecraft/mc-mods/verity-je), a mod
with an AI companion who lives in your world. I didn't care about its horror or its story. What
stayed with me was the idea of a companion that is **present**: it sees what you're doing, talks
with you, and keeps you company while you play. Kindred Spirit keeps only that idea and makes it
cozy and configurable. It isn't a fork: none of Verity's code or assets are used, and it's written
from scratch for Fabric.

> **Status: 0.1 preview.** It's playable and fun, but small. We're looking for contributors:
> see [what to build next](#help-wanted) and the [design](docs/DESIGN.md).

## What works today

| | |
|---|---|
| A slime ball drawn beside you | bounces and squishes, blinks, color follows its mood, mouth moves with its voice |
| Voice chat | hold **V**, speak, release; local Whisper hears you, local Kokoro answers |
| Typed chat | `/kindred <message>` (or `/ks`) |
| It understands your game | health, hunger, armor, effects, inventory, position, biome, time, weather, what you look at, nearby hostile mobs with direction |
| Danger warnings | creeper within 8 blocks, health at 3 hearts or less: instant subtitle, voice right after, with cooldowns |
| Personality | greets you, small talk when it's been quiet a while (configurable), moods |
| Subtitles | above the slime, optional captions and a log in your chat (only on your screen) |
| It feels alive | looks where you look, looks back when you look at it, wanders around you when you stand still, dozes after a long quiet time, leans as it floats, blinks, its eyes move before its head |
| You can direct it | say or type "stay here", "come here", "follow me", "look at me", "do a spin"; pet it by sneaking while looking at it |
| Skins | a slime, a soft cube, a fairy and a pixie with fluttering wings, a glowing wisp, a strawberry, a starry orb, or your own PNG ([how](docs/SKINS.md)) |

Not yet: actions in the world (giving items, lighting, finding structures), memory, the settings
screen, star and robot shapes. That's the [roadmap](docs/ROADMAP.md).

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
Minecraft 1.21.1 + Fabric
  └─ Kindred Spirit mod (Java, client only): draws the slime, reads game state, mic and speaker
        │  WebSocket on 127.0.0.1:47811, with a token from ~/.kindred-spirit/token
  Kindred brain (Python): conversation, moods, danger rules, voice
        ├─ speech cleaner :8090 → whisper.cpp :8083      (you → text, local)
        ├─ Kokoro :8885                                  (text → voice, local)
        └─ Kindred gateway :11437 → Gemini / Ollama / …   (the AI)
```

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

## Setup (macOS, about 10 minutes)

You need: Minecraft Java Edition, [Homebrew](https://brew.sh), and a
[Gemini API key](https://aistudio.google.com/apikey) (there is a free tier). Fully local with
[Ollama](https://ollama.com) should work through the gateway but hasn't been tested yet.

```bash
brew install openjdk@25 python@3.12 whisper-cpp
git clone https://github.com/PetitPotam/kindred-spirit.git && cd kindred-spirit
scripts/setup.sh                 # brain, local voice and speech-to-text (~700 MB download)
open -e ~/.kindred-spirit/secrets.env   # paste your key after GEMINI_API_KEY=
(cd mod && ./gradlew build)      # builds the mod
python3 scripts/install_profile.py      # quit the Minecraft Launcher first
```

`install_profile.py` adds a **Kindred Spirit (Fabric 1.21.1)** profile with its **own game folder**
(`minecraft-kindred`), installs Fabric Loader and Fabric API, and backs up your launcher profiles.
Your other profiles, mods and worlds are untouched.

Then play: double-click **`scripts/play-mac.command`**. It starts everything and opens the launcher
**from Terminal**, which matters on macOS: the launcher has no microphone permission of its own,
so started from the Dock the game records silence. Pick the Kindred Spirit profile and press Play.

**Linux:** the scripts are written to work there (`whisper-server` from [whisper.cpp](https://github.com/ggml-org/whisper.cpp)) but haven't been tried yet.
**Windows:** not tested yet. The Python parts are cross-platform, but the start scripts are bash;
a PowerShell version is a [good first issue](docs/GOOD_FIRST_ISSUES.md).

### Controls

| | |
|---|---|
| **V** (hold) | talk; release to send (change it in Controls → Kindred Spirit) |
| `/kindred <text>` or `/ks <text>` | type to it |
| `/kindred status` | brain connection, skin, mode, quality level, mood |
| `/kindred reconnect` | after restarting the brain |
| `/kindred skin <name>` · `/kindred skins` · `/kindred skins reload` | change its look, list skins, reload your skins folder |
| `/kindred mode follow\|stay\|come` | follow you (default), wait here, come close for a moment |
| `/kindred side left\|right\|above\|auto` | which side it floats on |
| `/kindred look me\|there\|ahead\|up\|down\|around` | where to look for a few seconds |
| `/kindred emote <name>` | nod, shake, spin, hop, wiggle, happy, shy, think, doze |
| `/kindred life` · `/kindred life <name> <value>` · `/kindred life reset` | its liveliness switches (see above) |
| sneak while looking at it | pet it |

Talking works too: "stay here", "come here", "follow me", "go to my left", "look at me", "look at that",
"do a spin", "dance". It acts at once, before the AI answers.

## Settings

- **Brain:** `~/.kindred-spirit/brain.toml` (name, personality, model, voice, chattiness, alerts).
- **Mod:** `minecraft-kindred/config/kindredspirit.json` (skin, quality, subtitles, captions, position, size,
  volume, and the liveliness switches under `"life"`).
- **AI provider:** the gateway, live, no restart:
  ```bash
  python3 services/kindred_gateway.py upstream ollama     # or gemini, groq, openai, openrouter, mistral
  python3 services/kindred_gateway.py persona "Speaks like a pirate."
  python3 services/kindred_gateway.py log                 # what it asked and answered
  ```
  Keys go in `~/.kindred-spirit/secrets.env` (readable only by you).
- Voices: `tts_voice` in brain.toml, e.g. `af_heart`, `af_bella`, `am_puck`, `bf_emma` (54 Kokoro voices).
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
3. **A sandbox Minecraft:** `cd mod && ./gradlew runClient -PdevScript=devscripts/smoke-test.txt` starts a
   throwaway dev game (its own folder, `mod/run`), creates a test world, talks to the companion,
   spawns a frozen creeper behind you, drops your health and takes screenshots in `mod/run/screenshots`.
   `devscripts/life-test.txt` does the same for its liveliness and every skin (eye contact, petting,
   gestures, stay and come, watching a creeper).

Only then install into your launcher.

## Privacy

Everything runs on your computer except the AI you choose. When you talk to it, the gateway sends
your words and a short text description of your game (the snapshot above) to that provider. With
Ollama nothing leaves your machine. Your voice never leaves your machine (local Whisper).
The bridge listens on 127.0.0.1 only and needs a token.

## Help wanted

Ideas sized for a first contribution are in **[docs/GOOD_FIRST_ISSUES.md](docs/GOOD_FIRST_ISSUES.md)**
(a settings screen, a PowerShell start script, more danger alerts, other shapes, a name tag, a
wake word...). Bigger plans are in the [roadmap](docs/ROADMAP.md). Start with
[CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

[Fabric](https://fabricmc.net) · [whisper.cpp](https://github.com/ggml-org/whisper.cpp) ·
[Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) via [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) ·
[websockets](https://github.com/python-websockets/websockets) · design notes from [MCPFabric](https://github.com/denfry/mcpfabric) ·
the idea of a companion that is always there, from [Verity JE](https://www.curseforge.com/minecraft/mc-mods/verity-je).

MIT licensed. Not an official Minecraft product; not approved by or associated with Mojang or Microsoft.
