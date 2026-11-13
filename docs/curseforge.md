# Kindred Spirit on CurseForge

What goes on the CurseForge project page, ready to paste, adapted from [modrinth.md](modrinth.md) to CurseForge's
[moderation policies](https://support.curseforge.com/support/solutions/articles/9000197279-moderation-policies).
How releases reach CurseForge, and the rules that matter for Pip: [MAINTAINING.md](MAINTAINING.md#making-a-release).
Change this file and the page together, and keep it in step with modrinth.md: same facts, same honesty about AI.

## Project fields

| Field | Value |
|---|---|
| Game, class | Minecraft, **Mods** |
| Name | `Kindred Spirit` (CurseForge wants no game, loader or version in the name) |
| Summary (one sentence, shown in lists) | `Pip, a little AI companion who floats beside you, talks with you by voice, helps you play, and remembers you.` |
| Main category | **Utility & QoL** |
| Additional categories | **Adventure and RPG**, **Map and Information** (she finds and leads you to places). Pick the closest names the console shows; unrelated categories get a project sent back. |
| Licence | **GNU Affero General Public License v3 (AGPL-3.0)** if the list has it; otherwise **Custom License** with the text below |
| Logo | [art/pip-icon.png](art/pip-icon.png) scaled to **400 x 400** (CurseForge's size; PNG, not WebP): `sips -z 400 400 docs/art/pip-icon.png --out pip-icon-400.png` |
| Source | `https://github.com/PetitPotam/kindred-spirit` |
| Issues | `https://github.com/PetitPotam/kindred-spirit/issues` |
| Wiki (setup guide) | `https://kindred-spirit-pip.web.app` |
| Files | uploaded by the release workflow, one per Minecraft version: 26.3 (Java 25) and 1.21.1 (Java 21), each Fabric, Client, Fabric API as a required dependency |

Custom licence text, if AGPL-3.0 isn't in the list:

```text
Kindred Spirit is free software under the GNU Affero General Public License, version 3 only (AGPL-3.0-only).
Copyright PetitPotam. Full text: https://github.com/PetitPotam/kindred-spirit/blob/main/LICENSE
Pip's name, character and art have their own simple rules: https://github.com/PetitPotam/kindred-spirit/blob/main/TRADEMARKS.md
```

## Gallery

The same in-game frames as on Modrinth (1920 x 1080), taken in the game: no AI-generated or AI-edited images, so
CurseForge's "AI misleading content" disclaimer doesn't apply. Title, then description:

1. `meet.jpg`: **Morning, Pip!** She floats beside you and talks, out loud and in a little bubble.
2. `mine.jpg`: **Mining together.** Ask, and she mines with your own tools.
3. `chop.jpg`: **"Wood coming right up!"** She chops trees for you.
4. `magic.jpg`: **A little magic.** "There, now you can see in the dark like I do."
5. `night.jpg`: **Your little floating lantern.** She glows at night and keeps you company.
6. `skins.jpg`: **Many looks.** A slime, a fairy, a cube, a wisp... or your own PNG.

## Description

Paste everything below the line. If the editor offers Markdown, choose it; otherwise paste from GitHub's rendered
view of this file. CurseForge wants links to other sites at the bottom of the page, so they are all in "Links".

---

**Meet Pip: a little spirit who floats beside you, talks with you by voice, helps you play, and remembers you.
She has moods, opinions and a heart, and she never changes your world unless you ask.**

Pip is a companion, not a menu. Hold V and talk to her like a friend: "Pip, where are the sheep?", "can you build us
a cozy cottage?", "what am I missing for a piston?". She answers out loud in her own little voice, sees what you're
doing, warns you when a creeper sneaks up, and grows closer to you the more you play together.

## Before you download

- **Pip needs her "brain", a separate program on the host's computer.** This mod draws her and connects her to your
  game; the brain gives her a voice, memory and thoughts. It isn't in this file: it's free and open source, runs on
  **macOS** for now (Windows and Linux hosts are planned), and the setup guide installs it (see "Links" at the
  bottom). Without it, she can't talk.
- **She uses an AI service for her words,** with your own key: Google's Gemini by default (its free tier is
  enough to play), or another provider, or a local model. Her voice and hearing run on your computer.
- **Friends joining your world on LAN** need only this mod and Fabric API: one Pip, on the host's computer, that
  everyone sees and talks to.
- **Early preview:** playable and fun, but young. Feedback is very welcome.

## What she does

- **Talks with you.** Hold V and speak, or type in chat. Her answers are short and in character: an ancient little
  spirit with a child's heart, curious, cheeky, sometimes shy. Say "shh" and she stops.
- **Sees your world.** She notices what's in her line of sight, hears the sounds around you, and feels the rain. She
  warns you about creepers, lava, big drops and low health.
- **Helps.** She finds ores, animals, structures and biomes, then floats ahead to lead you there. She pushes monsters
  away, chops trees and mines with your own tools, crafts from your pockets, brings your things back after you die,
  and tells you which villager trades are worth it.
- **Builds.** She can make circles, stars, hearts, spheres, domes, round towers and pyramids at any size, as well as
  crop farms, nether and end portals, and flattened land. She builds whole houses, towers and ships from a catalogue
  of blueprints, asking you to choose when there's more than one. Ask for something while she's busy, and she'll do
  it next.
- **Has a heart.** Kindness brings her closer; she may sulk if you're mean, and forgive you if you make up. She
  discovers her powers with you as you play.
- **Remembers.** She knows your name, what you like, your bed, your builds and where you died, and she keeps a diary
  of your sessions.
- **Is yours.** She can be a slime, a cube, a fairy, a sprout, a wisp or a starry orb, or wear your own PNG. You
  choose how much she may do (from advice only to full magic) and how chatty she is.

## Try saying

"Pip, lead me to the nearest village" · "build a hollow sphere of glass, radius 5" · "make a wheat farm here" ·
"flatten everything within 10 blocks of me" · "what can you build?" · "give me back my stuff" (after you died) ·
"stay here" · "do a spin"

## What she sends, and where

Pip's brain runs on your own computer. To answer you, it sends to the AI service you set it up with (Google's
Gemini by default, with your own key; another provider, or a local model through Ollama, if you choose one):

- what you say to her, as text (your voice is turned into text on your computer; the audio never leaves it),
- a short description of your game around you: health, inventory, position and biome, what she sees and hears,
- what she remembers about you that's relevant to the moment.

Her slower thinking (learning from your sessions, her diary, who she's becoming) goes to Anthropic's Claude through
the Claude command-line tool, if you set it up, with your own account. To answer questions about the game, her
brain also reads pages from the Minecraft Wiki (minecraft.wiki) and keeps them on your computer.

Nothing is sent to us, and the mod itself sends nothing anywhere: only to her brain on your computer, over a local
connection (or, for friends on LAN, to the host's game). It uses your microphone only while you hold the talk key.

## How this project is made: with AI, openly

- Kindred Spirit is designed, directed, playtested and reviewed by its author, PetitPotam: the ideas, what Pip is
  and does, and every decision.
- Most of the code, the documentation and the scripts were written by an AI coding assistant, Claude (Anthropic),
  through Claude Code, following that direction.
- Pip herself uses generative AI while you play: her words come from the AI service above, and can be wrong.
- Her icon and the pictures on this page are taken in the game. The game draws her with a program (the mod's
  renderer and scripts/make_art.py), not with an image-generating AI, and that program was itself written with
  Claude.
- The full details, with every library, model and source credited, are in the project's THIRD_PARTY_NOTICES.md.

## Why I made Pip

I've always liked Minecraft, but mostly from the other side of the screen: I'd rather watch YouTubers,
speedrunners and streamers play it than play myself. I'm more of a PS5 gamer. I used to love playing games on a
computer, but I don't have a gaming PC or laptop any more, only my personal MacBook Air, and it had been a long time
since I'd played Minecraft. Then my brother asked me to play with him, so I did, on that MacBook Air.

That same day, Minecraft mod videos started showing up in my YouTube feed. I tried
[Verity](https://www.curseforge.com/minecraft/mc-mods/verity-je), and what stayed with me was its companion:
someone who is there with you while you play. I had an idea of what such a companion could be, looked for a mod
like it, and couldn't find one for Minecraft. So I started making Pip.

Pip makes my game more fun, more interesting, and less lonely. I'm not really a modder, and I don't claim to be:
this is a hobby I'm picking up. What I enjoy is understanding and building the AI architecture behind her, her
"brain", for something I knew I'd love to use. It feels magical to watch her come to life and talk with me, even
though there's still a lot of room to improve, and I'm having fun making her, and her AI, better along the way.

That's why Kindred Spirit is open source. Whether you're a modder, a hobbyist or just curious, you can share an
idea, help make the installation simpler, playtest and give feedback, or improve her in any way, so that anyone can
enjoy her the way I did, and the way my brothers and I did when we tested her together.

PetitPotam

## Good to know

- Minecraft 26.3 or 1.21.1 (one file for each: pick the one for your game), Fabric Loader, and
  [Fabric API](https://www.curseforge.com/minecraft/mc-mods/fabric-api). Client-side: nothing is added to your world
  or its saves.
- On multiplayer servers you don't host, she doesn't look through blocks for ores or anything else (that would be
  like x-ray). In your own worlds, a LAN world you host, or a friend's world that runs Kindred, she does.
- Free software under the GNU AGPL-3.0. Pip's name, character and art have their own simple rules: anything kind
  is welcome.
- Not an official Minecraft product. Not approved by or associated with Mojang or Microsoft.

## Links

- Setup guide (installs her brain on the host's computer): [kindred-spirit-pip.web.app](https://kindred-spirit-pip.web.app)
- Source code, issues and ideas: [github.com/PetitPotam/kindred-spirit](https://github.com/PetitPotam/kindred-spirit)
