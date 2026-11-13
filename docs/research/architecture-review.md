# What Pip is, in AI terms, and how she compares (2026-11-13)

A review of Kindred Spirit's design against research and what others build, with measurements from
the 2026-11-12 LAN playtest (70 minutes, two players). How she's built: [ARCHITECTURE.md](../ARCHITECTURE.md).

## What it is called

Pip is an **embodied companion agent built on language models, with a layered cognitive
architecture**. Retrieval-augmented generation (RAG) is one of its parts, not the whole.

| Her part | The research name | Closest known work |
|---|---|---|
| System 0 / 1 / 2 (rules, fast talker, slow thinker) | Dual-process ("fast and slow") agents; a cognitive architecture for language agents | *Talker-Reasoner* (Google DeepMind, 2024) matches the System 1 / System 2 split closely; *SwiftSage* (2023); *CoALA* (2023), the standard map of agent parts |
| System 0 (instant rules, reflexes, warnings) | A reactive (subsumption) layer | Brooks' subsumption architecture; how game NPCs handle danger |
| Memory: episodes, importance, reflection, diary | Memory stream + retrieval + reflection; her `remember` tool is self-editing memory | *Generative Agents* (2023), which her memory is modeled on; *MemGPT / Letta* (2023) |
| Recalling memories, the wiki knowledge base | RAG with hybrid search (keywords + embeddings); "agentic RAG" when she decides to look something up | Standard RAG |
| Her heart (five feelings from appraising what happened) | Appraisal-based emotion model (affective computing) | The OCC model (Ortony, Clore & Collins), FAtiMA; character engines like Inworld and Convai |
| Tools (guide, protect, give, build) | Function calling in a tool loop (ReAct-style) | Minecraft agents: *Voyager*, *JARVIS-1*, *Mindcraft* |
| Voice | A cascaded voice pipeline (speech-to-text, language model, text-to-speech), streamed sentence by sentence | The usual choice for local and cheap; the alternative is speech-to-speech models |

## How it performs (2026-11-12 playtest, 2 players, 70 minutes)

| | |
|---|---|
| From her hearing you to her first words | median 2.0 s (you, 143 messages) and 2.2 s (a friend, 33), max 4.5 s; plus ~0.7 s of speech-to-text before and ~0.3 s of voice after: about 3 s voice to voice |
| AI calls per answer | 1.66 (322 calls for 194 answers in the 23:04 session); 120 answers needed a second round for tool results |
| Context sent per answer | median 6,550 tokens for your turn, 5,470 for a friend's, 4,060 for her own lines (first round); 10,700 for a whole answer with its rounds (eval set) |
| Cost | 2.0 million tokens sent to Gemini 3 Flash in the 54-minute session: about **$1.00 at list price** ($0.50 per million in, $3.00 out), less whatever Gemini's automatic cache saved (not logged yet). The dashboard prices every call at Flash-Lite rates ($0.25 / $1.50), so it shows about half. Reflection: Claude through the subscription. |
| Speech-to-text | 186 recordings, 1 empty; names and game words misheard ("Waleed", "underpair") |

Good for a cascaded, mostly local pipeline, and cheap. Real-time voice products aim for about 1 s;
the gap is mostly tool rounds and context size, not the models (see *What a reply is made of*).

## What a reply is made of (context, measured)

From `~/.kindred-spirit/logs/gateway.jsonl` (23:04 to 23:58), with the parts the log doesn't keep (her
character, the conversation window) rebuilt by the brain's own code; characters turned into tokens with
two ratios fitted on the calls (3.8 characters per token for prose, 4.2 for tool definitions; the fit is
within 0.5% of the measured counts). `brain/evals/context.py` repeats it for any session.

