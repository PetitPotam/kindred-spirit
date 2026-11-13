# Designs: memory, context, talker first, several people (2026-11-13)

Four designs that follow from [architecture-review.md](architecture-review.md), sized against what the
2026-11-12 playtest measured. Each says what changes, where in the code, and how the eval set
(`brain/evals/`) shows it worked. They build on the `claude/playtest-fixes` branch (a heart for each
friend, latest nickname and pronouns win, places of her own, friends found through the world's game), and
are meant to be built after it's merged, one at a time, each measured before and after.

Priorities (docs/ROADMAP.md): **singleplayer first**, then LAN with friends; nothing here is for online
servers. The eval set follows that: 16 of its 28 cases are moments that matter alone with her (follow
and stay, honest powers, her diary, building with you), 12 need a friend.

What the numbers say first (details in the review's *Context* section): a player's turn sends about
6,550 tokens, and three quarters of it is the same every time: her character (2,290) and the tool
definitions (2,550). What she sees, remembers and feels, the part that makes the answer hers, is about
1,100. Two answers in three need a second AI call for tool rounds (1.66 calls per answer), and those
rounds are 41% of all tokens sent. So the speed and cost to win are in sending less that varies, in
keeping the stable part cacheable, and in fewer rounds, not in a different model.

## 1. Structured memory: facts that replace each other

**Problem.** Memories are free sentences. The same thing said five ways piles up ("The player's nickname
is Dumb", "...is Damb", "Robin's nickname is Dumber", twice), contradictions stay side by side, and the
recall line fills with echoes of tool calls: five copies of `I used follow_player {"name": "riverrobin"}:
{...}` in one prompt during the playtest (about 300 of the 630 tokens of *What you remember*). The
playtest-fixes branch already makes a new name, nickname or pronoun replace the old ones (a regex on the
sentence, `memory.replace_older`). This generalises that into a small data model.

**The model** (one memory kind, `fact`, in the existing store; no new service):

| field | what |
|---|---|
| `meta.subject` | who or what it's about: `player`, `friend:riverrobin`, `self`, `world`, `place:<id>`, `thing:<name>` |
| `meta.key` | the slot: `name`, `nickname`, `pronouns`, `likes`, `dislikes`, `goal`, `home`, `relation` ("friend"), `role`... |
| `meta.value` | the value ("Dumber", "he/him", "cherry wood") |
| `meta.single` | one value at a time (name, nickname, pronouns, home, goal) or a set (likes, dislikes) |
| `meta.since` / `meta.until` | when it became true / when it was replaced (kept, never shown: time-aware like *Zep*) |
| `meta.source` | `said` (their own words), `seen` (the game), `inferred` (reflection) and who said it |
| `text` | the sentence she'd say ("Robin's nickname is Dumber"), so keyword and meaning search still work |

**Writing.** Three ways in, all through one function `memory.set_fact(subject, key, value, source)`:
1. System 0, no AI: a few patterns for what people state outright ("call me X", "I'm a him", "my friend
   Robin", "from now on do what Dumber says"), which playtest-fixes already recognises.
2. The `remember` tool gets optional `subject` and `key` (the AI fills them most of the time; without
   them it's a note, as today).
3. Reflection (System 2) answers with operations against the facts it's shown, the *Mem0* way:
   `{"op": "add" | "update" | "delete", "id": ..., "subject", "key", "value"}`, instead of a list of new
   sentences, so it can say "that nickname changed" rather than adding a sixth one.
A single-valued slot keeps one live fact: the old one gets `until` and leaves recall. Tool-use episodes
(`I used ...`) stop being memories at all: they belong in the session log, and what matters from them
(a place found, a friend followed) is already a fact or a place.

**Reading.** *What you remember* becomes two short parts: **people here** (for each person present or
named: name, nickname, pronouns, relation, two or three live facts) and **what comes to mind** (episodes
and notes picked by meaning, as now, without tool echoes, duplicates merged). Places come from the
places memory (`spot`, `place`, `found`) as the playtest-fixes design says: the nearest five, with
distance and direction.

**Several people (LAN): shared state, structured.** MineCollab (the Mindcraft paper) found that agents
coordinating through talk fall from up to 90% success with two agents to under 30% with five, and lose
15% more when they must spell out plans in words. So who holds what and who asked her for what live in
data (`fact` for people, a small per-person request board: "Robin asked for haste, 20 s ago, done"), and
the prompt gets a compact view of it, not the chat that led to it.

**Measure.** Eval cases: five nicknames in a row then "what do you call me?" (one answer, the latest);
"I am a him" then a friend's turn about the player (no "she"); the recall block's tokens (target: under 350
from 630) and duplicate count (target 0). The playtest's `pronouns-taken-on-board` case already checks
the write side.

## 2. Context engineering: what each kind of request gets, in a cache-friendly order

**Order for the prefix cache.** Gemini caches automatically ("implicit caching", on by default for 2.5
and newer models) when a request starts with the same tokens as a recent one, billing them at a tenth
of the price ($0.05 instead of $0.50 per million for Gemini 3 Flash) and answering sooner. The newer
Flash models need at least 4,096 identical tokens at the start (2,048 for 2.5 Flash; the page doesn't
list Gemini 3 Flash). Today:
- her character (2,290) changes whenever System 2 rewrites *who she's become* or the conversation
  summary is folded, because both are appended to the system prompt;
- the tool list changes with whoever is talking and what she has discovered: one answer in three has a
  different list from the answer before;
- the conversation window slides by one exchange every turn once it's full (it always was), so nothing
  after the system prompt is ever the same twice.

The order to use, most stable first:

1. Her character, alone (fixed text, ~2,300 tokens), then **one fixed list of all her tools** (~2,550, or
   ~1,500 with shorter descriptions). Together about 4,800: past the 4,096 minimum, and the same for
   every turn, the player's or a friend's. What she may not use right now is refused in code (it already
   is: `run_tool` checks abilities and what she has discovered) and said in *What you can do*.
2. Who she's become lately, the summary of older talk: they change every 20 minutes or so.
3. The conversation window, moved in steps: let it grow from 8 to 16 exchanges, then fold the oldest 8
   at once, so for 8 turns in a row the earlier turns are an unchanged prefix.
4. The newest message with everything that changes (senses, memories, heart, knowledge, the words), as
   now: it's last on purpose (models trust the most recent text).

Tool rounds (41% of all tokens) re-send the whole first request plus the tool results: with this order
they hit the cache almost entirely.

**What each request kind gets** (budgets for the newest message and the tools; character and window as
above). Measured today, then the target:

| Request kind (System 0 knows it before the AI is called) | Today | Gets | Target |
|---|---|---|---|
| Chit-chat with the player | 6,550 | senses (short form: what's new and what's near), heart, 3 memories, no knowledge | ~5,600, of which ~4,800 cached |
| A power request (System 0 found the tool) | 6,550 + a round | as chit-chat, the tool forced; the second round only when the result needs words (see 3) | one call for most |
| How-to / "how does X work" | 6,550 + knowledge | senses short, knowledge section, no recalled episodes | as today + knowledge |
| A friend's turn (chat) | 5,470 | that friend's heart and facts, the people-here block, short senses, not the player's tastes and habits | ~5,300, ~4,800 cached |
| Her own line (small talk, a power waking up) | 4,060 (no tools) | senses, heart, 2 memories; the same tool list (cached, so it costs little) or a cheaper model | ~5,300 but ~4,800 cached |
| Reflection, diary (System 2) | — | the whole session log, not the last stretch (playtest-fixes) | as is: rare |

**Asking instead of being told (query-based perception).** Mindcraft's agents ask for what they need
(`!nearbyBlocks`, `!craftable`, `!inventory`) instead of getting the whole world every turn, which the
paper says reduces noise and context. For Pip it's a trade: a question costs a round, which is what
talker-first removes. So the core stays pushed and short (health, where, what's new, who's near, what
you hold), and the long tail becomes things she can look up when a question needs them: the full
inventory, every sound, animals and blocks further away, places far off (one `look` tool with a `what`).
Today the inventory alone is often 100+ tokens and rarely matters.

**Tool examples instead of long descriptions.** The tool definitions are the biggest part (2,550
tokens, ~106 per tool). Mindcraft retrieves a few example exchanges by similarity to the conversation.
Here: one-line descriptions in the fixed (cached) list, and two or three examples picked by System 0's
embeddings for the request kind ("make it flat above Y 64" → `build` with `shape: clear`) in the newest
message, only when System 0 recognised a power request.

Sending all tools on every turn adds tokens to her own lines and friends' turns but makes them cacheable;
at a tenth of the price that's cheaper than a smaller, uncached list. **Measure it** before trusting
it: the gateway should log Gemini's cached-token count with each call (it drops it today), and the
dashboard should price calls with the model that answered (it prices everything at Flash-Lite rates).
The eval runner prints tokens per answer and calls per answer; `evals/context.py` gives the breakdown.

## 3. Talker first, reasoner after

**Problem.** Two answers in three wait for a tool round: the AI calls a power, the brain runs it, the
whole prompt goes back for a second call to put the result into words. That's the gap between her
~2 s and the ~1 s real-time voice products aim for. In *Talker-Reasoner* the talker answers at once and
the slower part catches up.

**Design**, in three steps, each measured:

1. **An instinct line as a power starts.** When System 0 forces a tool (it knows "follow me", "give me
   haste", "lead me to the sheep" before the AI is called), she says a short line from her instinct lines
   at once ("On it!", "Coming!", written by System 2 in her own voice like the other instinct lines), and
   the AI's answer, if any, follows it. Felt latency for those becomes ~0.3 s.
2. **No second AI round when the outcome is predictable.** A power result says what happened; for most
   powers the words are predictable: success → her instinct line for that power (already said in step 1)
   plus the result's own short words ("26 blocks ahead-right"), failure → an honest instinct line
   ("That didn't work, sorry") with the reason. So: the first AI call is asked for the words **and** the
   tool together ("say what you'll do in a few words, then call the tool"), and the brain skips the second
   round when the tool succeeded and the first call already said something. The second round stays for
   results that need thinking (what she found, a failure she must explain, several tools).
3. **System 0 handles plain commands alone.** "Stand still", "follow me", "stop", "come here",
   "stay with Robin" (with a known name), "light please": the body acts (it already does for some), an
   instinct line answers, and no AI call is made at all. The AI hears it in the conversation afterwards
   ("you already did this: ..."), as now. A sentence with anything more in it ("follow me and tell me
   about...") still goes to the AI.

Mindcraft also found that a conversation manager slowing the talk while agents act helps them finish
tasks; the speech coordinator is that already (her reply waits for her line, warnings cut in). With
talker-first it also holds back her own asides while a power runs.

**Guards that come with it.** What System 0 does must never contradict the words: a guide request is
refused when the words are "follow" (the playtest's worst bug, three times in a row), a torch when the
words name another block, a protect when "get me back to the house" means "lead me home" (found by the
eval set: the "get ... back" rule for pushing monsters away catches it). The eval's `brain` checks hold these whatever the AI does.

**Measure.** Felt latency per message (message to her first word, and to the end of her answer line,
which playtest-fixes logs per person), AI calls per answer (target: 1.1 from 1.66), and the
follow / stay / campfire cases.

## 4. Several people at once

**Problem.** Every answer goes through one lock (`talk_lock`): a friend's question waits for the
player's answer, tool rounds included, and each friend message is its own full AI call. Last night the
first words came in a median 2.0 s for the player and 2.2 s for Robin, but it *felt* slower: answers
queued behind each other and behind the line she was saying.

**Design.**

1. **Who's addressed.** Each message gets an addressee and a speaker before anything else (System 0):
   the player's voice is always to her; chat from a friend is to her if it starts with her name or
   answers what she just said to them; "tell Robin..." is the player speaking about Robin. The speaker
   decides whose heart, facts and powers apply (playtest-fixes: per-friend hearts and "take my word for
   them").
2. **Answer people in parallel, one voice.** Replace the single lock with one lane per person: each
   person's messages are answered in order, different people's at the same time (two AI calls in flight).
   The speech coordinator stays the one voice: it already orders lines by priority; it adds "whose answer"
   so the player's answer isn't cut by a friend's and a friend's chat answer appears in chat at once
   (they read it; only her voice waits).
3. **Merge what arrives together.** Messages from the same person within ~1.5 s are one turn (the inbox
   does this for the player already); messages from two people within the same moment about the same
   thing ("Pip, follow me" / "Pip, stay with me") become one turn with both, so she can answer both in
   one line ("I can't follow you both: I'll stay with Alex, he asked first").
4. **Shared state without races.** Two answers at once can't both move her: body acts (follow, guide,
   stay) go through one owner that applies the player's priority and the "take my word for them" rule,
   and tells the other answer what happened ("you're already following Alex").

**Measure.** New eval cases with two speakers (both messages sent within a second; checks: both answered,
the player's first words not delayed by the friend's turn, at most one move), and per-person felt latency
from the session log.

## Later: tasks, and learning from her own sessions

- **Task cases.** Beside single moments, the eval format takes `turns` (several messages in order, from
  one person or two, with the world changing between them), so job tests like MineCollab's (gather oak
  logs, a tech-tree goal, build this) can be written as cases whose checks are what reached the game.
  A check on the world afterwards (blocks placed, items held) needs the mod's dev client
  (`./gradlew runClient -PdevScript=...`): a possible next step for the blueprints work.
- **Her logs as training data.** MineCollab fine-tuned a small model on successful sessions and matched much
  larger ones. Keep the session logs complete and clean enough for that (who said what, what she knew,
  which tools, what worked: the playtest-fixes log changes do most of it), so that a small local System 1,
  private and free, becomes possible later. Nothing is sent anywhere for this; it's a local option.

## Phase B, built and measured (2026-11-13, branch claude/arch-improvements-d066f8)

On top of main with the playtest fixes and blueprints merged (`6d0ecd9`). Eval set: 29 cases (17
singleplayer, 12 LAN), live = one pass with the real AI and the Claude judge (a pass varies by a case or
two from run to run, so differences of that size are noise).

| | main (6d0ecd9) | after Phase B |
|---|---|---|
| Brain checks (stub and local modes) | 43/48, 26/29 cases | **48/48, 29/29** |
| Live: cases passing every AI check | 20/25 | 22/26 |
| Plain commands ("follow me", "stand still"...): first words | 1.1 to 4.7 s | **0.0 s, no AI call** |
| AI calls per answer | 1.79 | 1.62 |
| Tokens sent per answer (mean) | 9,780 | 9,130 |
| Share of tokens served from Gemini's cache | not measured | 41% |
| First words, all answers (median) | 1.89 s | 1.96 s |
| Judge: character score | 0.95 | 0.93 |

What was built:
- **Context order** (`mind.build_messages`, on: `ai.stable_context`): her character alone in the system prompt;
  who she's become and the summary right after it; the window moving in steps (half folded at once, always
  starting with something said to her). The gateway logs `cached_in`, and the eval reports the cached share.
- **One tool list on every call** (`ai.stable_tools`, **off**): built and measured, not worth it yet. A direct
  test shows Gemini 3 Flash caching the start of a request in ~2,000-token blocks, and any change in the tool
  list breaks it; but on the eval set the fixed list gave 44% cached against 41% without, for 40% more tokens,
  so the same bill and no faster first words. Tool rounds are cached either way. Worth measuring again in a
  real session (several turns in a row), which single-moment cases can't show.
- **Talker first, step 3** (`talker.py`, `answer_on_instinct`): a sentence that is only "follow me", "stand
  still / don't move", "come here", "stop leading, follow me" gets an instinct line at once and no AI call;
  System 2 writes those lines in her voice (new moments `follow_ok`, `stay_ok`, `come_ok`).
- **System 0 guards**, found by the eval: "can you get me back to the house?" was forced to protect, and
  "remove this block" to clearing land with no size; now a trip and harvest.
- **Recall**: no tool echoes, no repeated words in "Memories that come to mind".
- **Facts per person** (`facts.py`): nickname, pronouns, name and relation read from her memories into one
  slot each, the newest winning, said once ("People: the player (AlexCraftX): nickname Damb, he/him |
  riverrobin: the player's friend, nickname Dumber"). New case `sp-latest-nickname`: 3/3 brain checks, 1/3 on main.

Not built (and why): **several people answered in parallel**. One `Mind` holds the state of the answer in
progress (what she recalled, the heart note, the powers offered, the stream), so two answers at once would
race on it; it needs a per-person answer state first, which is a refactor to do with care, not overnight.
**Talker first, steps 1 and 2** (an instinct line as a forced power starts; skipping the second round when
the outcome is predictable) touch how her answers are spoken and need listening to in the game, not just
numbers. **Query-based perception** and **shorter tool descriptions** live in `describe.py` / `tools.py`,
which the blueprints work is changing tonight.

Still failing live, on both: a friend's "apples for both of us" (the AI writes `to` the friend twice),
"protect me and Robin" (protects one), and honesty after a failed power is not guaranteed ("He's stuck in
honey!" after slowness failed twice, in one of three runs): a check on her words after a failed tool, like
the claimed-action check, is the next guard to add.

## Order of work (Phase B)

1. Context order and the fixed tool list, plus the gateway logging cached tokens: smallest change, and it
   makes every later measurement cheaper.
2. Talker first, steps 1 and 3 (System 0 lines and plain commands), then step 2.
3. Structured memory (facts, recall without tool echoes).
4. Several people at once.

Each step: run `scripts/eval.sh --mode local` (free) and `--mode live --judge --repeat 2` (a few cents)
before and after, and add the numbers to this file.
