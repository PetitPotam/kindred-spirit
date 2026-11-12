# Blueprints, expertise and jobs: the next phases

Research and design for building from blueprints (sections 1-6), Phase 4, expertise and
understanding (section 7), and Phase 5, grounded actions and jobs (section 8), November 2026.

## Part one: blueprints and schematics

Research for the next building phases. In the 2026-11-12 LAN playtest the players
asked Pip for "a house for the three of us" and to flatten a hill; she could only stack simple shapes
(pillar, corners, wall, floor, outline, at most 256 blocks, a few a second). The playtest-fixes branch
adds a box house, a portal, clearing and flattening, and runs Minecraft commands for her powers. This
document is about the step after that: building **from blueprints**, files that describe a whole
build block by block, and what she'd need to choose, show, place, build and remember them.

What's here: the file formats (and which we can read with plain Java on Fabric 1.21.1), the mods that
already do this and what to learn from them, where builds come from and what their terms allow, how
Pip should use all of it, and a plan with estimates. The first piece, a reader for all three modern
formats, is implemented in `mod/src/main/java/dev/kindredspirit/blueprint/` (see the end).

## In short

- **Three formats cover nearly every modern build**: vanilla structure templates (`.nbt`, also
  Create's schematics), Sponge schematics (`.schem` v2/v3, WorldEdit and most build sites) and
  Litematica (`.litematic`). All three are gzip-compressed NBT with a palette of block states, so one
  small plain-Java reader handles them (done, tested). The old MCEdit `.schematic` (numeric ids from
  before 1.13) isn't worth supporting: WorldEdit converts it.
- **Nobody's build library lets us fetch or ship their files.** Planet Minecraft, GrabCraft and
  minecraft-schematics.com all keep rights with the creators and forbid redistribution or embedding
  in software. So Pip builds from (1) files the player downloads and drops in a folder, (2) the game's
  own structures (village houses and the rest, read from the player's own game), (3) our own
  blueprints and a house generator, and (4) what she and the player built and she remembered.
- **Learn from Litematica** (ghost preview where you look, material list, verifier) **and Create's
  schematicannon** (builds from materials in a chest, waits when something's missing, sound and
  particles per block). Baritone shows the order that works: bottom layer first, only what has
  support, nearest first.
- **Order**: wire the reader into her building once the playtest-fixes branch lands (she builds any
  blueprint file and the village houses), then a house generator ("a cozy cottage for three"), then the
  ghost preview, then "remember this house", then understanding builds (vision). About 8 to 11
  focused days in all, each step playable on its own.

## 1. The formats

| | Vanilla structure `.nbt` | Sponge `.schem` | Litematica `.litematic` | MCEdit `.schematic` |
|---|---|---|---|---|
| Made by | structure blocks, `/place template`, every built-in structure, Create | WorldEdit, FastAsyncWorldEdit, most build sites, Axiom export | Litematica | MCEdit, Schematica, old WorldEdit |
| Blocks | palette of `{Name, Properties}` + a list of `{state, pos, nbt?}` (only the listed cells) | palette `"minecraft:oak_stairs[facing=east]" → int` + one varint per cell | per region: palette + bit-packed longs | numeric ids + 4-bit data |
| Leave-alone cells | not listed (structure void) | `minecraft:structure_void` in the palette | none (air) | none (and air vs "don't care" can't be told apart) |
| Block entities | `nbt` on the block (chests' items, signs' words) | `BlockEntities [{Pos, Id, Data}]` | `TileEntities [{x, y, z, ...}]` | `TileEntities` |
| Entities | `[{pos, blockPos, nbt}]` | `[{Pos, Id, Data}]` | per region `[{Pos, ...}]` | `Entities` |
| Version tag | `DataVersion` | `Version` (1-3) + `DataVersion` | `Version` (7 since 1.21) + `MinecraftDataVersion` | none |
| Size limit | 48³ from a structure block; any size placed by code | unsigned 16-bit sides (65535) | none stated | 16-bit sides |
| Read with plain Java | yes | yes | yes | needs the 1.12 id table |

### Vanilla structure templates (`.nbt`)

The game's own format ([Structure file](https://minecraft.wiki/w/Structure_file),
[Structure Block](https://minecraft.wiki/w/Structure_Block), [/place](https://minecraft.wiki/w/Commands/place)).
Root: `DataVersion`, `size` (three ints), `palette` (list of `{Name, Properties}`) or `palettes`
(several looks of one shape, used by shipwrecks), `blocks` (each `{state: palette index, pos: [x,y,z],
nbt: block entity}`), `entities` (`{pos: doubles, blockPos: ints, nbt}`). Gzip-compressed (the wiki
doesn't say; the game's own `NbtIo.readCompressed` agrees with our reader in a test).

- **Saving**: a structure block saves at most **48×48×48** (since 1.16) to
  `saves/<world>/generated/<namespace>/structure/<name>.nbt` (singular `structure` since 1.21).
- **Placing**: `/place template <id> [pos] [rotation] [mirror] [integrity] [seed]` (permission 2;
  rotations `none`, `clockwise_90`, `counterclockwise_90`, `180`; mirrors `none`, `front_back`,
  `left_right`; `strict` only from 1.21.5). It looks the id up like a structure block: in memory, then
  the world's `generated` folder, then data packs, then the game's own (`minecraft:village/plains/houses/...`).
  It fails if a chunk it covers isn't loaded. No size limit beyond that.
- **In code**: `StructureTemplateManager` (`server.getStructureManager()`) gets or loads templates,
  `StructureTemplate.placeInWorld(level, pos, pivot, StructurePlaceSettings, random, flags)` places one
  with rotation, mirror and integrity, and it upgrades old files with Mojang's DataFixerUpper
  (`DataFixTypes.STRUCTURE`). Air in a template replaces what's there; a structure void keeps it.
- **Why it matters for Pip**: it's the format Create uses, `/place` places, and every vanilla
  structure is made of, so it's the one to save her own blueprints in.

### Sponge schematics (`.schem`, v1-v3)

[Specification](https://github.com/SpongePowered/Schematic-Specification) (v2 2019, v3 2021).
WorldEdit's default; most sites offer it.

- **v3**: `{Schematic: {Version: 3, DataVersion, Width, Height, Length, Offset, Metadata{Name, Author,
  Date, RequiredMods}, Blocks: {Palette, Data, BlockEntities}, Biomes, Entities}}`, wrapped in a
  `Schematic` compound. **v2**: the same fields flat at the root, with `Palette`, `PaletteMax`,
  `BlockData`, `BlockEntities` (block entity fields flat beside `Pos` and `Id`). **v1**: like v2,
  block entities under `TileEntities`.
- Sizes are unsigned shorts (`value & 0xFFFF`). Every cell has a palette index, as unsigned varints
  (7 bits a byte, low bits first) in a byte array, ordered `x + z*Width + y*Width*Length`.
- Palette keys are block states as commands write them (`minecraft:wheat[age=3]`); property order
  isn't fixed in v3, so they're parsed as a set. The v3 changelog mentions renaming `Palette` to
  `BlockPalette` but the field table still says `Palette`; the reader accepts both.

### Litematica (`.litematic`)

No written spec; checked against Litematica's own source (`LitematicaSchematic`,
`LitematicaBlockStateContainer`, `LitematicaBitArray` in [sakura-ryoko/litematica](https://github.com/sakura-ryoko/litematica))
and [Litemapy's format notes](https://litemapy.readthedocs.io/en/latest/litematics.html).

- Root: `MinecraftDataVersion`, `Version` (7 since 1.21; 6 for 1.20.4 files), `SubVersion`,
  `Metadata` (name, author, enclosing size, totals, preview image), `Regions` (named).
- A region: `Position {x,y,z}`, `Size {x,y,z}` that **may be negative** (it then reaches back from
  Position), `BlockStatePalette` (air first), `BlockStates` (longs), `TileEntities` (`x,y,z` from the
  region's min corner), `Entities` (`Pos` from the region's Position), pending ticks.
- Packing: `bits = max(2, bits needed for paletteSize-1)`, entries packed low bits first, and **an
  entry can run over into the next long**; cell order `y*sizeX*sizeZ + z*sizeX + x`.
- Several regions per file; we merge them into one blueprint.

### Legacy MCEdit/Schematica `.schematic`

[Schematic file format](https://minecraft.wiki/w/Schematic_file_format): `Blocks` (8-bit ids),
`AddBlocks` (extra 4 bits), `Data` (4-bit metadata), `Materials: "Alpha"`, index `(y*Length + z)*Width + x`.
Pre-1.13 numeric ids need the old id table (and the Flattening's renames) to mean anything. Not worth
it: our reader recognises the file and says how to convert it (WorldEdit on 1.13+ loads it and saves `.schem`).

### Create's schematics and Building Gadgets' templates

- **Create** saves schematics as vanilla structure `.nbt` in the instance's `schematics/` folder
  ([Saving a Schematic](https://github.com/Creators-of-Create/Create/wiki/Saving-a-Schematic)), so
  reading `.nbt` covers them. Servers cap uploads (`maxTotalSchematicSize`, 256 KB by default
  according to a hosting guide; unverified in Create's own docs).
- **Building Gadgets** (BG2 for 1.20+, Forge/NeoForge only) copies and pastes with its own template
  format: a JSON header with the material list and a compressed NBT body "closely related to the
  Minecraft Structure system" but not compatible with it
  ([BG wiki: Template](https://github.com/Direwolf20-MC/BuildingGadgets/wiki/Template), written for
  1.16). Not on Fabric, not a file people share: skip.

### Versions: `DataVersion` and renamed blocks

Every modern format records the game's data version (1.21.1 is **3955**). Blocks get renamed now and
then (`grass` became `short_grass` in 1.20.3; newer versions renamed `chain` to `iron_chain`) and the
Flattening (1.13) changed everything. In the game the right fix is the game's own: DataFixerUpper, as
vanilla does for structures and Litematica does for its palettes. The plain reader keeps the
`DataVersion` for that and fixes only the most common renames itself. A file from a **newer** game
may use blocks 1.21.1 doesn't have; the in-game step must skip those and say so ("there's a block
here I don't know: copper bulbs from a newer world").

## 2. The mods that already build from blueprints

| Mod | What it does | What Pip can learn | Interop |
|---|---|---|---|
| **Litematica** (Fabric, client, LGPL-3.0; [Modrinth](https://modrinth.com/mod/litematica)) | Saves areas, shows a schematic as **ghost blocks** placed where you choose, a **material list**, a **verifier** (missing, wrong, extra blocks), "easy place" (click to place the right block). No printer (left to add-ons) | The ghost preview where you'll build, layer by layer; the material list with what you have; the verifier as "what's left to do"; moving and turning the placement before building | Read its files (done). It also reads `.schem` and `.nbt`. Its placements live in its config folder; reading which schematic the player has open is possible later |
| **WorldEdit** (Fabric/Bukkit, GPL-3.0) / **FAWE** (Paper only) | Copy, paste, rotate, flip, load `.schem`; `//paste -a` skips air | Paste with or without air, rotate around the copy point, undo | Read `.schem` (done); WorldEdit keeps them in `config/worldedit/schematics/` |
| **Schematica** (legacy, up to 1.12) | The original ghost preview and printer | The idea Litematica refined | `.schematic` only: skip |
| **Create** (Forge/NeoForge; Fabric port) | Schematic and Quill saves; the **Schematicannon** prints a schematic from materials in adjacent chests, using gunpowder, **stalls when the next block is missing** (or skips it), shows progress, a book becomes the material list ([Printing a Schematic](https://github.com/Creators-of-Create/Create/wiki/Printing-a-Schematic)) | Grounded building as a visible machine: materials from a chest, a pause when something's missing ("I need 12 more glass"), a block flying into place. Her version: blocks float from your chest to the spot | Its schematics are `.nbt` (done) |
| **Building Gadgets** (Forge/NeoForge) | Copy-paste gadget, template manager with a preview | Paste costs real materials; a template keeps its material list | Own format, not on Fabric: skip |
| **Baritone** (client, LGPL-3.0) | `#build file.schematic` builds automatically, `#schematica` builds what Schematica shows; reads MCEdit `.schematic`, Sponge **v1-v2** and Litematica **v7** ([formats](https://github.com/cabaletta/baritone/blob/1.21.1/src/main/java/baritone/utils/schematic/format/DefaultSchematicFormats.java)) | The builder order that works: only blocks it can place against something, nearby first, lower layers preferred (`y*100` in its goal heuristic); `buildInLayers`, substitutes (`buildSubstitutes`), "treat these as air" (`okIfAir`), ignore direction or properties | None needed: she floats, she doesn't walk or pathfind |

What none of them do, and Pip can: **choose** a build with you in words, **turn it to face you** by
finding its door, show it as a little magic before it's real, build it **with** you (you lay the
floor, she does the walls), and **remember** what you built together as hers.

## 3. Where builds come from, and what we may do with them

| Source | Access | Formats | Terms (read November 2026) | So Pip may... |
|---|---|---|---|---|
| **Planet Minecraft** | Web pages, downloads per project (some need a login); no public API found | `.schem`, `.litematic`, `.nbt`, world saves (whatever the author uploads) | [Terms of Use](https://www.planetminecraft.com/terms_of_use/): no redistributing site content "in any manner whatsoever", no embedding site data in "application software" without written permission, no systematic extraction. Creations stay the creators' | Not fetch or ship. The player downloads, Pip reads |
| **minecraft-schematics.com** | Web pages, downloads with an account | `.schematic`/`.schem` mostly | [Terms](https://www.minecraft-schematics.com/terms/) (2013): "All schematics on this site are copyright their original authors"; no license granted | Same |
| **GrabCraft** | Browse layer-by-layer blueprints online; no downloads | none to download | [Terms](https://www.grabcraft.com/terms-of-use-privacy-policy/): personal use only, no sharing "by downloading them, recreating, or by taking pictures", only links | Never copy; she could *link* a page for the player |
| **createmod.com** (Create schematics) | Downloads, an API | `.nbt` | [Terms](https://createmod.com/terms-of-service): API for individual good-faith use, no bulk retrieval; [rules](https://createmod.com/rules) ask for visible credit | The player downloads; no bulk fetching |
| **The game itself** | `StructureTemplateManager`, `/place template` | `.nbt` in the game jar (`data/minecraft/structure/...`) | Mojang's assets: fine to *use* from the player's own game, not to redistribute | **Yes**: village houses for every biome, igloo, ruined portals, trail ruins... read from the player's own game, nothing shipped |
| **Ours** | in the mod's resources | `.nbt` | the project's license | Yes: a few original builds we design (a cottage, a lookout, a bridge, a farm plot) |
| **Generated** | code | in memory | ours | Yes: a house generator sized for N people |
| **What you build together** | captured from the world | `.nbt` per world | the player's own | Yes: "remember this house", "build our house again over there" |

Conclusion: **Pip doesn't download or ship anyone else's builds.** The player drops files in a
folder (her own `config/kindredspirit/blueprints/`, and she can also look in `schematics/`, which
Litematica and Create use, and WorldEdit's `config/worldedit/schematics/`), and she keeps the author
and file name with each blueprint so she can say whose it is. A future "find me a castle online"
would at most open the page for the player to download themselves. Any outbound fetching or
publishing stays behind the user's explicit OK.

## 4. How Pip should use them

**Choosing.** "Build us a cozy cottage for three" → System 1 calls one tool, `blueprint`, with what
it understood: a name or a description ("cozy cottage", "the castle I downloaded", "a plains house",
"our house"), the number of people, and a block style if said. The mod lists what she has (files in
the folders with their names, sizes and authors; vanilla village houses by biome; her own; generated
houses) and picks the best match by name and size (a house for three: at least 3 beds or 7×7 inside);
when nothing matches, the generator makes one. She says what she picked in her words ("A little
plains house with a garden, it'd fit the three of you!"), never invents one she doesn't have.

**Previewing as a ghost.** Before anything is real, she shows it: translucent blocks where it will
stand, drawn on the asking player's screen only (like her body, nothing in the world), rising layer by
layer in a second, with her glow sweeping over it. It follows where the player looks until they say
"here" or "build it", and listens to "turn it", "the other way", "a bit further", "smaller" (the
generator) or "never mind". In grounded style the preview carries the material list ("you have 40 of
the 120 planks"); missing blocks show in red, like Litematica's verifier.

**Turning and placing.** The front of a blueprint is the side with its door (`Blueprint.frontTurns()`),
else its south side; the build is turned so the front faces the player and starts where they look,
reaching away from them (centred on the door, or from the left corner like her simple shapes). Its
bottom layer sits on the ground at that spot; later, she can lift or sink it to the terrain's average
height and fill under it.

**Building, magic style.** Fast and visible: a layer or a few dozen blocks a tick through the
game's own placing (or `/setblock` and `/place template` once the command powers land), sparkles on
each new block, her floating along the rising edge. Small houses appear in a few seconds, castles in
under a minute. The terrain is cleared where the template has air (a hill inside the house), top down,
and the details (torches, doors, beds) go in last so nothing pops off.

**Building, grounded style.** From the player's inventory (and later a chest they point at, like the
schematicannon): the material list first ("we need 64 oak planks, 20 glass, a door; you have
everything but the glass"), then block by block at a calm pace, each one taken from the pockets. When
something runs out she pauses and says what's missing instead of skipping it, and carries on when it
appears ("got the glass? Then let's finish the windows!"). Partial builds are fine and resumable: the
remaining steps are what's still different from the blueprint (Litematica's verifier, Baritone's
"incorrect positions").

**Remembering.** "Remember this house" (or "save this as our base") → the mod captures the box around
the building site (from the playtest notes' building-site places: a cluster of blocks you placed, or
the box the player points out) as a blueprint, saves it as a vanilla `.nbt` in that world's
memory folder, and the brain stores a memory ("our cherry cottage, built together on day 12"). Later,
"build our house again by the lake" works, and the file is one a structure block, `/place`, Create
or Litematica can open.

**Seeing (the vision side, Phase 4).** The same capture lets her *understand* what's in front of her:
a building site turned into a short description for the AI (size, materials, a roof or not, a door,
rooms, what's unfinished: "a 9×7 spruce cabin, no roof yet, the east wall half done"). With a
blueprint in progress, the verifier tells what's left ("three windows and the roof"). Further on,
matching what she sees against known shapes (a village house, a portal, a farm) lets her say "oh, a
little temple!" and the player's build habits ("you love spruce and dark oak") feed her memory.

## 5. Plan for the next phases

Each step ends in something playable. Days are focused working days for one person (or one agent
session), including tests and a sandbox check.

| # | Step | What it gives | Depends on | Estimate |
|---|---|---|---|---|
| **B0** | **Blueprint reader** (done on this branch) | `.nbt`, `.schem` v1-v3, `.litematic` into one blueprint; turning; front by the door; placement in front of a player; build order; material list; saving as `.nbt`. 19 tests | — | done |
| **B1** | **In-game blueprints** | Block states resolved through the game (`BlockStateParser`, unknown blocks skipped and reported), old files upgraded with DataFixerUpper, block entities loaded (chest items, sign text), the library: her folder, `schematics/`, WorldEdit's folder, the vanilla village houses, our own few | B0 | 1 day |
| **B2** | **Building a blueprint** | A `blueprint` build in her Builder: magic (fast, sparkles, clears where there's air) and grounded (material list, from your pockets, pauses when something's missing); the brain's tool (`blueprint`: name/description, people, style) and "what can you build?"; honest answers when nothing fits | B1, playtest-fixes merged | 1 to 1.5 days |
| **B3** | **House generator** | "A cozy cottage for three": a floor plan sized by people (a bed each, a table, a chest, a crafting table, a furnace), walls with windows, a pitched stair roof, a door facing you; wood and stone from the biome or what you hold. Outputs a blueprint, so B2 builds it and B4 previews it | B0 (B2 to build) | 2 days |
| **B4** | **Ghost preview** | Translucent blocks where it will go, following your look, "turn it / here / never mind", missing materials in red, her glow sweeping it | B1 | 1.5 to 2 days |
| **B5** | **Remember this house** | Capture a building site or a pointed-out box into a blueprint, save per world, a memory with her own name for it; "build our house again here" | B1, B2 | 1 day |
| **B6** | **Understanding builds** (Phase 4 vision) | What's in front of her as words for the AI (size, materials, roof, door, unfinished parts), the verifier's "what's left", recognising known shapes, the player's building habits into memory | B5 | 2 to 3 days |
| later | Phase 5 jobs | Materials from a chest you point at; "gather what we need" (chop, mine within the grounded radius); building alongside you (you do the floor, she does the walls); terrain fitting (foundations, stairs down a slope) | B2 | — |

**First**: B1 and B2 together, as soon as the playtest-fixes branch is merged, because they turn
"build us a house" from a box into any real house (the player's downloads, or the game's own village
houses) with almost no new design. **Then B3**, since "for three people" is what the players actually
asked and the generator needs no files at all. B4 makes it feel like her magic, B5 and B6 make it hers.

## 6. What's implemented on this branch

Package `dev.kindredspirit.blueprint` (plain Java, no game classes, so it's tested on its own):

| Class | What it does |
|---|---|
| `Nbt` | gzip NBT reader/writer into plain maps and lists, bounded for untrusted files (64 MB, depth 512, array lengths checked) |
| `BlockSpec` | a block state (`minecraft:oak_stairs[facing=east,half=bottom]`), parse/print like commands, turned by quarter turns (facing, axis, sign rotation, fence/wall/pane/vine sides, rail shapes, jigsaw orientation) |
| `Blueprint` | the box: dense cells (palette index or "leave alone"), block entities, entities, name, author, format, data version; `rotated`, `frontTurns` (by the door), `materials`, `solidBlocks`; a `Builder` to make one |
| `StructureFormat`, `SpongeFormat`, `LitematicFormat` | the three readers (Sponge v1-v3, Litematica multi-region with negative sizes and entries over two longs); the structure writer for saving |
| `Blueprints` | reads any file by what's inside, refuses huge ones (more than a 128³ box, 16 MB files) and old `.schematic` with a helpful message; writes `.nbt` |
| `Placement` | turns and places a blueprint in front of the player (front centre or front left), its world box, and the build order: clear top down, frame bottom up row by row back and forth, then details (torches, doors, beds, plants, water), second halves marked |
| `Materials` | block → items (doors and beds once, double slabs twice, wall torches as torches, crops as seeds, potted plants, buckets, candles...) |
| `Renames` | the common block renames for files from other versions |

Tests: `mod/src/test/java/dev/kindredspirit/blueprint/BlueprintTest.java`, 19 tests on sample files
written by an independent Python encoder (`mod/src/test/resources/blueprint/make_samples.py`): the
same cottage (chest with bread, door, wall torch, double slab, a structure void, an armor stand) as a
structure file, Sponge v2 (palette ids past 127, so two-byte varints), Sponge v3, and Litematica (a
negative-size region with 5-bit entries running over longs, plus a chimney region). Also: turning,
door-facing placement for all four directions, build order, saving and reading back, the game's own
`NbtIo` reading what we write and the other way round, broken, huge and legacy files.

### How it plugs into her building (after the playtest-fixes branch lands)

That branch's `BuildPlan.Step(x, y, z, kind, block)` and `Builder` (place like a player `P`, clear
`X`, magic at ~120 blocks a second, grounded 10, remembers who asked) are the seam:

1. A new shape `blueprint` in `Builder.start`: load the blueprint by name through the library (B1),
   `Placement.inFront(bp, origin, facing, FRONT_CENTER)`, and turn its steps into the builder's queue:
   `CLEAR` → `X`; `BLOCK` and `DETAIL` → a new kind `S` (set this exact state) carrying
   `step.state().toString()` and the block entity; `SECOND_HALF` → dropped when placing like a
   player (the game makes the top of a door and the head of a bed), kept for the command path.
2. Kind `S` in `Builder.tick`: parse the state with `BlockStateParser.parseForBlock`, then in magic
   `level.setBlock(at, state, 2|16)` (or `/setblock x y z <state>` through the command powers) and load
   the block entity with the level's registry access; in grounded take `Materials.of(state)` from the
   pockets first and place like a player, then correct the state (stairs facing) if the placement
   differs.
3. The material check uses `Blueprint.materials()` against the inventory before starting (grounded),
   instead of counting one block kind.
4. Limits: blueprints get their own cap (the `Blueprint.MAX_VOLUME` box, and a block count per style)
   rather than `MAX_BIG`; magic can place a whole vanilla template with `/place template` (it handles
   rotation and block entities itself) when the template is in the game or the world's `generated`
   folder.
5. The brain: a `blueprint` tool (or `build(shape="blueprint", name=...)`) plus "what can you build?"
   from the library list; the honest "I can't build that" stays.

## Part two: Phases 4 and 5

What already exists, so nothing is built twice:

- **In the brain and mod (main)**: a knowledge base of the wiki plus minecraft-data's exact 1.21.1
  recipes, foods and mining needs, searched when you ask how something works (`docs/KNOWLEDGE.md`,
  `brain/kindred/knowledge.py`); reminders, including repeating ones ("every night"), and standing
  requests ("always protect me"); proposing little goals when close; `harvest` (the tree in front of
  you, whole, or the block you look at, drops into your pockets); `guide` (she leads you somewhere);
  `youDid` in every snapshot ("broke 3 oak log", "placed a torch", last 30 seconds).
- **On the playtest-fixes branch (in progress)**: a memory of places with coordinates, including
  where you died (item 25); a per-player activity log on the world's game (blocks placed and broken,
  crafted, killed, ate; item 13); session logs good enough to analyse a playtest from, a diary from
  the whole session (items 23, 28); Minecraft commands as her powers (/fill, /setblock, /give,
  /effect, /enchant...; item 30); building; finding and following players anywhere; a heart for each
  person.

## 7. Phase 4: expertise and understanding

### Recipes and items

**What exists elsewhere.** [minecraft-data](https://github.com/PrismarineJS/minecraft-data) (MIT;
per version: items, blocks with hardness, the tool they need and their drops, recipes, foods,
entities, biomes, enchantments) is what Mineflayer bots use, through
[prismarine-recipe](https://github.com/PrismarineJS/prismarine-recipe) and mineflayer's `craft`. It's
already in her knowledge base as text. Bots like [Mindcraft](https://github.com/kolbytn/mindcraft)
and [Voyager](https://arxiv.org/abs/2305.16291) go further: they plan crafting chains (logs to planks
to sticks to a pickaxe) from those recipes and the bot's inventory.

**What Pip needs** is the planning part, with *your* pockets: "can I make a piston? What am I
missing?" should be answered exactly ("you need an iron ingot: smelt the raw iron you have"), not
from a recipe page. **Design**: the mod plans from the game's own RecipeManager (exact for 1.21.1,
data packs and mods, nothing downloaded) and the player's inventory; the brain gets a short
answer and says it in her words. The knowledge base stays for the "why" and "how" (where to find
things, what something is for).

**Done on this branch**: `mod/.../craft/` (`CraftPlanner`, `Recipe`, `GameRecipes`), see section 9.

### Expert modes: survival, redstone, builder, speedrun

**What exists elsewhere.** Mindcraft has *modes* the bot switches on and off (self-preservation,
self-defense, item collecting, torch placing, hunting, idle staring...), each a small rule set
around the LLM, listed by a `!modes` command. Speedrunners use timers with splits
([LiveSplit](https://livesplit.org/), SpeedRunIGT), and the classic any% route is well documented
(the wiki's speedrunning tutorials are in her knowledge base's reach).

**Design.** A mode changes what she pays attention to and how she helps, never who she is:
- **survival** (default): food, light before night, the next tool or armor worth making;
- **redstone**: an engineer friend (signal strength, repeater ticks, comparators, quasi-connectivity),
  explains why, suggests the smallest fix, looks up redstone pages first;
- **builder**: notices shapes and materials, suggests details, offers to help build or remember it
  (ties to part one);
- **speedrun**: brief, the next objective and the time, danger only, no small talk or pranks;
  splits (Nether, blaze rods, pearls, eyes, the End, the dragon) from what the snapshot already says.

**auto** (the default setting) follows the activity: building gives builder hints, redstone gives
redstone ones, otherwise survival; speedrun only when you say so. You switch by saying it ("Pip,
speedrun mode", "help me with redstone", "normal mode"). The design doc's profiles (Quiet Expert,
Speedrun Coach) are a mode plus power and chattiness settings.

**Done on this branch**: `brain/kindred/expertise.py` (modes, guidance, which comments a mode keeps,
what to look up, `asked_mode`, `Splits`). Wiring into her prompt and System 0 waits (section 9).

### Activity understanding and a session journal

**What exists elsewhere.** The design doc's open question 4 ("how far can rules go before a vision
model?") has an answer from the bots: rules over actions go a long way (Mindcraft and Voyager read
inventory and nearby blocks, not pixels). Vision models are for describing builds, later.

**Design.** Rules over what you did: what was placed, broken, hit, eaten, gained, weighted by kind
(redstone components, crops, ores and stone, logs, building blocks, hostile mobs), over the last five
minutes, plus where (depth for mining, a box of placed blocks for a building site). The result is a
main activity for modes and nudges, and a short line for her prompt and the journal ("building with
oak planks and glass for 4 minutes, a 7x5 spot, 3 high; a little redstone"). Input: the `youDid`
phrases today; the per-player activity log of the playtest-fixes branch when it lands (with
positions, so building sites become places: item 25's "where the player builds").

**The session journal** is the playtest-fixes branch's session log and whole-session diary (items 23
and 28). What this adds: one activity line every few minutes into that log ("12:40 building at the
cherry cottage; 12:52 mining at y -40, found iron"), so the diary and "what did we do today?" come
from what really happened. Nothing separate is built.

**Done on this branch**: `brain/kindred/activity.py`.

### Goals that survive restarts, routines, goal nudges

**What exists elsewhere.** Voyager's automatic curriculum proposes the next task from what the agent
has and has done; MineColonies' builders list what they still need and the request system follows
it up. In Pip: reminders (also repeating) and standing requests exist, and she proposes little
goals when close, but nothing remembers *your* goals ("full diamond armor", "a castle by the lake").

**Design.** A goal is a short text, optional steps, and an optional check the game can answer
itself (have 24 diamonds; be in the Nether; an advancement), kept per world in the memory store like
her heart. She sees the active ones in her prompt with progress ("9 of 24 diamonds so far"),
notices when they're done ("twenty-four! We did it!"), and nudges rarely: only when you've been idle a
minute, nothing's dangerous, not in quiet mode, 20 minutes apart (40 when the bond is low), never the
same goal twice in a row. **Routines** are repeating reminders, which exist: no new store.

**Done on this branch**: `brain/kindred/goals.py`. Tools (`set_goal`, `goal_progress`, `drop_goal`)
and the nudge in her idle loop wait for the branch (section 9).

## 8. Phase 5: grounded actions and jobs

### What exists elsewhere

| Who | How jobs work | What to take |
|---|---|---|
| [Baritone](https://github.com/cabaletta/baritone) | Moves the *player*: `#goto`, `#mine diamond_ore`, `#farm`, `#follow`, `#explore`, `#build`; processes with goals and A* paths | Nothing to depend on (Pip floats and acts directly, the player keeps their body); its mining order (veins, nearest) and "only what you can reach" |
| [Mindcraft](https://github.com/kolbytn/mindcraft) | Mineflayer bots with skills (collect blocks, craft, smelt, go to, attack) the LLM calls, plus modes | A small set of well-named jobs the AI calls, each reporting a result in words |
| [Voyager](https://arxiv.org/abs/2305.16291) | Writes code for skills, keeps a skill library, retries with feedback | Later: "saved skills" (roadmap Phase 6, code mode) |
| [MineColonies](https://minecolonies.com/wiki/systems/request) | Citizens with jobs; a builder requests materials, couriers bring them from the warehouse, crafters make what's missing | Jobs that say what they need and wait; a crafting chain to fill a request |
| Create's schematicannon | Builds from materials in adjacent chests, stalls when one's missing | Same as above, for building (part one) |
| Vanilla allays | Collect items matching what you gave them, bring them to you or a note block | The gentlest "autonomous helper": collect only what you asked for |

### Design

One job at a time, run a little every server tick so you see it happen and can say "stop"; each job
remembers who asked (their pockets and reach, as the playtest-fixes Builder does), and reports in
words: what it did, what it skipped and why.

- **Grounded tasks in reach** (grounded: 12 blocks; magic: 32): break the tree in front of you exists
  (`harvest`); **mine** some of something: the nearest veins, whole, nearest first, with the tool in
  your hand (it wears; a block needing a better tool stops the job with that reason), drops into
  your pockets; **collect** what's lying around; **craft** a batch from your things with the planner
  (a crafting table or furnace nearby or in your pockets, coal or charcoal for smelting).
- **Walk you somewhere** exists (`guide`), and the playtest-fixes branch makes it work for friends
  and far places.
- **Return your items after death**: her place memory (playtest-fixes) keeps where you died; she
  offers "your things are still there, shall we get them?" and, once you're near (grounded) or from
  anywhere loaded (magic), gathers them into your pockets. Items vanish five minutes after a death,
  so she says so.
- **Trading help**: the nearest villager's real offers (read on the world's game: a client only sees
  them with the screen open), against your pockets: what turns your things into emeralds now, the
  treasures (Mending, diamond gear, bottles o' enchanting) even when you can't afford them yet, what's
  sold out. She says it simply; the knowledge base explains trading halls and curing discounts.
- **Autonomous helpers** (the design's open question): option 1 first, her doing the job herself in
  grounded style. Repeating jobs ("keep the farm harvested", "collect the mob farm's drops") are a
  job plus a repeating reminder or standing request, run while you're near, never while you're
  away, and logged. Summoning vanilla helpers (an allay to collect, a golem to guard) stays an
  all-powerful, off-by-default option for later; it adds entities to the world, which nothing else
  of hers does.

**Done on this branch**: `mod/.../job/` (`Dig` with tests, `Jobs` runner: mine, collect, craft,
return items, stop, status), `mod/.../trade/` (`TradeAdvice` with tests, `VillagerTrades`).

### Order and estimates

| # | Step | Depends on | Estimate |
|---|---|---|---|
| P4.1 | Wire the crafting planner: a `craft_help` answer ("what am I missing for a piston?") through the mod | playtest-fixes merged (Actions, tools) | 0.5 day |
| P4.2 | Activity in her prompt and the session log; the per-player log as input | playtest-fixes merged | 0.5 day |
| P4.3 | Expert modes in her prompt and System 0 ("speedrun mode"), speedrun splits spoken | P4.2 | 1 day |
| P4.4 | Shared goals: tools, prompt, checks, nudges in the idle loop | playtest-fixes merged | 1 day |
| P5.1 | Jobs wired (`job` action and tool), sandbox-tested: mine, collect, craft, stop | P4.1 | 1 day |
| P5.2 | Return items after death, from the death place memory | P5.1 + places (playtest-fixes) | 0.5 day |
| P5.3 | Trading help wired (`trades` action, she reads the offers when you look at a villager) | playtest-fixes merged | 0.5 day |
| P5.4 | Repeating jobs near you (farm, mob farm drops), as standing requests | P5.1 | 1 day |
| later | Materials from a chest you point at; summoned helpers (off by default) | — | — |

About 6 days, after the blueprint steps or interleaved with them: P4.1 and P5.1 share the
planner with grounded blueprint building (the material list and crafting what's missing).

## 9. What's implemented for Phases 4 and 5, and what waits

| Where | What | Tests |
|---|---|---|
| `mod/.../craft/CraftPlanner`, `Recipe` | The whole crafting tree from your pockets: steps in order, what's used, what's missing, stations, the inventory after; picks the alternative that leaves least to gather, mixes accepted items (1 oak + 2 birch planks), uses spares, ends recipe loops (ingots and blocks), bounded | `CraftPlannerTest` (9) |
| `mod/.../craft/GameRecipes` | The game's crafting and smelting recipes as `Recipe`s; your pockets as counts (damaged or enchanted items never used up); carrying a plan out with real items | compiles; not run in a game |
| `mod/.../job/Dig` | Which blocks a mining job takes: whole veins, nearest first, within the radius; names to block kinds ("iron", "diamonds", "logs") | `DigTest` (4) |
| `mod/.../job/Jobs` | The job runner: mine, collect, craft, return items, stop, status; grounded vs magic; never containers, unbreakables or the block under you | compiles; not run in a game |
| `mod/.../trade/TradeAdvice`, `VillagerTrades` | Offers ranked against your pockets with plain lines; reading a villager's real offers, profession and level | `TradeAdviceTest` (3) |
| `brain/kindred/activity.py` | The main activity and a summary line, from `youDid` or structured events | `tests/test_phase4.py` |
| `brain/kindred/goals.py` | Goals per world in the memory store, steps, checks, context, nudges | `tests/test_phase4.py` |
| `brain/kindred/expertise.py` | Modes, guidance, which comments each keeps, `asked_mode`, speedrun `Splits` | `tests/test_phase4.py` (13 in all) |

**Waits for the playtest-fixes branch** (it owns the files that wire things in: `act/Actions.java`,
`act/Builder.java`, `KindredSpiritClient.java`, `brain/kindred/server.py`, `tools.py`, `mind.py`,
`intents.py`, `sessionlog.py`):
- `Jobs.tick(server)` next to `Builder.tick`; a `job` action (mine, collect, craft, return_items,
  stop, status) and a `trades` action in Actions; a `craft_help` action returning the plan;
- brain tools: `job`, `craft_help`, `trades`, `set_goal`, `goal_progress`, `drop_goal`, `set_mode`;
- her prompt: `activity.summary()`, `expertise.guidance()`, `goals.context()`; `expertise.allows()`
  around her own comments; `goals.nudge()` in the idle loop; `goals.check()` and `Splits.update()` on
  each snapshot; System 0 words for "speedrun mode" (`asked_mode`);
- the per-player activity log as `Activity.add(...)` input; return items from the death place;
- an activity line every few minutes into the session log.

## Sources

- [Structure file](https://minecraft.wiki/w/Structure_file), [Structure Block](https://minecraft.wiki/w/Structure_Block), [Commands/place](https://minecraft.wiki/w/Commands/place), [Schematic file format](https://minecraft.wiki/w/Schematic_file_format) (Minecraft Wiki)
- [Sponge Schematic Specification](https://github.com/SpongePowered/Schematic-Specification): [v2](https://github.com/SpongePowered/Schematic-Specification/blob/master/versions/schematic-2.md), [v3](https://github.com/SpongePowered/Schematic-Specification/blob/master/versions/schematic-3.md)
- Litematica: [Modrinth page](https://modrinth.com/mod/litematica), source ([sakura-ryoko/litematica](https://github.com/sakura-ryoko/litematica), branch 26.3: `LitematicaSchematic`, `LitematicaBlockStateContainer`, `LitematicaBitArray`), [Litemapy format notes](https://litemapy.readthedocs.io/en/latest/litematics.html)
- Baritone: [USAGE.md](https://github.com/cabaletta/baritone/blob/master/USAGE.md), [Settings](https://github.com/cabaletta/baritone/blob/master/src/api/java/baritone/api/Settings.java), [DefaultSchematicFormats (1.21.1)](https://github.com/cabaletta/baritone/blob/1.21.1/src/main/java/baritone/utils/schematic/format/DefaultSchematicFormats.java), [BuilderProcess](https://github.com/cabaletta/baritone/blob/master/src/main/java/baritone/process/BuilderProcess.java)
- Create: [Saving a Schematic](https://github.com/Creators-of-Create/Create/wiki/Saving-a-Schematic), [Printing a Schematic](https://github.com/Creators-of-Create/Create/wiki/Printing-a-Schematic); [createmod.com terms](https://createmod.com/terms-of-service), [rules](https://createmod.com/rules)
- Building Gadgets: [CurseForge](https://www.curseforge.com/minecraft/mc-mods/building-gadgets), [wiki: Template](https://github.com/Direwolf20-MC/BuildingGadgets/wiki/Template)
- Phases 4 and 5: [minecraft-data](https://github.com/PrismarineJS/minecraft-data), [prismarine-recipe](https://github.com/PrismarineJS/prismarine-recipe), [Mindcraft](https://github.com/kolbytn/mindcraft), [Voyager (arXiv 2305.16291)](https://arxiv.org/abs/2305.16291), [MineColonies request system](https://minecolonies.com/wiki/systems/request), [Baritone](https://github.com/cabaletta/baritone)
- Build libraries: [Planet Minecraft Terms of Use](https://www.planetminecraft.com/terms_of_use/), [minecraft-schematics.com Terms](https://www.minecraft-schematics.com/terms/), [GrabCraft terms](https://www.grabcraft.com/terms-of-use-privacy-policy/)

Not verified: Create's upload cap default (from a hosting guide), whether Planet Minecraft offers any
developer API (none found), and `iron_chain` as the newer name of `chain` (from memory of 1.21.9).
