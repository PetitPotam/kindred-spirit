# The gateway: choose your AI, voice, speech-to-text and memory

Kindred talks to the outside world through **one address**, the Kindred gateway
(`services/kindred_gateway.py`, `http://127.0.0.1:11437/v1`). Behind it, each part can be a free
tool on your computer or a service you already use, and you can switch any of them in one command,
without restarting the game.

| Part | What it does | Default (free, on your computer) | Other choices |
|---|---|---|---|
| **AI** | thinks and talks | Gemini (needs a key, has a free tier) | Claude (with your own Claude subscription through the Claude CLI, or an API key), Ollama (local), Groq, OpenAI, OpenRouter, Mistral, any OpenAI-compatible server |
| **Speech-to-text** | hears you | Whisper (whisper.cpp, on your GPU) | Groq, OpenAI, any OpenAI-compatible server |
| **Voice** | speaks | Kokoro | OpenAI, any OpenAI-compatible server that returns WAV |
| **Embeddings** | understands what memories mean | a small local model (bge-small, 65 MB) | Gemini, Ollama, OpenAI, or none (keyword search only) |
| **Memory** | stores what it remembers | a SQLite file on your computer | a gateway you deployed somewhere else |

You set it up once; the brain and the mod never need to know which you chose.

## Quick start

```bash
scripts/setup.sh            # a guide: pick each part from what you have, then it tests everything
```

The guide writes the same settings as the commands below, so you can use either. To change one part
later, run the guide again (`brain/.venv/bin/python scripts/guide.py`) or use `$G use ...`.

At the end it runs `check` (also `brain/.venv/bin/python services/kindred_gateway.py check`), which
tests every part the way the brain uses it (parts you turned off show as "off, by your choice"):

```
ok   AI           Hello there, friend!
ok   voice        68 KB of WAV
ok   speech->text heard: 'Testing 1, 2, 3.'
ok   embeddings   384 numbers per text
ok   memory       stored, found and removed a test memory
```

`status` shows what each part uses and the other options.

## Switching

```bash
G="brain/.venv/bin/python services/kindred_gateway.py"
$G use ai ollama              # AI: gemini, claude, anthropic, groq, ollama, openai, openrouter, mistral
$G use stt groq               # speech-to-text: local_whisper, groq, openai
$G use tts openai             # voice: local_kokoro, openai
$G use embeddings gemini      # embeddings: local, gemini, ollama, openai, none
$G use memory remote          # memory: local, remote
$G voice am_puck              # the voice of the current voice provider
$G model gemini-3.1-flash-lite   # override the AI model (--clear to undo)
```

Changes apply on the next request. If you switch a part away from a local tool, `scripts/start.sh`
stops starting that tool, so it costs nothing.

## Claude

Two ways, each with your own account:

**`claude`: your Claude subscription, through the Claude CLI on your computer.** If you have
Claude Code installed and logged in (run `claude` once and `/login`), `$G use ai claude` makes Pip
think with Claude, counted in your own plan's usage limits like your other Claude Code use. It's
for your own play on your own computer: the gateway runs the `claude` command you're logged in
with; nothing is shared.

- Each kind of call can use its own model and effort. The default is Haiku at low effort for
  everything she says (the fastest), and Sonnet at medium effort for learning from what happened
  (not time-critical; quality matters more). Change them in `gateway.json`:
  ```json
  "upstreams": {"claude": {"model": "haiku", "effort": "low",
                           "by_kind": {"reflect": {"model": "sonnet", "effort": "medium"},
                                       "fold": {"model": "haiku"}, "own": {"model": "haiku"}}}}
  ```
  Kinds: `reply` (answering you), `own` (things she says on her own), `reflect` (learning),
  `fold` (summarizing older conversation). Efforts: low, medium, high.
- It starts the CLI for each answer (about a second) in an empty folder, with its own tools, MCP
  servers and saved sessions turned off; her tools (find, guide, protect...) come back as structured
  answers. Expect about 2 to 3 seconds per reply, a bit slower than Gemini.
- If the login expires, the game shows "AI gateway problem: ... run claude in a terminal and /login".

**`anthropic`: the Claude API with a key** (pay per use): put `ANTHROPIC_API_KEY=...` in
`secrets.env`, then `$G use ai anthropic`. It uses Anthropic's OpenAI-compatible endpoint, Haiku by
default (`$G model claude-sonnet-5-5` for another). Not tested with Kindred's tools yet; reports welcome.

### Any AI you already pay for, through its command-line tool

