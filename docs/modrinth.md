# Kindred Spirit

**Pip, a little AI companion who floats beside you, talks with you by voice, helps, builds, remembers, and has
feelings. She never changes your world unless you ask.**

> **Early preview.** Kindred Spirit has two parts: this mod, and Pip's "brain", which runs on the computer of
> whoever hosts her (macOS for now) together with a local voice and your own AI key. Setting up the brain:
> [the guide](https://kindred-spirit-pip.web.app). Friends who join the host's world on LAN only need this mod.

## What she does

- **Talks with you:** hold V and speak (local speech-to-text), or type in chat. She answers out loud with a local
  voice, short and in character: an ancient little spirit with a child's heart.
- **Sees your game:** what's in her line of sight, the sounds around you, your health, the weather, what you're
  doing. She warns you about creepers behind you, lava, big drops and low health.
- **Helps:** finds ores, animals, structures and biomes, and leads you there. She pushes monsters away, chops and
  mines with your own tools, crafts from your pockets, gets your things back after you die, and tells you which
  villager trades are good.
- **Builds:** circles, stars, hearts, spheres, domes, towers, pyramids and more, at any size. Also crop farms, nether
  and end portals, flattened land, and whole buildings from a catalogue of blueprints. While her hands are busy, she
  keeps your next request for after.
- **Has a heart:** a bond that grows with kindness and cools when you're mean, with moods, sulks, pranks and making
  up. She discovers her powers with you.
- **Remembers:** who you are, your places (your bed, your builds, where you died), a diary of your sessions.
- **Plays with friends on LAN:** one Pip on the host's computer. Friends with the mod see her and talk to her in chat.
- **Is yours:** skins (a slime, a fairy, a wisp, a starry orb, your own PNG), how much she may do (powers and
  style), how chatty she is.

## What she sends, and where

Pip's brain runs on your own computer. To answer you, it sends to the AI service you set it up with (Google's
Gemini by default, with your own key; another provider, or a local model through Ollama, if you choose one):

- what you say to her, as text (your voice is turned into text on your computer; the audio never leaves it),
- a short description of your game around you: health, inventory, position and biome, what she sees and hears,
- what she remembers about you that's relevant to the moment.

Her slower thinking (learning from your sessions, her diary, who she's becoming) goes to Anthropic's Claude through
the Claude command-line tool, if you set it up, with your own account. To answer questions about the game, her
brain also reads pages from the Minecraft Wiki (minecraft.wiki) and keeps them on your computer.

Nothing is sent to us, and the mod itself sends nothing anywhere: only to her brain on your computer (or, for
friends on LAN, to the host's game). Her voice and hearing run locally.

## How this project is made: with AI, openly

- Kindred Spirit is designed, directed, playtested and reviewed by its author, PetitPotam: the ideas, what Pip is
  and does, and every decision.
- Most of the code, the documentation and the scripts were written by an AI coding assistant, Claude (Anthropic),
  through Claude Code, following that direction.
- Pip herself uses generative AI while you play: her words come from the AI service above, and can be wrong.
- Her icon and skins are drawn by a small program (scripts/make_art.py), not by an image-generating AI; that program
  was itself written with Claude.
- The full details, with every library, model and source credited: the project's THIRD_PARTY_NOTICES.md.

## Good to know

- Minecraft 1.21.1, Fabric Loader, and [Fabric API](https://modrinth.com/mod/fabric-api). Client-side: nothing is
  added to your world or its saves.
- On multiplayer servers you don't host, she doesn't look through blocks for ores or anything else (that would be
  like x-ray); in your own worlds, a LAN world you host, or a friend's world that runs Kindred, she does.
- Free software under the GNU AGPL-3.0. Pip's name, character and art have their own simple rules: anything kind
  is welcome.
- Not an official Minecraft product. Not approved by or associated with Mojang or Microsoft.
