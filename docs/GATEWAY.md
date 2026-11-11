# The gateway: choose your AI, voice, speech-to-text and memory

Kindred talks to the outside world through **one address**, the Kindred gateway
(`services/kindred_gateway.py`, `http://127.0.0.1:11437/v1`). Behind it, each part can be a free
tool on your computer or a service you already use, and you can switch any of them in one command,
without restarting the game.

| Part | What it does | Default (free, on your computer) | Other choices |
|---|---|---|---|
| **AI** | thinks and talks | Gemini (needs a key, has a free tier) | Ollama (local), Groq, OpenAI, OpenRouter, Mistral, any OpenAI-compatible server |
| **Speech-to-text** | hears you | Whisper (whisper.cpp, on your GPU) | Groq, OpenAI, any OpenAI-compatible server |
| **Voice** | speaks | Kokoro | OpenAI, any OpenAI-compatible server that returns WAV |
| **Embeddings** | understands what memories mean | a small local model (bge-small, 65 MB) | Gemini, Ollama, OpenAI, or none (keyword search only) |
| **Memory** | stores what it remembers | a SQLite file on your computer | a gateway you deployed somewhere else |

You set it up once; the brain and the mod never need to know which you chose.

## Quick start

```bash
scripts/setup.sh            # installs the local tools (Whisper, Kokoro, embeddings)
open -e ~/.kindred-spirit/secrets.env    # paste the keys you use, e.g. GEMINI_API_KEY=...
scripts/start.sh --background
brain/.venv/bin/python services/kindred_gateway.py check
```

`check` tests every part the way the brain uses it:

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
$G use ai ollama              # AI: gemini, groq, ollama, openai, openrouter, mistral
$G use stt groq               # speech-to-text: local_whisper, groq, openai
$G use tts openai             # voice: local_kokoro, openai
$G use embeddings gemini      # embeddings: local, gemini, ollama, openai, none
$G use memory remote          # memory: local, remote
$G voice am_puck              # the voice of the current voice provider
$G model gemini-3.1-flash-lite   # override the AI model (--clear to undo)
```

Changes apply on the next request. If you switch a part away from a local tool, `scripts/start.sh`
stops starting that tool, so it costs nothing.

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
