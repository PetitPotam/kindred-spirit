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

## Each world has its own companion

By default every world gets its own companion: a new world means meeting a new Pip, with her own
memories, bond and discovered powers. Coming back to a world, you find the Pip who lives there.

- In game: `/kindred memory` (what she knows here), `/kindred memory worlds`, `/kindred memory import
  <world>` (her bond, her powers and how long you've known each other come along too: she isn't
  meeting you for the first time, and she rewrites her instinct lines as who she has become), `/kindred memory forget <words>`, `/kindred reset`.
- `scripts/memory.sh worlds` lists your worlds and what she knows in each.
- `scripts/memory.sh import "Old World"` brings what she knew about you, about herself and your
  habits into the world you played last (or name it: `import "Old World" "New World"`). Places and
  events stay in their own world. With the game closed, her bond and discovered powers come too.
- `same_companion_in_every_world = true` in `brain.toml` `[heart]` gives you one companion who
  follows you from world to world instead (then the "every world" rows above are shared).

## How it learns

1. **Everything is an episode.** Each exchange and each action is stored with its time and world.
2. **It reflects.** Every 8 exchanges, and when you leave the world, the AI reads what just
   happened and the related things it already knows, and writes down only *lasting* knowledge:
   who you are, its own feelings, your habits, facts about the world, each with an importance from
   1 to 10. Passing states ("Alex is sad about losing their items", "I feel guilty about tonight")
   are marked temporary: they fade after a day and a half and never outrank what lasts. Very similar memories are merged (the newer wording and the higher importance win), and
   the AI can point out duplicates to merge. When you leave, it also writes a diary entry.
3. **You can tell it directly.** "Remember that..." uses the `remember` tool; "this is my base"
   names a place; "remind me in 10 minutes to..." sets a reminder; "forget that..." forgets.

Who writes what: the brain's rules (System 0) store the episodes, the places she found and her heart;
her conversation (System 1) writes live with her tools (remember, forget, name a place, reminders); her
deeper thinking (System 2) keeps the lasting knowledge and the diary after each reflection. See the
[architecture](ARCHITECTURE.md#how-the-three-systems-talk-to-each-other).

**Known gaps, being fixed** (2026-11-12 LAN playtest): a friend's LAN world is named with its port,
which changes each time it's opened, so each LAN session was a fresh "world" (memories, heart and diary
split); the diary is written from the last few minutes only; places keep coordinates only when named or
found on request. A memory of places with coordinates, filled on her own, a stable LAN world name and a
diary from the whole session are in progress (see the roadmap).

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

## Places she remembers on her own

Beside the places you name (`place`) and what she found when asked (`found`), she keeps places on her own
(`spot`), with coordinates and dimension, from what the game already tells her: no extra talk, no AI call.

| What | When | Kept |
|---|---|---|
| where you're building | 15+ blocks placed in a short while | one per site (sightings within 24 blocks merge; it moves as the site grows) |
| your bed, chests, where you craft | you place one | one bed; chests and workshops merge within 8 blocks |
| portals | you go to another dimension | where the portal was on the side you came from |
| where you died | your health hits 0 | the latest death (so "take me back to where I died" finds your things) |
| firsts | the first of each animal you meet, each biome you find together | the first one stays first |
| dangerous spots | a lava or big-drop warning | merged within 10 blocks |
| where friends were last | a friend goes out of her sight | one per friend, the latest |

Each record: her words for it ("where we met our first cow"), what it is, x/y/z, dimension, biome, first and last
seen, how many times, with whom, how she felt, where it came from. At most 150 per world (the least important, then
oldest, fade). In each answer she sees "Places you know": the nearest and most important six, with distance and
direction from you, plus any that match your words. "Lead me back to where we saw the first cow", "to what I was
building", "to where I died" find the place by its description and lead there. The dashboard's Memory page shows them
on a map from above, with a list to rename or forget one; the session log notes each new place, with who and where.
