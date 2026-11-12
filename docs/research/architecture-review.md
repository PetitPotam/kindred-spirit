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
| AI calls | 550 in all; 447 for replies, about 2.5 per answer (tool rounds) |
| Context sent per reply | median 6,400 tokens (4,400 a day earlier) |
| Cost | $0.33 for the evening (Gemini 3 Flash for replies, Claude via subscription for reflection) |
| Speech-to-text | 186 recordings, 1 empty; names and game words misheard ("Waleed", "underpair") |

Good for a cascaded, mostly local pipeline and very cheap. Real-time voice products aim for about 1 s;
the gap is mostly tool rounds and context size, not the models.

## Speech-to-speech models, briefly

One model takes voice in and gives voice out, hearing tone and interruptions, answering in roughly
0.3-0.8 s. Cloud (OpenAI's Realtime API, Gemini Live) costs per minute of audio, far more than today's
setup (prices change: check them); local open models (Kyutai's Moshi, Qwen-Omni, ~7B parameters) need a
strong GPU or 16 GB+ of a Mac's memory, competing with Minecraft. Both mostly give up her chosen voice,
the layered prompt (heart, memories, senses) and control over each sentence. For now the cascade stays;
the speed to win is inside it.

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

## Lessons from the MineCollab paper (Mindcraft)

White, Nottingham et al., *Collaborating Action by Action: A Multi-agent LLM Framework for Embodied
Reasoning* (2025), the paper behind Mindcraft. Agents play as players through **47 parameterized
high-level commands** on Mineflayer (`!givePlayer("randy", "oak log", 4)` instead of many low-level
steps), with code generation as a fallback. Their benchmark, **MineCollab**, has cooking, crafting and
construction tasks (blueprints split across agents), each with a goal, starting inventories and a
timeout; crafting and cooking score 1 or 0, construction by an edit distance to the blueprint.

Their results (2-5 agents per task, test set): Claude 3.5 Sonnet best at 0.47 crafting / 0.64 cooking
/ 0.36 construction; GPT-4o 0.17 / 0.40 / 0.31; Llama 3.3 70B 0.16 / 0.36 / 0.19. Even the best model
"struggle[s] to place more than 40% of the total blocks" of a blueprint. Success falls from up to 90%
to under 30% going from two to five agents, and drops by over 15% when agents must spell out detailed
plans to each other. A small model (Llama 3 8B) fine-tuned on successful runs reaches the level of the
70B model and GPT-4o on crafting and construction. Agents often undo each other's work.

What it means for Pip:
1. **Ask for what you need, don't receive everything.** Their agents query the world (`!nearbyBlocks`,
   `!craftable`) instead of getting it pushed, "reducing noisy information and context lengths". Pip
   gets a full description of her senses with every message (part of the 6,400 tokens). Give her a
   short core and query tools for the rest: the context-engineering direction above.
2. **High-level, parameterized actions** are the right level (as Minecraft commands as her powers will
   be), with **few-shot examples retrieved by similarity** to the conversation instead of ever-longer
   tool descriptions.
3. **Don't let the AI place blueprints block by block.** Language models are poor at it (under 40% of
   blocks). The AI chooses what and where; deterministic code builds it (`/fill`, schematic placement):
   exactly the blueprints plan.
4. **Several people: share state, not words.** Coordination breaks with more participants and with
   long explanations. Keep who has what, who asked what and what's already done in structured state
   (per-person hearts, the activity log, places), not in her talk.
5. **Never undo the player's work.** Pip's building and chopping must respect what players built (the
   building sites in her memory of places can mark it).
6. **Pause talk while acting**: their conversation manager slows dialogue while agents are busy, like
   her speech coordinator; talker-first should speak once, then act.
7. **Measure like they do**: tasks with a goal, a starting inventory and a timeout, and an edit
   distance for builds, for her jobs and blueprints.
8. **Later, a small local model of her own**: fine-tuning on her successful sessions (the session logs
   are that data) could make a small model as good as large ones for her tools, privately and cheaply.
   Not now; the logs should be kept with that in mind.
9. **Keep what must be reliable in code.** Even the best models succeed less than two times in three;
   warnings, safety and anything she must never get wrong stay in System 0.

## Sources

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
- Mindcraft (Minecraft LLM agents with commands). https://github.com/mindcraft-bots/mindcraft
- White, Nottingham et al. *Collaborating Action by Action: A Multi-agent LLM Framework for Embodied Reasoning* (MineCollab), 2025. https://arxiv.org/abs/2504.17950
- Défossez et al. *Moshi: a speech-text foundation model for real-time dialogue*, 2024. https://arxiv.org/abs/2410.00037
- Ortony, Clore & Collins. *The Cognitive Structure of Emotions*, 1988 (the OCC appraisal model).