You don't need to buy API credits if you already have an AI subscription with a command-line tool
on your computer: the `cli` provider type runs any of them, from a template in `gateway.json`. For
example (these flags are from each tool's documentation and haven't been tried with Kindred yet:
check them against `--help` for your version):

```json
"upstreams": {
  "codex":  {"type": "cli", "command": "codex", "args": ["exec", "--model", "{model}", "{prompt}"]},
  "gemini_cli": {"type": "cli", "command": "gemini", "args": ["--model", "{model}", "-p", "{prompt}"]},
  "cursor": {"type": "cli", "command": "cursor-agent", "args": ["-p", "--model", "{model}", "{prompt}"]}
}
```

then `$G use ai codex` (or the name you chose). Placeholders: `{model}` and `{effort}` (left out with
their flag when empty), `{system}` (her personality and rules; without it they go at the start of
the prompt) and `{prompt}` (without it, the prompt goes to the tool's standard input). Add
`"output": "json", "result_field": "result"` for tools that answer in JSON. Her tools (find,
guide, protect...) are asked for as a JSON answer and read back from it. Each call starts the tool,
so expect a few seconds per reply, and it counts against that subscription's own usage limits.

### A different AI for each kind of call

Each kind of call can go to another AI entirely: for example Gemini for her quick replies and your
Claude subscription for learning, where quality matters more than speed:

```bash
$G use ai gemini                     # the main AI: answering you, things she says on her own
$G use ai claude --for reflect       # learning from what happened
$G use ai --for reflect --clear      # back to the main AI
```

Kinds: `reply` (answering you), `own` (things she says on her own), `reflect` (learning), `fold`
(summarizing older conversation). The dashboard shows which AI answered each call.

Within one provider, `by_kind` can also change the model and, for thinking models, how much it thinks
(`reasoning_effort`). The recommended Gemini setup puts her conversation on Gemini 3 Flash kept quick, and
summaries on Flash-Lite:

```json
"gemini": {"model": "gemini-3.1-flash-lite",
           "by_kind": {"reply": {"model": "gemini-3-flash-preview", "reasoning_effort": "minimal"},
                       "own":   {"model": "gemini-3-flash-preview", "reasoning_effort": "minimal"}}}
```

Without `"minimal"`, a thinking model can spend her whole answer budget thinking and get cut off. A model or
thinking level set by hand (`$G model ...`) still wins.

## Special instructions

The gateway can steer the AI without touching the brain, from the game or the terminal:

| In game | Terminal (`$G ...`) | What it does |
|---|---|---|
| `/kindred persona Speaks like a pirate.` | `persona "..."` | standing rules for how she behaves and speaks (`clear` / `--clear` removes) |
| `/kindred fact The base is at the lake.` | `fact "..."` | facts she knows to be true (add several; `clear` removes all) |
| `/kindred hint Tease them about the creeper.` | `hint "..."` | for her next reply only |
| `/kindred model gemini-3.1-flash` | `model ...` | use another model of the same provider |
| `/kindred pause` / `resume` | `pause` / `resume` | send requests through untouched, or apply the instructions again |
| `/kindred instructions` | `status` | what's set right now |

The dashboard ([DASHBOARD.md](DASHBOARD.md)) shows them, and which AI calls they were applied to.

## Her voice

With the local voice (Kokoro), Pip's voice is `bf_lily`, a British voice, slightly faster and higher
than normal so she sounds bright and lively (chosen from an audition of the local and cloud voices;
see the roadmap for the expressive voices tried and postponed). Each sentence is said a little
differently (speed and pitch vary), and the sounds that don't speak well ("hm", "pff", "tsk") are left
to her gestures instead of her voice. Each line is said in a
style that follows her mood: **excited** (faster), **calm**, **sad** (slower, softer), and
**whisper** (quieter, breathier) for secrets, spooky things and what she senses in the dark.

All of it is in `~/.kindred-spirit/gateway.json`, under `tts.providers.local_kokoro`:

```json
"voice": "bf_lily", "speed": 1.12, "pitch": 1.1,
"styles": {"excited": {"speed": 1.28, "pitch": 1.16}, "calm": {"speed": 1.08}, "sad": {"speed": 1.0, "pitch": 1.06},
           "whisper": {"voice": "bf_lily", "speed": 1.0, "gain": 0.5}}
```

- `voice`: one of Kokoro's 54 voices (`af_heart`, `af_bella`, `bf_emma`, `am_puck`...) or a blend,
  `name*weight+name*weight`. `$G voice af_heart` switches it.
- `pitch` (1.0 = natural, 1.08 = a bit younger), `speed`, `gain` (loudness, for the whisper).
- A style only lists what it changes. Any voice provider can have its own `styles` with the same
  names (for OpenAI, say, a different `voice` or `speed` per mood); without them, every line uses the
  provider's normal voice.

Her slow thinking can also be switched **off** (the Setup's "Her slow thinking" step does it): an upstream
`{"type": "off"}` for the kind `reflect` answers at once that it's off, and her brain carries on without learning.

## Keys

Keys go in `~/.kindred-spirit/secrets.env` (readable only by you, never in the repository):

```
GEMINI_API_KEY=...
GROQ_API_KEY=...
OPENAI_API_KEY=...
```

In `gateway.json`, a provider's `"key": "env:GEMINI_API_KEY"` means "read it from there".

## Recipes

**Everything on your computer (free, private, works offline).** Needs [Ollama](https://ollama.com)
and a model that's good at short, friendly answers and tool calls:

```bash
ollama pull qwen3.5:4b
$G use ai ollama
```

Speech-to-text, voice, embeddings and memory are already local. (Not tested with Kindred's tools
yet; reports welcome.)

**The default: Gemini for the AI, the rest local.** Fast (~1 s replies), cheap, with a free tier.
Get a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).

**A computer that struggles.** Keep the AI in the cloud and move speech too:

```bash
$G use stt groq        # free tier at console.groq.com
$G use embeddings gemini
```

**All cloud (nothing heavy on your computer).** `use ai openai`, `use stt openai`,
`use tts openai`, `use embeddings openai`, with `OPENAI_API_KEY`.

## Adding a provider

Any OpenAI-compatible service works. Add it to `~/.kindred-spirit/gateway.json`, for example a
second voice server:

```json
"tts": {"providers": {"my_voice": {"url": "http://192.168.1.20:8880/v1/audio/speech", "model": "kokoro", "voice": "bf_emma"}}}
```

then `$G use tts my_voice`. For the AI, add an entry to `"upstreams"` with `base`, `key` and `model`.

## Deploying the gateway (shared or remote memory)

The gateway is one Python file with no required dependencies, so it can run on a home server, a
Raspberry Pi, or a small cloud machine. That lets your companion's memory live in one place for
all your computers, or lets you keep the AI keys off your gaming PC.

On the server:

```bash
echo "KINDRED_GATEWAY_KEY=$(openssl rand -hex 24)" >> ~/.kindred-spirit/secrets.env
# in ~/.kindred-spirit/gateway.json:  "access_key": "env:KINDRED_GATEWAY_KEY"
KINDRED_GATEWAY_HOST=0.0.0.0 python3 services/kindred_gateway.py serve
```

Put it behind HTTPS (a reverse proxy like Caddy) if it's reachable from the internet. It refuses
requests without the key, and warns if you open it to the network without one.

On your own computer (the default, listening on 127.0.0.1) it also refuses requests sent by a web page
on another site (an `Origin` that isn't 127.0.0.1 or localhost) and requests whose `Host` isn't this
computer: a page you visit can't rewrite her persona, delete her memories or spend your AI credits.
Scripts and the brain (no `Origin`) and the dashboard (a local page) are fine.

Then on your gaming computer, either:

- **Only memory remote:** in the local `gateway.json`, set
  `"memory": {"use": "remote", "providers": {"remote": {"base": "https://your-server/v1", "key": "env:KINDRED_REMOTE_KEY"}}}`
  and put the key in `secrets.env` as `KINDRED_REMOTE_KEY`.
- **Everything remote:** in `~/.kindred-spirit/brain.toml`, set `[gateway] url = "https://your-server/v1"`
  and `key = "..."`. (Speech-to-text and voice then also run on the server.)

## Troubleshooting

| Symptom | What to do |
|---|---|
| `FAIL AI ... 401/403` | the key is missing or wrong in `secrets.env`; `status` shows which provider is used |
| `FAIL voice` | is the voice tool running? `scripts/start.sh` says; logs in `~/.kindred-spirit/logs/` |
| `FAIL speech->text` | the same for Whisper; on macOS, start the Minecraft Launcher from Terminal for the microphone |
| `FAIL embeddings` | memory still works with keyword search; `$G use embeddings none` silences it |
| Pip is slow to answer | `kindred_gateway.py log` shows how long each AI reply took |

Logs: `~/.kindred-spirit/logs/gateway.log` (every request, briefly) and `gateway.jsonl` (AI exchanges).
