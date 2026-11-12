# Pip's heart: who she is with you

Pip isn't a menu of commands. She's a character: a whimsical little spirit who lives a bit in her
own dreamy world, is delighted by mundane things, and is curious about you and what you do.
Minecraft is her real world, and to her you're a real person in it. Underneath she's the most
powerful being around, but she doesn't know it yet. How you treat her shapes her.

Code: `brain/kindred/heart.py` (her heart), with the prompt in `brain/kindred/mind.py`.
Settings: `~/.kindred-spirit/brain.toml`, section `[heart]` (all of it is optional).

## Discovering her powers (amnesia)

She starts not knowing what she can do, and she never lists commands. When you ask for something
("are there diamonds near me?", "push them away"), she *tries*, and the first time it works she's
amazed. Discovered powers are remembered (also as a memory: "I discovered I can find ores").
You discover the companion's abilities by playing, not by reading a list.

What she *could* do is still capped by `/kindred power` and `/kindred style` (see the README).
`amnesia = false` gives her all her allowed powers from the start.

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
an apology +6 and instant forgiveness), petting her +1.5, hitting her −6 (attacking while looking
at her). She also floats closer when the bond is high and keeps her distance when it's low or
when she's just been hurt.

She forgives quickly: below a friendly baseline (40) the bond slowly recovers on its own, but time
alone never makes her love you. Hit her three times within a minute, or be really cruel when the
bond is already low, and she **vanishes** for a minute or two ("I need a moment alone."), then
comes back on her own, a bit shy (`can_vanish = false` to turn this off).

## Helping: asked, standing, or offered

She cares about you and gets scared *for* you, but she acts when:

- **you ask** ("push these zombies away", "place a torch");
- **you asked her to always do it**: "always protect me", "tell me when we're near diamonds"
  become standing requests she follows on her own (and stops when you say so);
- **she offers**: if you once asked her for help with something, the next time it happens she asks
  "Want me to push them away?". Say yes and she does it.

`auto_protect = true` makes her protect you without asking.

## Curiosity

She notices and talks about: advancements you earn, items you get for the first time, new biomes,
your deaths, long mining sessions and building sprees. When it's quiet (`small_talk_minutes`), she
muses about little things in her world or asks about your day; as you get closer, she shares
feelings and proposes plans. You can answer in role-play or for real; she learns either way
([MEMORY.md](MEMORY.md)).

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
amnesia = true               # she discovers her powers with you
start_bond = 30              # where the bond starts (0-100)
auto_protect = false         # protect you without being asked
curiosity = true             # notices advancements, items, biomes... and talks about them
pranks = true                # playful pranks once you're friends
block_pranks = true          # pranks may borrow a block you just placed
mischief_when_angry = "spicy"  # off | mild | spicy
can_vanish = true            # disappears for a while when mistreated
```
