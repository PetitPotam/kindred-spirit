# The dashboard: watch what she does, thinks and remembers

`scripts/start.sh` also starts a small dashboard. Open **http://127.0.0.1:11440** in your browser
while you play (or after). It only listens on your computer, only reads, and shows nothing that
isn't already on your computer or behind your gateway.

| Tab | What you see | Where it comes from |
|---|---|---|
| **Live** | her bond and level, her mood score (how good she feels and how stirred up), powers she has discovered and the ones waking up right now (with their favour), standing requests, offers waiting for your yes, the game state she sees, the conversation window and its summary, and exactly what was sent to the AI last: the memories she recalled, her feelings, her settings | the brain writes `logs/brain-state.json` every 2 seconds |
| **Conversation** | everything that happened, newest first: what you said and her answer (mood, gesture), tools she used and what the game answered, things she noticed, lines she said on her own, powers waking up, bond changes, honesty checks, what she learned. Filter by kind or search | `logs/brain.log` |
| **AI calls** | every call to the AI: why (a reply to you, on her own, learning, summarizing), how long it took, tokens sent and back, an estimated cost (today and per call, with a chart), the tools offered, a tool it had to use, special instructions applied. Click a call to see each part of the prompt and the answer | `logs/gateway.jsonl` |
| **Speech & voice** | each time speech-to-text heard you (and what it heard), each voice line, average times, problems | `logs/gateway.log` |
| **Memory** | her memories per world, by kind, with importance, passing feelings and when they fade, what was imported from another world; a search box that shows what would come to her mind for any sentence (the same search she uses); her saved state (bond, conversations) | the gateway's memory API (works with a remote memory too) |
| **Settings** | which AI, speech-to-text, voice, embeddings and memory are in use, the gateway's special instructions (persona, facts, next-reply hint, paused), `brain.toml`, the mod's settings. Keys are never shown, only their names | `gateway.json`, `brain.toml`, `kindredspirit.json` |

Cost estimates use Gemini 3.1 Flash-Lite's list prices ($0.25 per million tokens sent, $1.50 per
million back). For another model, start the dashboard with `KINDRED_PRICE_IN=... KINDRED_PRICE_OUT=...`.
Token counts are recorded from the first gateway start with the dashboard; older calls show "–".

Run it on its own with `brain/.venv/bin/python services/dashboard.py` (standard library only), or on
another port with `KINDRED_DASHBOARD_PORT`.
