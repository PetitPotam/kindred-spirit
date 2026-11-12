# The dashboard: watch what she does, thinks and remembers

`scripts/start.sh` also starts a small dashboard. Open **http://127.0.0.1:11440** in your browser
while you play (or after). It only listens on your computer, only reads (except **Learn this** in the Knowledge tab), and shows nothing that
isn't already on your computer or behind your gateway.

| Tab | What you see | Where it comes from |
|---|---|---|
| **Live** | her bond and level, her mood score (how good she feels and how stirred up), powers she has discovered and the ones waking up right now (with their favour), standing requests, offers waiting for your yes, the game state she sees, the conversation window and its summary, and exactly what was sent to the AI last: the memories she recalled, her feelings, her settings | the brain writes `logs/brain-state.json` every 2 seconds |
| **Conversation** | everything that happened, newest first: what you said and her answer (mood, gesture), tools she used and what the game answered, things she noticed, lines she said on her own, powers waking up, bond changes, honesty checks, what she learned. Filter by kind or search | `logs/brain.log` |
| **AI calls** | every call to the AI: why (a reply to you, on her own, learning, summarizing), how long it took, tokens sent and back, an estimated cost (today and per call, with a chart), the tools offered, a tool it had to use, special instructions applied. Click a call to see each part of the prompt and the answer | `logs/gateway.jsonl` |
| **Speech & voice** | each time speech-to-text heard you (and what it heard), each voice line, average times, problems | `logs/gateway.log` |
| **Memory** | her memories per world, by kind, with importance, passing feelings and when they fade, what was imported from another world; a search box that shows what would come to her mind for any sentence (the same search she uses); her saved state (bond, conversations) | the gateway's memory API (works with a remote memory too) |
| **Knowledge** | what the world remembers (the knowledge base): how many pages and passages from which sources and licenses, its size, whether learning while playing is on; a box to ask any question as the player would and see what she'd be told and whether it counts as known; **Learn this** to make it read the pages that answer a question now; what she learned while you played; the latest pages | the gateway's `/knowledge/` API and the knowledge file (read-only) |
| **Settings** | which AI, speech-to-text, voice, embeddings and memory are in use, the gateway's special instructions (persona, facts, next-reply hint, paused), `brain.toml`, the mod's settings. Keys are never shown, only their names | `gateway.json`, `brain.toml`, `kindredspirit.json` |

Cost estimates use Gemini 3.1 Flash-Lite's list prices ($0.25 per million tokens sent, $1.50 per
million back). For another model, start the dashboard with `KINDRED_PRICE_IN=... KINDRED_PRICE_OUT=...`.
Token counts are recorded from the first gateway start with the dashboard; older calls show "–".

The pages are grouped in a side bar (a top bar on a phone), each with its own address
(`http://127.0.0.1:11440/#settings`), with a light / dark / auto switch. Only pages opened as
`127.0.0.1` or `localhost` are answered, so another web site can't read her token or memories.

Run it on its own with `brain/.venv/bin/python services/dashboard.py` (standard library only), or on
another port with `KINDRED_DASHBOARD_PORT`.

## Sessions

Every play session is recorded in `~/.kindred-spirit/logs/sessions/`: a timeline (`.jsonl`) and,
when you leave, a summary (`.md`) with what stands out (how much she talked, how much on her own,
interruptions, failed tools, slow answers, errors). The **Sessions** tab shows them: what you said,
every line she said (and why: answering you, on her own, on instinct, a warning), lines she held
back, interruptions, tools and their results, heart changes, errors, how long answers took, and,
under each thing you said, *what went to the AI and what came back*. ▶ next to a line says it
again with her current voice (made again from the text; no audio is stored).

## Try Pip (a simulator)

The **Try Pip** tab talks to her brain the way the game does, without Minecraft: type or hold to
talk (your microphone goes through her real speech-to-text), pet her, hit her, and set up a
pretend world (biome, time, weather, health, what you hold, animals, a monster nearby,
underground). Her answers come with her voice. Her tools can pretend to work or fail honestly.
It's its own world (`sim:Playground`), with its own companion and memories. Close the game first:
her brain talks to one game at a time (the simulator, or Minecraft).

## Changing settings

The **Settings** tab can change every setting, each shown with its default (↺ puts one back;
"Reset all to defaults" does them all, then Save):
- **Her brain**: everything in `brain.toml` (her name and personality wishes, her AI, voice, behaviour
  and heart), listed from its defaults so new settings show up on their own. Saved in
  `~/.kindred-spirit/brain-overrides.json` on top of `brain.toml` (which keeps your comments), picked up
  within seconds, no restart. Only the connection settings (server, gateway address) aren't here.
- **The game (mod)**: everything in `kindredspirit.json` (skin, power, style, chat mode, subtitles,
  glow, her liveliness, size and position...), applied within two seconds, even while you play. The
  mod writes its defaults next to it (`kindredspirit.defaults.json`) when it starts.
- **The gateway**: the AI for her conversation and for her deeper thinking, the Gemini model and
  thinking for her replies, her Kokoro voice, speed and pitch, and speech-to-text, for the next call.

Numbers have sliders, her skin is picked from the skins there are (the mod's and yours), her Kokoro
voice and the Gemini model come with suggestions (a voice can also be a blend like
`bf_lily*0.7+bf_emma*0.3`). Types and choices are checked; changes are accepted only from the
dashboard's own page.

**Profiles** keep whole sets of settings to switch between and compare: "Save current as" (e.g.
"calm Pip", "chaotic Pip"), "Use" applies one (only what differs changes), and "Compare" shows a
table of the differences between two profiles, your current settings, or the defaults. They're
kept in `~/.kindred-spirit/profiles/`.
