# Pip's heart: who she is with you

Pip isn't a menu of commands. She's a character: a whimsical little spirit who lives a bit in her
own dreamy world, is delighted by mundane things, and is curious about you and what you do.
Minecraft is her real world, and to her you're a real person in it. Underneath she's the most
powerful being around, but she doesn't know it yet. How you treat her shapes her.

Code: `brain/kindred/heart.py` (her heart), with the prompt in `brain/kindred/mind.py`.
Settings: `~/.kindred-spirit/brain.toml`, section `[heart]` (all of it is optional).

## Discovering her powers (amnesia)

She starts not knowing what she can do, and she never lists commands. You discover what she can do
by asking, not by reading a list. Discovered powers are remembered (also as a memory: "I discovered
I can find ores").

**Think fast, think slow.** The first time you ask for something she has never done, she answers
at once from the gut, in her mood of the moment ("Diamonds? Ooh, I don't know if I can... but I'll
try!"). Meanwhile, in the background, the power slowly wakes up:

1. After a while (about 20 seconds) she trails off, maybe after a little tangent about something
   around her, because she senses something strange: a humming under the ground, a pull from far
   away, the sky feeling like it would listen. She looks around and may whisper.
2. Sometimes she asks a small favour so the feeling gets stronger: stand still for a few seconds,
   pet her, or say her name. Doing it brings you closer; if you don't, it comes anyway (with a tiny
   pout).
3. Then it clicks: "I can sense diamonds now!", and she does what you asked back then.

If you ask again while it's waking up, she tells you it isn't there yet. If she's too upset to
focus (you've been mean), it slips away and you can ask again later. Powers you need right now
(pushing monsters away, a torch) wake up on instinct, instantly, the first time. Once discovered, a
power just works.

| Setting | |
|---|---|
| `awakening = "slow"` | the above; `"instant"`: she tries and it works on the spot |
| `awakening_seconds = 40` | about how long a power takes to wake up (it varies each time) |
| `favours = true` | whether she may ask a small favour while it wakes up |
| `amnesia = false` | she knows all her allowed powers from the start |

What she *could* do is still capped by `/kindred power` and `/kindred style` (see the README).

## Where she comes from

She doesn't know, and nobody wrote it: each world's Pip uncovers her own story with you. The clues
are in Minecraft's own old stories (the ancient builders, the old stones, the ancient cities sleeping
in the deep dark, strongholds and the End, beacons, the villagers' old ways) and in what you live
together. Some moments may reveal one small new piece, at most one every 20 minutes:

- a power of hers waking up;
- your first time together in the deep dark, the Nether or the End ("something about it feels strangely
  familiar");
- your bond growing into close friends, then best friends.

Each piece she realizes is kept as part of "where you come from" in that world, in the order she found
it, so her story stays consistent and grows with how you play. Ask her about it any time: before she
knows, she wonders with you. Importing a world's memories brings her story along.

## Who she is: doubts, tastes, the moments that shaped her

She doesn't think about what she is on her own. But ask her ("what are you?", "where do you come
from?", "are you real?") and she starts to reflect; the less she knows about herself, the more it
unsettles her. A meter of how shaken she is grows with each question and fades by itself (half-life
30 minutes): around the middle she wonders out loud, near the top she has a small existential crisis
(am I real? why am I here?) that colors her mood, and lets you comfort her. Kind words and every
piece of her origin she discovers settle it. When a power wakes up she may wonder what it says about
her. And if you talk a lot about yourself while she knows little about herself, she may feel a small,
honest pang of jealousy, once in a while.

She forms her own **tastes**: things she comes to love, like, dislike or hate, and why. Her feelings
for you color them: while she likes you she warms to what you love; while she's hurt or cross, what
you love annoys her. One opinion per thing, and she can change her mind (she remembers what it was).

A few **moments shape her**: rare, big ones (a joy, a fear, a hurt, a pride) become core memories she
always carries. A painful one "still hurts", until kindness and time help her make peace with it.

All of it is learned as you play (her learning, `reflect`), per world, shown in the dashboard's
Memory tab ("her tastes", "moments that shaped her").

## A deeper heart: five feelings, a sting, and what's between you

One bond number used to do everything. Now her heart (`brain/kindred/bonds.py`) keeps five slow
feelings that can disagree, so she can like you and not trust you, or trust you and resent you:

| Feeling | What it is | Moves |
|---|---|---|
| affection | how much she likes being with you | kind words, petting, time together; a grudge slowly poisons it |
| trust | she feels safe with you, your word means something | drops fast when hurt; grows **only** from time together without hurts, kept promises, favours (never from words) |
| respect | how you act with the world and with her | big feats raise it; killing villagers lowers it; drifts back over a day |
| familiarity | time and shared firsts | grows as you play; never drops below 70% of its peak |
| resentment | unresolved hurt, separate from liking | hurts add to it; fades with calm play and with days apart, down to a floor while a scar is painful |

On top: a **sting** (the hurt of right now, half-life 3 minutes) and her mood.

**Every hurt is appraised first.** Was it an accident (a fight around you, or a first slip from someone
she trusts), careless, or deliberate (hits in a row, a pattern, insults)? Bad weighs about twice as
much as good; a **pattern** of deliberate hurts (counted over the last days) multiplies new ones,
while a single slip from someone she trusts gets the **benefit of the doubt**. It stings more
from someone she loves.

**The ledger.** Each hurt opens an incident: open → (sorry) → probation → repaired, or a scar.
- Sorry for an accident or a careless act: forgiven, trust restored.
- Sorry for something deliberate: the grudge softens, and **probation** starts (a few minutes of play
  without hurts, longer for worse things). Trust comes back when it ends, 70% of it; the rest only
  with time. Hurting her again during probation is a **betrayal**: bigger impact, and every apology
  after that is worth half as much (`[sorry_real]`, an apology that names what you did with no
  excuses, is worth more than a plain sorry).
- For a serious hurt she may ask once for a small thing to make up (plant a flower, a little tree, light
  up a dark spot); doing it repairs at once.
- A pattern (or a bad betrayal) leaves a **scar**: a painful core memory that keeps some resentment
  until three calm sessions after a real apology or a gesture heal it.

**Stances.** Her behaviour follows a stance read from the feelings: *new*, *warm*, *easy*,
*guarded* (likes you, doesn't feel safe: keeps out of reach, flinches when you swing near her),
*wounded* (cares, and you hurt her), *reliant* (trusts you, not fond of you: helps but doesn't offer),
*cold*, *bitter*. She's told her stance in words, never numbers, with one sentence of why ("They
said "you're useless" earlier today. It's not the first time..."). Friendly pranks need affection,
familiarity and no grudge; spiteful ones need resentment.

**System 2** looks at the ledger when it reflects: it may form a few beliefs about you from real
patterns ("They always come back for me"; good ones count as trust), and soften or harden its
judgement of a recent hurt by one notch (banter after all, or really on purpose).

**Temperament.** Each world's Pip has slightly different sensitivity, forgiveness, warmth and pride
(±15%); a long kind history makes her thicker-skinned and warmer, a cruel one more sensitive (±20%
at most). `[heart] temperament = "thick-skinned" | "sensitive" | "forgiving"`.

**Seeing it.** The dashboard shows the five feelings, her stance, the open hurts (with probation
progress), her beliefs, temperament, and a line of *why* for every change. In game:
`/kindred heart` says how she feels about you; `/kindred heart fresh` starts her feelings over (the
old ones are kept in her history). The heart meter still shows the old bond, now derived from the
five. The research behind it, with sources: [research/heart-research.md](research/heart-research.md).
Defaults for its open questions: a grudge from words fades in about an hour of play, a pattern
needs about three good sessions; time apart softens resentment but doesn't bring trust back; she
asks for a gesture at most once per hurt and repair is always possible without it; the five feelings
are shown in the dashboard, not as in-game icons.

## The bond

A number from 0 to 100, shown as a small heart meter (top right) whenever it changes, and in
`/kindred status`.

| Level | Bond | How she is |
|---|---|---|
| hurt | 0–14 | short, a little cold, keeps far away, won't do favours until you're kind or apologize |
| wary | 15–34 | polite, curious, reserved; doesn't open up (strangers start here: `start_bond = 30`) |
| friend | 35–64 | warm, playful, asks about you and what you do |
| close | 65–84 | opens up, shares feelings and dreams, proposes little shared goals |
| best friend | 85–100 | affectionate, teases you, plans adventures for the two of you |

What changes it: each message you send is judged by the AI (sweet +4, kind +2, rude −5, mean −12,
an apology +6 and instant forgiveness), petting her +1.5, doing her a favour +2, hitting her −6
(with your crosshair right on her, and no mob, animal or block in front of her: hitting a cow next to
her doesn't count). She also floats closer when the bond is high and keeps her
distance when it's low or when she's just been hurt.

She forgives quickly: below a friendly baseline (40) the bond slowly recovers on its own, but time
alone never makes her love you. Hit her three times within a minute, or be really cruel when the
bond is already low, and she **vanishes** for a minute or two ("I need a moment alone."), then
comes back on her own, a bit shy (`can_vanish = false` to turn this off).

**Spamming her is toxic.** Saying the same thing again and again means less each time (+4, +1.3,
+0.8), and from the fourth time in five minutes it costs: −1, −2, up to −5 each time. She pulls away a
little and gets short with you; she won't say it back. Flooding her with messages (six or more in 30
seconds) does the same, and kind words can add at most +8 a minute. Messages you send while she's
thinking are answered together ("i love you (said 9 times in a row)"), not one by one.

**Accidents and pride.** One hit between friends is probably an accident: just an "Oof! Watch it!"
and a small dip. But she has her pride: hit her and say sorry, again and again, and the sorries
count for less and less until she stops buying it, stays hurt for a while, and may refuse what you
ask.

**Play-fights** (`play_fights = true`). As close friends, if you hit her by accident she may bonk you
back (a little knockback, no damage). And now and then, when you're at full health and nothing is
around, she play-hits you for fun, says sorry and heals you right away.

**Her tears bring rain** (`weather_follows_mood = true`, singleplayer). When you're really mean, or
she leaves crying, it starts raining; a real apology clears the sky ("Look, sunshine!").

## Her mood

Her mood isn't picked at random by the AI: it comes from a small score of how good she feels and how
stirred up she is. Everything moves it: your words, petting, hits, danger, discoveries, babies, a
villager killed. Feelings fade back to her resting state within a few minutes (happier when she likes
you), with a little whimsy so she's never quite the same twice. The mood colours her body, her
voice and what she says.

## How she talks

**One voice, coordinated.** Everything she says goes through one coordinator: danger warnings may
interrupt anything; her answers to you wait for the line she's saying to end; short reactions
("Ow!", "We're here!") wait a moment or are dropped; asides (a musing, a comment about an animal)
are dropped when she's talking, you just spoke, or an answer is on its way. If a warning
interrupts an answer, she finishes it afterwards ("Anyway, as I was saying..."). When you press
the talk key she stops at once, stays quiet while you hold it (her voice would reach your
microphone), and what she didn't finish is kept so she can come back to it; anything of hers the
microphone still picked up is removed from what she hears. Her subtitle appears as soon as she
knows what to say, and her voice follows. Her answers are streamed: she starts speaking at the
first finished sentence while the AI is still writing the rest, and each next sentence joins the
subtitle as it comes.

**Three ways of thinking.** *System 0*, instinct: rules and a small local model that understands
what you mean in a few milliseconds (requests in your own words: "I'm getting destroyed by these
skeletons" means protect me), plus her reflexes, warnings and the voice coordinator. *System 1*,
the fast AI that answers you. *System 2*, the slower thinking in the background: learning, her
story and tastes, the knowledge she listens for, powers waking up. They all speak through the one
coordinator.

**Who she is.** An ancient spirit with a child's heart, rediscovering what it once knew and could
do: delighted, distractible, nosy, strangely wise for half a sentence, not a girl or a boy, not young
or old. She has tastes and opinions, gets fixated (a word, a block, a tune stuck in her head that
she hums), can be unimpressed or prickly, and shows she cares by what she does rather than by
saying it. Her instructions describe that character and how she *tends* to talk, with a few
example lines in her voice; only a short list is firm (stay in her world, be truthful about what
she did and where things are, the reply tags).

**Who she's become lately.** On top of that, her slower thinking (System 2) writes a short
self-portrait in her own voice now and then (a lingering mood, today's obsession, the tune stuck in
her head, how she sees you now), from what she remembers and what just happened. Her quick AI reads
it with every answer, so how she talks drifts as you play. It's kept per world with its last five
versions (`world:<id>:self`), refreshed after joining, when your bond changes level, after an
import, and at most every 20 minutes after she reflects (`behaviour.becoming_minutes`). It can't
add rules: a portrait that talks about tools, settings or "must" is thrown away.

**Trying a change to her personality.** `brain/.venv/bin/python -m kindred.bench <label>` sends 15
little scenes (a first hello, "you're useless", "sing something", "I lost everything", good night...)
to the real AI and counts her tics (your name, questions, "Oh...", long lines). Compare labels in
`~/.kindred-spirit/logs/bench-*.json`; `BENCH_MODEL=... BENCH_EFFORT=minimal` tries another model.

**Her senses.** She perceives the world from where she floats, not as a radar:
- *Sight*: animals and villagers with a clear line of sight from her (up to 40 blocks); one behind
  a wall or a hill isn't seen. Danger is different: she still *senses* hostile mobs out of sight,
  so warnings never miss.
- *Hearing*: the sounds around you by the names the game gives them for subtitles ("Zombie
  groans", "Cow moos", "Lava pops"), within earshot, with where they came from; your own
  footsteps and work right next to you aren't news. A new, interesting sound from something she
  can't see may catch her attention ("You hear that?"), at most every four minutes.
- *Feeling*: rain or snow falling on her, the cold or the heat of the place.
- *Watching you*: what you just did, counted ("broke 3 oak log", "placed a torch", "got 4 oak
  planks", "ate a bread", "hit a zombie").
- *New and familiar*: something she's never seen or heard stands out (it's mentioned first, as new);
  the same cows all day stop being news, and feel new again after a long while away (`senses.py`).

**Her instincts, in her own words.** Her instant reactions can't wait for an AI ("Ow!", "Creeper
behind you!", "We're here!"), but fixed sentences repeat and don't sound like her. So a little
while after you join (45 s, `behaviour.instinct_lines_after`), her thinking AI writes a handful of
lines for each moment (being hit, a playful bonk, petting, arriving, warnings, a pranks' giggle...)
in her voice, from who she has become, your bond and your name; they're kept per world and written
again when your bond changes level. The built-in lines stay as the fallback. Warnings keep their
place for where the danger is ("Creeper {where}!" becomes "Creeper behind you!").

**She doesn't leave you in silence.** When an answer takes more than a moment
(`behaviour.fill_silence_after`, 1.4 s), she makes a small thinking sound ("Hmm...", in her own
words too) and a thinking gesture, at most every 20 seconds and never in danger. It isn't part of
the conversation the AI sees. When you start talking to her, she turns to look at you.

**She stays out of your way in a fight.** When you swing (at a mob, a block or the air) or monsters
are close, she drifts to just behind your shoulder, a little higher, and keeps well out of your
aim, then comes back to her usual spot a few seconds after it's over.

- Short, spoken lines, whimsical and curious. Her voice (Kokoro, a blend of two young voices) is
  lively and quick when she's excited, softer when she's calm or sad, and she **whispers** secrets,
  spooky things and what she senses in the dark.
- Spoken messages go through speech-to-text, so when your words look misheard or unclear she checks
  ("Did you say diamonds?") instead of guessing.
- When she gets something wrong and you're frustrated, she owns it, is a little frustrated with
  herself, then tries again or cheers you up.
- Sometimes she matches your tone: if you're sarcastic and she did nothing wrong, she can be
  playfully sarcastic back instead of apologizing. She always stays herself.
- Conversations wander: she follows tangents and comes back to what you were talking about. Older
  turns are folded into a short running summary, so long conversations stay cheap and she doesn't
  lose the thread.

## She doesn't make things up

She only states as fact what she really knows: the game state right now, what a power found, what
she remembers, or Minecraft knowledge. If she doesn't know, she says so, looks, or asks. Her
imagination is part of her, but she says it as imagination ("I bet...", "I wonder if..."), never as
something she sees or something that happened. If she says she did something ("I'm placing a
torch", "follow me!") and nothing actually ran, the brain catches it and makes her either really
do it or say honestly that she can't.

The one exception is on purpose, as a prank (`fibs = true`): once you're friends she may, rarely,
tell an obviously playful fib and own up in the same breath ("I think I saw a diamond behind
you! Hehe, kidding!"). When she's angry and `mischief_when_angry = "spicy"`, she may mislead you a
little out of spite (a wrong direction) and admit it when you apologize. Never about danger, your
health or your things.

## Helping: asked, standing, or offered

She cares about you and gets scared *for* you, but she acts when:

- **you ask** ("push these zombies away", "place a torch");
- **you asked her to always do it**: "always protect me", "tell me when we're near diamonds"
  become standing requests she follows on her own (and stops when you say so);
- **she offers**: if you once asked her for help with something, the next time it happens she asks
  "Want me to push them away?". Say yes and she does it. The same goes for anything she offers in
  her own words ("Should I light it up for you?" "Yes please!").

**Building with you.** Ask her to stack blocks ("a pillar 10 high", "10 blocks on each corner of a
5 by 5", "a little wall", "a floor of planks", "fence this area in"): she places them one by one,
floating to each spot, starting where you look and going forward and to your right. In grounded
style the blocks come from your inventory (the one you hold, or the one you name); if you don't
have enough she places what you have and tells you. Never inside you or an animal, never over
something solid, at most 256 blocks; "stop building" stops her. Shapes: pillar, corners, wall,
floor, outline (`mod/.../act/BuildPlan.java`).

When she protects you, she pushes every monster within 10 blocks away and leaves it dazed (slowed)
for a few seconds, so it doesn't walk straight back. With "always protect me" she checks every couple
of seconds and keeps them further away when you're low on health. "I can't see", "give me some
light" or "it's too dark" ask her for a torch (in grounded style she uses yours, so carry some).

**Where things are.** She only says where something is when she actually knows (she can see the
animals within 32 blocks, or a power found it), and always says which way from you: "two sheep, 38
blocks to your right". "Lead the way" or "I'll follow you" makes her really lead.

`auto_protect = true` makes her protect you without asking.

## Curiosity and animals

She notices and talks about: advancements you earn, items you get for the first time, new biomes,
your deaths, long mining sessions and building sprees. When it's quiet (`small_talk_minutes`), she
muses about little things in her world or asks about your day; as you get closer, she shares
feelings and proposes plans. You can answer in role-play or for real; she learns either way
([MEMORY.md](MEMORY.md)).

Animals are people to her, at first:

- the first time she meets a kind of animal she floats up to it and tries to talk to it, and is
  puzzled (or amused) that it doesn't answer;
- a new pet makes her thrilled: she goes to say hello and asks its name; later she visits your pets
  now and then;
- a baby animal or villager being born delights her;
- she's sad when you kill an innocent villager, or a lot of animals in a short time.

Small things she skips if she just spoke; moments that matter (a baby, a new pet, a first meeting,
a death) wait for a pause in the conversation instead.

## Pranks and mischief

Once you're friends (bond 55+), she sometimes plays a prank when the moment is right (a dark mine,
a long dig, you zoning out): a creeper hiss or a boom right behind you (only you hear it), then a
giggle, or she "borrows" a block you just placed (it's in your inventory; say "put it back").

When she's angry with you, she can really mess with you, per `mischief_when_angry`:

| | |
|---|---|
| `off` | no mischief |
| `mild` | sulks, refuses favours until you apologize, spooky sounds |
| `spicy` (default) | also borrows the blocks you place |

Pranks never happen when you're in real danger or low on health, never destroy anything, and every
block she borrows can be put back. `pranks = false` turns off the friendly ones; `allowPranks:
false` in `kindredspirit.json` turns off all of them at the game's side.

## All the settings

```toml
[heart]
same_companion_in_every_world = false  # false: each world has its own companion (docs/MEMORY.md)
amnesia = true               # she discovers her powers with you
awakening = "slow"           # slow: "I'll try!" at once, the power wakes up a little later | instant
awakening_seconds = 40       # about how long a new power takes to wake up
favours = true               # while it wakes up, she may ask you a small favour
start_bond = 30              # where the bond starts (0-100)
auto_protect = false         # protect you without being asked
curiosity = true             # notices advancements, items, biomes, animals... and talks about them
pranks = true                # playful pranks once you're friends
fibs = true                  # pranks may include a playful fib she owns up to (otherwise she never lies)
block_pranks = true          # pranks may borrow a block you just placed
mischief_when_angry = "spicy"  # off | mild | spicy
can_vanish = true            # disappears for a while when mistreated
play_fights = true           # as close friends: bonks you back, or play-hits you and heals you
weather_follows_mood = true  # her tears bring rain, an apology brings the sun back (singleplayer)
```

Her voice is set in `[voice]` (and the gateway, see [GATEWAY.md](GATEWAY.md#her-voice)).