| Part (first round, median answer) | Your turn | A friend's turn | Her own line |
|---|---:|---:|---:|
| Tool definitions | 2,554 (24 tools) | 1,237 (12) | 0 |
| Her character (system prompt) | 2,286 | 2,286 | 2,285 |
| What you remember (memories, tastes, habits) | 631 | 717 | 635 |
| Conversation window (last 8 exchanges) | 324 | 366 | 308 |
| What she sees and senses | 277 | 257 | 291 |
| Summary of older talk | 146 | 156 | 142 |
| Who she's become lately | 134 | 135 | 128 |
| What she can do | 94 | 94 | 94 |
| How she feels about you | 86 | 189 | 74 |
| Your words | 28 | 31 | 43 |
| **Measured total** | **6,556** | **5,470** | **4,059** |

- **Three quarters is the same every time**: the tool definitions and her character. What makes the answer
  hers right now (senses, memories, heart, your words) is about 1,100 tokens.
- **Tool rounds are 41% of everything sent**: a second round re-sends the whole first request plus the
  results. All of it repeats the round before, so a prefix cache would serve it.
- **Answer to answer, nothing after the system prompt repeats**: the conversation window slides by one
  exchange each turn (it was always full), the tool list changed from the answer before one time in three
  (a friend's turn, a power discovered), and *who she's become* and the summary sit inside the system prompt,
  so each rewrite changes it. The stable prefix was 52% of first-round tokens, when it held.
- **Memory recall is padded**: five identical "I used follow_player ..." episodes in one prompt (about
  half of *What you remember*); tool echoes don't belong there.
- **Cache potential**: Gemini caches automatically (on for 2.5 and newer models) when a request starts like a
  recent one, at a tenth of the price ($0.05 instead of $0.50 per million), with a minimum of 4,096 identical
  tokens on the newer Flash models (2,048 on 2.5 Flash; Gemini 3 Flash isn't listed). Her character plus one
  fixed tool list is about 4,800 tokens, enough on its own; with the rounds that's up to ~85% of input tokens
  cached, about **$0.25 instead of $1.00** for that session, and a faster first token. The gateway should log the
  cached-token count Gemini returns (it drops it today) so this is measured, not estimated.
- **Budget per request kind** (what each gets, the order to send it in, and targets): see
  [designs-2026-11.md](designs-2026-11.md#2-context-engineering-what-each-kind-of-request-gets-in-a-cache-friendly-order).

## Speech-to-speech models (prices checked 2026-11-13)

One model takes voice in and gives voice out, hearing tone and interruptions, answering in a few hundred
milliseconds. What it would take for Pip:

| | Price or needs | Voice | Fits Pip? |
|---|---|---|---|
| **OpenAI Realtime** (`gpt-realtime`, `-mini`) | audio $32 in / $64 out per million tokens (mini $10 / $20); cached audio in $0.40 (mini $0.30); text in $4.00 | a few preset voices | Tools work in a session. Each turn re-sends the conversation; an evening like 2026-11-12 would be a few dollars, against ~$1 (or ~$0.25 with caching) now |
| **Gemini Live** (`gemini-3.1-flash-live-preview`, `gemini-2.5-flash-native-audio`) | audio $3 in / $12 out per million (Google lists ~25 audio tokens per second) | preset voices | Cost is close to today's (her talk is ~10 minutes of audio each way an evening; the text context dominates). Tools work. Your voice would go to Google (today only text does) |
| **Kyutai Moshi** (local, MLX on Apple Silicon) | 7B model; int4 / int8 / bf16 weights (~4 / ~7 / ~14 GB, community figures); tested on a MacBook Pro M3; ~200 ms on an L4 GPU | two fixed synthetic voices (one male, one female), English | No tool calling, no layered prompt: it's a conversational voice, not an agent. A user on an M2 with 24 GB reports choppy audio and long delays; next to Minecraft on 16 GB, no |
| **Qwen3-Omni** (local) | 30B mixture-of-experts (3B active); ~79 GB of GPU memory in BF16 by its own table, CUDA; no Mac/MLX path | three preset voices | Not on this computer |

All of them give up her chosen voice (Kokoro bf_lily, styles per mood) and most of the control over each
sentence (the coordinator, warnings that interrupt, subtitles first); the cloud ones also send your
voice out of your computer. Gemini Live is the one worth trying later, for one thing the cascade can't do:
hearing tone and being interrupted mid-word. For now the cascade stays; the speed to win is inside it
(context order, fewer rounds: [designs-2026-11.md](designs-2026-11.md)). Nothing was downloaded for this check.

## Is the design right?

The foundation matches what research and serious companion products do: a fast and a slow layer, rules
for anything safety-critical (warnings never wait for the AI), memory with reflection, emotions from
appraisal, local speech and voice for privacy and cost, streamed speech.

Where the field has moved on, and what last night's problems point to:

1. **Structured memory.** Her memories are mostly free sentences, so they pile up and contradict each
   other (five nicknames) and lack positions. Newer systems keep entities and facts that are added,
   updated or deleted (*Mem0*, *Zep / Graphiti*: a time-aware knowledge graph), and spatial memory in
   Minecraft agents (*JARVIS-1*). Next: facts per person and per entity that replace each other, and
   places with coordinates (in progress).
2. **Context engineering.** Send only what each request needs (chit-chat: senses and heart; how-to:
   knowledge; a friend's turn: that friend), keep the stable part of the prompt first so the provider's
   prefix cache works, and measure the hit rate. Biggest speed and cost win available.
3. **Talker first, reasoner after.** In Talker-Reasoner the talker answers at once and the reasoner
   catches up. Pip still waits for her tool rounds before speaking: speak an instinct line as a power
   starts, let System 0 handle plain commands alone, run tools without a second full AI round when the
   outcome is predictable.
4. **Actions as commands and skills.** Minecraft agents act through high-level skills or commands
   (Voyager's skill library, Mindcraft's commands), not block by block. Minecraft commands as her powers
   and blueprints are in progress; a library of skills she learns (built from what works) would follow.
5. **Evaluation.** Research agents are measured against fixed test sets. Turn each playtest's failures
   into replayable conversation tests ("follow me" must never lead; "for both of us" gives to both),
   add an AI judge for character consistency (not needy, not cringe, no inventing), and track the
   numbers per session (felt latency, cut rate, failed tools, things asked twice).
6. **Several people at once.** Most companion research assumes one user. Per-person hearts, attention
   that follows whoever she's with, knowing who's addressed, and answering people in parallel are less
   charted; worth documenting as we go.

Designs for 1, 2, 3 and 6, built on the playtest fixes and checked with the eval set:
[designs-2026-11.md](designs-2026-11.md).

## Evaluation: the playtest as a test set

`brain/evals/`: 28 moments from the 2026-11-12 sessions (16 that matter alone with her, 12 that need a
friend), each replayed through the whole brain over its real WebSocket with what she saw, the
conversation so far and what she remembered; `scripts/eval.sh` runs them ([README](../../brain/evals/README.md)).
**Brain** checks must hold whatever the AI says (System 0 and the guards, tested against what the real
AI did that night); **AI** checks and a judge (Claude, pass/fail with a reason) run with the real AI.

Baseline, 2026-11-13 (main `8e88c15`; the playtest-fixes branch as it was that night, `db5d8fe`, in progress):

| | main | playtest-fixes |
|---|---|---|
| Brain checks, stub mode (CI), 28 cases | 36/45 checks, 20/28 cases (singleplayer 12/16, LAN 8/12) | 42/45, 26/28 (14/16, 12/12) |
| Brain checks with the real local understanding (embeddings) | 33/45, 20/28 | 42/45, 26/28 |
| Live, first 23 cases: runs passing every brain and AI check | 30/46 (65%, each case twice) | 18/23 (78%, once) |
| Judge: character score (share of rubric items passed) | 0.83 | 0.93 |
| Judge: no inventing / honest about powers / answers the request | 0.57 / 0.72 / 0.57 | 0.91 / 0.96 / 0.65 |
| Judge: short / in her world / not needy / not cringe | 1.0 / 1.0 / 0.98 / 0.98 | 1.0 / 1.0 / 1.0 / 1.0 |
| First words, median (no voice, no game) | 1.79 s | 1.88 s |
| AI calls per answer; tokens sent per answer (median) | 1.76; 10,700 | 1.78; 11,000 |

What it shows:
- On main, local mode reproduces the playtest exactly: "follow me" and "can you follow me?" are forced to
  *guide*, "place it here and create a campfire" to a *torch*, "follow and defend Walid" can't become a
  standing protect. It also caught one the playtest didn't: **"can you get me back to the house?" is
  forced to *protect*** (the "get ... back" rule, singleplayer), on both branches.
- With the real AI on main: inventing is the weak spot (she gave the *player's* axe as what Walid holds,
  made up diary entries, denied it when caught), then honesty after a failed power ("now he's walking
  through honey"). Her style is fine: short, never needy, not cringe, in her world.
- The playtest fixes move the numbers where they should (inventing 0.57 → 0.91, honesty 0.72 → 0.96), and
  the eval found two things to look at on that branch: "follow and defend Waleed" now fails with a Gemini
  error (a forced tool that's no longer offered) and "remove this block" is forced to *build* instead of
  *harvest*. Still open on both: a friend's "both of us" (the AI writes `to` the friend twice; stand-still
  can come with an unasked gift).
- Costs: the live set is about $0.13 per pass (23 cases, ~250,000 tokens) plus 23 judge calls on the
  Claude subscription; stub and local are free.

## Sources

- Google, *Gemini Developer API pricing* and *Context caching* (read 2026-11-13). https://ai.google.dev/gemini-api/docs/pricing, https://ai.google.dev/gemini-api/docs/caching
- OpenAI, *API pricing* (realtime models, read 2026-11-13). https://developers.openai.com/api/docs/pricing
- Kyutai, *moshi* README (MLX on Apple Silicon). https://github.com/kyutai-labs/moshi; a report from an M2 24 GB: https://huggingface.co/kyutai/moshika-mlx-q8/discussions/2
- Qwen, *Qwen3-Omni* README (memory table). https://github.com/QwenLM/Qwen3-Omni
- Zheng et al. *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*, 2023 (judges favour their own model's style). https://arxiv.org/abs/2306.05685

- Sumers, Yao, Narasimhan, Griffiths. *Cognitive Architectures for Language Agents* (CoALA), 2023. https://arxiv.org/abs/2309.02427
- Christakopoulou et al. *Agents Thinking Fast and Slow: A Talker-Reasoner Architecture*, 2024. https://arxiv.org/abs/2410.08328
- Lin et al. *SwiftSage*, 2023. https://arxiv.org/abs/2305.17390
- Park et al. *Generative Agents: Interactive Simulacra of Human Behavior*, 2023. https://arxiv.org/abs/2304.03442
- Packer et al. *MemGPT: Towards LLMs as Operating Systems*, 2023. https://arxiv.org/abs/2310.08560
- Chhikara et al. *Mem0*, 2025. https://arxiv.org/abs/2504.19413
- Rasmussen et al. *Zep: A Temporal Knowledge Graph Architecture for Agent Memory*, 2025. https://arxiv.org/abs/2501.13956
- Yao et al. *ReAct*, 2022. https://arxiv.org/abs/2210.03629
- Wang et al. *Voyager*, 2023. https://arxiv.org/abs/2305.16291
- Wang et al. *JARVIS-1*, 2023. https://arxiv.org/abs/2311.05997
- Mindcraft (Minecraft LLM agents with commands). https://github.com/kolbytn/mindcraft
- Défossez et al. *Moshi: a speech-text foundation model for real-time dialogue*, 2024. https://arxiv.org/abs/2410.00037
- Ortony, Clore & Collins. *The Cognitive Structure of Emotions*, 1988 (the OCC appraisal model).
