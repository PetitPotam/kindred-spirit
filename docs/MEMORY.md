# How Pip remembers and learns

The companion keeps what happens, learns from it, and brings the right memories back when it
talks to you. It's modeled on agent-memory research (Generative Agents, MemGPT), sized for a
laptop. Code: `brain/kindred/memory.py` (what to keep, learning, recall) and
`services/memory_store.py` (storage and search, behind the gateway).

## What it keeps

| Kind | Example | Where |
|---|---|---|
| **episode** | "The player said: let's find iron · I said: there's some 8 blocks ahead" | per world |
| **player** | "His name is Alex." "Loves building with cherry wood." | every world |
| **self** | "I love watching sunsets from the hill." | every world |
| **habit** | "Often asks me where to find diamonds." | every world |
| **world** | "The treehouse near spawn is the main project." | per world |
| **place** | "my base" at 120 64 -40 | per world |
| **found** | diamond ore, a village | per world |
| **diary** | one entry per play session | per world |
| **reminder** | "check the furnace", in 10 minutes / at night / next time / every night | every world |

## How it learns

1. **Everything is an episode.** Each exchange and each action is stored with its time and world.
2. **It reflects.** Every 8 exchanges, and when you leave the world, the AI reads what just
   happened and the related things it already knows, and writes down only *lasting* knowledge:
   who you are, its own feelings, your habits, facts about the world, each with an importance from
   1 to 10. Very similar memories are merged (the newer wording and the higher importance win), and
   the AI can point out duplicates to merge. When you leave, it also writes a diary entry.
3. **You can tell it directly.** "Remember that..." uses the `remember` tool; "this is my base"
   names a place; "remind me in 10 minutes to..." sets a reminder; "forget that..." forgets.

## How it remembers (recall)

For every message, the prompt gets a short "What you remember" section:

- **always:** what it knows about you (most important first), its own identity, your habits, the
  places you named (with distance and direction from where you stand), and active reminders;
- **plus the memories that matter right now**, found by the gateway's search, which blends:
  - **meaning:** cosine similarity of embeddings (a small local model by default),
  - **keywords:** SQLite full-text search, so names and exact words always count,
  - **recency:** memories fade with a half-life of about a week, unless they're used,
  - **importance:** set when the memory was written.

So the prompt stays small and fast however much it remembers, and an old memory comes back
exactly when it's relevant ("how's the cherry house?" brings up the cherry house).

## Reminders

- by the clock: "in 10 minutes", "in an hour", "every 20 minutes"
- by game time: "at night" (when night falls), "in the morning" (at sunrise)
- by session: "next time we play" (said in the welcome back)
- "every ..." makes it repeat

## Your memories are yours

- Stored in `~/.kindred-spirit/memory/kindred.db` (or on your own deployed gateway, see
  [GATEWAY.md](GATEWAY.md)). Nothing is uploaded anywhere else; the AI provider sees only the few
  memories included in each message.
- `scripts/memory.sh` shows everything it remembers;
  `scripts/memory.sh forget` erases every memory but keeps the bond and her powers;
  `scripts/memory.sh reset` makes her a brand-new companion (memories, bond, powers, conversations).
- In game: "forget that I ..." removes matching memories.
