# Third-party notices and credits

Kindred Spirit is MIT licensed ([LICENSE](LICENSE)), © 2026 Kindred Spirit contributors. It builds on
the work of many others. This file lists everything it uses, downloads, reads or learned from, with
the licence of each, as far as we know it. If something is missing or wrong, please open an issue.

**Not an official Minecraft product.** Not approved by or associated with Mojang or Microsoft.
Minecraft is a trademark of Mojang Synergies AB / Microsoft. Nothing from the game is shipped in this
repository.

## How this project was made: with AI, openly

Kindred Spirit is written with **[Claude Code](https://www.anthropic.com/claude-code)**, Anthropic's agentic
coding tool, used in the Claude desktop app. Its author directs the work: the ideas and design decisions, the
playtests, the feedback, and the approval of every merge and download. Claude does most of the writing.

- **What Claude wrote:** most of the code (the Fabric mod in Java, her brain and the local services in Python, the
  dashboard), the tests, the documentation, the research summaries in `docs/research/`, the scripts that draw her
  skins and make the demo video and its music, and the commit messages. Commits carry no AI co-author line, at the
  owner's request; this section is that disclosure instead.
- **Which model:** Claude Opus 5.5 (`claude-opus-5-5`), for the whole project so far. Some work ran in parallel
  Claude Code sessions in their own git worktrees (titled "Fable: ..." in the work history: those were asked to
  use Claude Fable 5.2 but, per the app's session records, ran on Claude Opus 5.5 too).
- **How:** Claude Code's sessions and subagents, its web search and page reading for research (the sources are
  cited where they're used), its built-in browser to check the dashboard, and scripted test games of Minecraft
  for checks and the demo videos.
- **Pip herself uses AI while you play:** her conversation is generated live by Google's Gemini; her deeper
  thinking (learning, her diary, who she's becoming) by Anthropic's Claude through the Claude CLI; her voice by a
  local speech model. What she says is AI-generated and can be wrong.
- **Research summaries are AI-written** from the cited papers and pages; check the sources for anything that matters.

## In the mod (Java)

| What | Used for | Licence |
|---|---|---|
| [Minecraft Java Edition](https://www.minecraft.net) 1.21.1, by Mojang Studios | the game the mod runs in (not distributed) | [Minecraft EULA](https://www.minecraft.net/en-us/eula) |
| Mojang's official mappings | building the mod (names of the game's code) | Mojang's mappings licence (development use) |
| [Fabric Loader](https://github.com/FabricMC/fabric-loader) | loading the mod | Apache-2.0 |
| [Fabric API](https://github.com/FabricMC/fabric) | events, networking, commands, the fake player for her "hands" | Apache-2.0 |
| [Fabric Loom](https://github.com/FabricMC/fabric-loom) | the Gradle plugin that builds the mod | MIT |
| [Gradle](https://gradle.org) (wrapper) | building | Apache-2.0 |
| [JUnit 5](https://junit.org/junit5/) | the mod's tests | EPL-2.0 |
| [Gson](https://github.com/google/gson) (comes with Minecraft) | JSON | Apache-2.0 |
| [OpenJDK](https://openjdk.org) (Homebrew's build on the author's Mac; [Eclipse Temurin](https://adoptium.net) for friends on Windows) | compiling and running the build | GPL-2.0 with the Classpath Exception |

Her skins, textures and icon are original art made for this project (`scripts/make_art.py` and by hand).

## In her brain and the local services (Python)

| What | Used for | Licence |
|---|---|---|
| [websockets](https://github.com/python-websockets/websockets) | the link between the game and her brain | BSD-3-Clause |
| [NumPy](https://numpy.org) | audio and vectors | BSD-3-Clause |
| [pytest](https://pytest.org) | tests | MIT |
| [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) | running the Kokoro voice locally | MIT |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | running the voice model | MIT |
| [soundfile](https://github.com/bastibe/python-soundfile) | writing audio | BSD-3-Clause |
| [phonemizer](https://github.com/bootphon/phonemizer) with [eSpeak NG](https://github.com/espeak-ng/espeak-ng) | turning text into sounds for the voice (installed on your computer by the setup, not distributed) | GPL-3.0 (both) |
| [fastembed](https://github.com/qdrant/fastembed) | local embeddings (her understanding and memory search) | Apache-2.0 |
| [whisper.cpp](https://github.com/ggml-org/whisper.cpp) (`whisper-server`) | local speech-to-text (installed with Homebrew, not distributed) | MIT |
| [Pillow](https://python-pillow.org) | the demo video's cards | MIT-CMU (HPND) |
| [Python](https://www.python.org) and its standard library | her brain, the gateway, the dashboard (standard library only), the knowledge base | PSF License |
| [FFmpeg](https://ffmpeg.org) | recording and editing the demo video (installed separately) | LGPL-2.1+ / GPL-2.0+ depending on the build |

## Models (downloaded by `scripts/setup.sh` to your computer, never in this repository)

| Model | Used for | Licence |
|---|---|---|
| [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) by hexgrad (ONNX files and voices from [kokoro-onnx releases](https://github.com/thewh1teagle/kokoro-onnx/releases)) | her voice (`bf_lily`) and the demo's player voice | Apache-2.0 |
| [Whisper](https://github.com/openai/whisper) large-v3-turbo by OpenAI, in ggml format from [ggerganov/whisper.cpp](https://huggingface.co/ggerganov/whisper.cpp) | hearing you | MIT |
| [Silero VAD](https://github.com/snakers4/silero-vad) (ggml, [ggml-org/whisper-vad](https://huggingface.co/ggml-org/whisper-vad)) | finding where speech starts and ends | MIT |
| [BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) | embeddings for understanding and memory | MIT |

## AI services (through the gateway, with your own keys or subscription)

Her conversation uses Google's [Gemini API](https://ai.google.dev) (Gemini 3 Flash and Flash-Lite) and
her deeper thinking Anthropic's [Claude](https://www.anthropic.com) through the Claude CLI; the gateway can
also use OpenAI, Groq, Mistral, OpenRouter or a local [Ollama](https://ollama.com). Each is used under its
provider's terms, with the player's own account; nothing is shared between players.

## Knowledge and game data

| Source | Used for | Licence |
|---|---|---|
| [Minecraft Wiki](https://minecraft.wiki), by the Minecraft Wiki contributors | the knowledge base each player builds locally with `services/knowledge` (not distributed); passages are kept with their page and licence | [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/) ([terms](https://meta.weirdgloop.org/w/Meta:Copyrights)): non-commercial, share-alike, attribution |
| [minecraft-data](https://github.com/PrismarineJS/minecraft-data) by PrismarineJS | recipes, foods and mining data in the knowledge base | MIT (the game data in it is Mojang's) |
| The game's own recipes, structures and registries | crafting help, blueprints, her senses (read at runtime from your game) | Mojang |
| Minecraft's structure templates (village buildings, igloo, ruined portals, shipwrecks, pillager watchtower) | blueprints in your local blueprints folder, extracted from your own game files for personal use (not distributed) | Mojang |
| [minecraft-circles-schematics](https://github.com/Greaby/minecraft-circles-schematics) by Greaby | the circle blueprints (`circle_*`) in your local blueprints folder | CC0-1.0 |

## Research, references and inspiration (studied; no code copied)

- **Agents and memory:** Sumers et al., *Cognitive Architectures for Language Agents* (CoALA, 2023,
  [arXiv 2309.02427](https://arxiv.org/abs/2309.02427)); Christakopoulou et al., *Agents Thinking Fast and
  Slow: A Talker-Reasoner Architecture* (2024, [arXiv 2410.08328](https://arxiv.org/abs/2410.08328)); Lin et
  al., *SwiftSage* (2023, [arXiv 2305.17390](https://arxiv.org/abs/2305.17390)); Park et al., *Generative
  Agents* (2023, [arXiv 2304.03442](https://arxiv.org/abs/2304.03442)), the model for her memory; Packer et
  al., *MemGPT* (2023, [arXiv 2310.08560](https://arxiv.org/abs/2310.08560)); Chhikara et al., *Mem0* (2025,
  [arXiv 2504.19413](https://arxiv.org/abs/2504.19413)); Rasmussen et al., *Zep* (2025,
  [arXiv 2501.13956](https://arxiv.org/abs/2501.13956)); Yao et al., *ReAct* (2022,
  [arXiv 2210.03629](https://arxiv.org/abs/2210.03629)).
- **Minecraft agents:** Wang et al., *Voyager* (2023, [arXiv 2305.16291](https://arxiv.org/abs/2305.16291));
  Wang et al., *JARVIS-1* (2023, [arXiv 2311.05997](https://arxiv.org/abs/2311.05997)); White, Nottingham et
  al., *Collaborating Action by Action* (MineCollab, 2025, [arXiv 2504.17950](https://arxiv.org/abs/2504.17950))
  and [Mindcraft](https://github.com/mindcraft-bots/mindcraft) (MIT), whose commands and tasks shaped her
  jobs and tests; [Mineflayer](https://github.com/PrismarineJS/mineflayer) (MIT); [Baritone](https://github.com/cabaletta/baritone)
  (LGPL-3.0) for the building and mining order; [Carpet](https://github.com/gnembon/fabric-carpet) (MIT) for the
  fake-player idea; [Automatone](https://github.com/Ladysnake/Automatone) (LGPL-3.0).
- **Emotions:** Ortony, Clore & Collins, *The Cognitive Structure of Emotions* (1988), the OCC appraisal
  model behind her heart; the research notes in [docs/research/heart-research.md](docs/research/heart-research.md).
- **Voice:** Défossez et al., *Moshi* (2024, [arXiv 2410.00037](https://arxiv.org/abs/2410.00037)), weighed and
  set aside for now.
- **Blueprint formats:** the [Sponge Schematic Specification](https://github.com/SpongePowered/Schematic-Specification)
  (v2, v3), the vanilla structure format, and Litematica's format (as documented by
  [Litematica](https://github.com/sakura-ryoko/litematica) and [Litemapy](https://litemapy.readthedocs.io));
  readers written from the specifications. More in [docs/research/blueprints.md](docs/research/blueprints.md).
- **Ideas:** design notes from [MCPFabric](https://github.com/denfry/mcpfabric); the idea of a companion who is
  always there from [Verity JE](https://www.curseforge.com/minecraft/mc-mods/verity-je); Black & White's creature
  for learning from your reactions.

## Tools and services for building, installing and updating

| What | Used for | Terms |
|---|---|---|
| [Git](https://git-scm.com), [GitHub](https://github.com) and the [GitHub CLI](https://cli.github.com) | the repository, and friends cloning it | GPL-2.0 (Git), MIT (CLI); GitHub's terms |
| [Homebrew](https://brew.sh) | installing whisper.cpp, OpenJDK and FFmpeg on macOS | BSD-2-Clause |
| [Modrinth API](https://docs.modrinth.com) | `scripts/update-pip-windows.ps1` fetches Fabric API from Modrinth when it's missing | Modrinth's terms |
| [Hugging Face](https://huggingface.co) and GitHub releases | where `scripts/setup.sh` downloads the models above | their terms |
| [winget](https://learn.microsoft.com/windows/package-manager/) and PowerShell | the Windows guide and update script | MIT (winget) |
| [Mermaid](https://mermaid.js.org) | the diagrams in the docs (drawn by GitHub) | MIT |

## The demo video

The background music is generated from scratch by `demo/make_music.py` (no samples). The cards use Apple's
SF Pro Rounded system font on the computer that edits the video (not distributed). The player's voice in
the demo is synthesized with Kokoro.
