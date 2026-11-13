"""Tools the AI can call, in the OpenAI function format (the gateway passes them to any model).

The AI only ever sees the tools the player's settings allow (the mod sends that list as
"abilities"), and the mod checks again before acting. Memory tools are always there.
"""

STRUCTURES = ("village, mineshaft, shipwreck, ruined_portal, ocean_ruin, monument, mansion, stronghold, "
              "fortress, bastion, desert_temple, jungle_temple, witch_hut, igloo, outpost, ancient_city, "
              "trail_ruins, trial_chambers, end_city, buried_treasure")


def _fn(name, description, props=None, required=()):
    return {"type": "function", "function": {
        "name": name, "description": description,
        # an empty "properties" object, not a missing one: some models reject tools without it
        "parameters": {"type": "object", "properties": props or {}, "required": list(required)}}}


ABILITY_TOOLS = {
    "find_ore": _fn("find_ore", "Find the nearest ore of a kind within 24 blocks of the player (what the game has "
                    "loaded). Use when they ask where to find diamonds, iron, coal, etc.",
                    {"ore": {"type": "string", "description": "diamond, iron, gold, coal, copper, redstone, lapis, emerald, quartz or ancient_debris"}},
                    ["ore"]),
    "find_animal": _fn("find_animal", "Find the nearest animal of a kind (or a villager) within about 96 blocks of "
                        "the player, among what the game has loaded. Use when they look for sheep, cows, horses, "
                        "villagers... Then guide can lead them to it, even as it walks around.",
                        {"animal": {"type": "string", "description": "sheep, cow, pig, chicken, horse, wolf, cat, fox, "
                                    "villager... or 'animal' for any animal"}}, ["animal"]),
    "find_block": _fn("find_block", "Find the nearest block of a kind within about 24 blocks: a flower, a pumpkin, "
                       "a melon, sugar cane, bamboo, a chest, a bed, water, a tree... Use it before leading the player "
                       "to such a thing, then guide.", {"block": {"type": "string", "description": "flower, pumpkin, "
                       "chest, water, tree, sugar cane..."}}, ["block"]),
    "locate": _fn("locate", "Find the nearest structure or biome in this world (uses the world seed, any distance). "
                  "Structures: " + STRUCTURES + ". Or any biome, like cherry_grove or mushroom_fields.",
                  {"what": {"type": "string"}}, ["what"]),
    "guide": _fn("guide", "Float ahead and lead the player to a place until they arrive (they see an arrow and the "
                 "distance on screen). Use it whenever you say 'follow me' or 'this way'. Usually call it with no "
                 "arguments: it goes to what you just found or located (an animal: you follow it as it walks). Or set 'to' to the name of a place you "
                 "remember (like 'base'). Give x/z only if the player said exact coordinates.",
                 {"to": {"type": "string", "description": "'last' (default) or a remembered place name"},
                  "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"}}),
    "stop_guide": _fn("stop_guide", "Stop leading the way and float beside the player again."),
    "protect": _fn("protect", "Push every hostile mob within 8 blocks away from the player (no damage), or from "
                   "another player here if 'to' names them. Use when they're in danger or ask for help with monsters. "
                   "It also gives a friend who just hit the player a playful shove. With poke=true and 'to' a player's "
                   "name: a playful poke on that player (a little shove and a puff, no harm), when asked to poke, prod, "
                   "boop, push back or playfully hit someone.",
                   {"to": {"type": "string", "description": "another player's name; empty = the player"},
                    "poke": {"type": "boolean", "description": "true: poke the player named in 'to' (playful, no harm)"}}),
    "harvest": _fn("harvest", "Break what the player is looking at, within 6 blocks: a whole tree (all its logs) "
                   "if they look at a log, else that one block. What drops goes into their inventory, as if mined "
                   "with what they hold. Use when they ask you to chop a tree, cut wood, mine or break a block. "
                   "Never for animals, chests or anything that holds things."),
    "build": _fn("build", "Build with the player, starting at the spot they're looking at (or just in front of them) "
                 "and going forward (the way they face) and to their right. In grounded style each block comes from "
                 "their inventory (you place what they have) and what you clear goes into it; in magic style it's free "
                 "and fast. Shapes: place (ONE block or item where they look, placed properly: a campfire, a bed, a "
                 "chest, a door, a lantern...), pillar (a stack, 'height' high), corners (a pillar on each corner of "
                 "'width' x 'length'), wall (a row 'width' long, 'height' high), floor ('width' x 'length', flat), "
                 "outline (the border of 'width' x 'length', 'height' high, like a pen), house (floor, walls, a door, a "
                 "roof, sized for 'people'), portal (a nether portal: 10 obsidian, then lit), clear (everything in "
                 "'width' x 'length' goes, from where they stand up, or above 'level'), end_portal (a working end portal: twelve frames with eyes around it, open to the End; magic only), farm (a crop farm: tilled ground with water in the middle and crops planted, 'width' x 'length', 9 x 9 by default; 'block' is the crop: wheat, carrots, potatoes or beetroots), flatten (clear, and fill holes "
                 "in the ground at that level with 'block'). 'stop' stops. Use the block they named, in this or an "
                 "earlier message. If what they want isn't one of these shapes, say you can't build that yet: never "
                 "build something else and call it done. If the size isn't clear, ask first.",
                 {"shape": {"type": "string", "enum": ["place", "pillar", "corners", "wall", "floor", "outline", "house",
                                                       "portal", "end_portal", "farm", "clear", "flatten", "stop"]},
                  "block": {"type": "string", "description": "the block or item, e.g. cobblestone, oak_planks, campfire, "
                            "red_bed; empty = the one in their hand (or the one they have most of)"},
                  "height": {"type": "integer"}, "width": {"type": "integer", "description": "to their right"},
                  "length": {"type": "integer", "description": "forward"},
                  "people": {"type": "integer", "description": "house: how many it's for"},
                  "level": {"type": "integer", "description": "clear / flatten: a Y level ('above Y 64': 64)"}}, ["shape"]),
    "blueprint": _fn("blueprint", "Build a whole house where the player is looking: a cottage made for how many people "
                     "it's for (a bed each, a chest, a crafting table, a furnace, windows, a door facing them, a stair roof), "
                     "or a blueprint file by its exact name from find_blueprint (a village house, an igloo, a ship...). For a "
                     "house in general ('a house', 'a cozy cottage for three'), the cottage; for a particular kind ('a "
                     "desert house', 'the plains smithy', 'a ship', 'something big'), look it up with find_blueprint first, "
                     "and if several fit or you're not sure, ask which one before building; confirm a big one first. In "
                     "magic style it rises in a few seconds; in grounded style it needs the materials in their pockets, and "
                     "if something's missing you get the list (and what they could craft): tell them what to gather. It "
                     "never builds over something built: then say so. 'stop' stops.",
                     {"what": {"type": "string", "description": "'cottage' (default), or a schematic's name, or 'stop'"},
                      "people": {"type": "integer", "description": "how many it's for (a bed each)"},
                      "wood": {"type": "string", "description": "oak (default), spruce, birch, jungle, acacia, dark_oak, "
                               "cherry or mangrove"}}),
    "job": _fn("job", "Work that takes a while, done with your hands, near the player: mine some of something (whole "
               "veins, nearest first, with the tool in their hand: a stone pickaxe can't take diamonds), chop the tree "
               "they look at (all its logs), collect the items lying around, craft something from what they carry, or "
               "get their things back where they died. What it gets goes into their pockets. You get the result when it "
               "starts; 'status' says how it went, 'stop' stops. Kinds: mine (what: iron, coal, copper, gold, diamond, "
               "redstone, lapis, emerald, stone, logs...; count), chop, collect, craft (what: an item id; count), "
               "return_items, status, stop.",
               {"kind": {"type": "string", "enum": ["mine", "chop", "collect", "craft", "return_items", "status", "stop"]},
                "what": {"type": "string", "description": "mine: the block or ore; craft: the item, e.g. furnace, torch"},
                "count": {"type": "integer"}}, ["kind"]),
    "craft_help": _fn("craft_help", "Work out how to make something from what the player has right now: the steps "
                      "(planks, then sticks, then the pickaxe), what they're missing, and whether they need a crafting "
                      "table or a furnace. Use it for 'what am I missing for a piston?', 'can I make a bed?', 'how do I "
                      "craft a furnace?'. It reads the game's own recipes, exactly.",
                      {"item": {"type": "string", "description": "the item id, e.g. piston, furnace, white_bed"},
                       "count": {"type": "integer"}}, ["item"]),
    "trades": _fn("trades", "Read the trades of the nearest villager (within 10 blocks), checked against what the player "
                  "carries: what they can sell now for emeralds, the good ones (Mending, diamond gear) even if they can't "
                  "afford them yet, what's sold out. Use it when they ask what a villager sells or buys, or for good trades."),
    "place_torch": _fn("place_torch", "Place a torch at or right next to the player's feet (in grounded style it "
                       "uses one of their torches)."),
    "give_item": _fn("give_item", "Make items appear in someone's inventory (magic): the player's, or another "
                     "player's here if 'to' names them. Use Minecraft item ids.",
                     {"item": {"type": "string", "description": "e.g. bread, torch, oak_log, diamond_pickaxe"},
                      "count": {"type": "integer", "description": "how many, up to four stacks"},
                      "to": {"type": "string", "description": "another player's name; empty = the player"}},
                     ["item"]),
    "give_effect": _fn("give_effect", "Give someone a magic effect for a few minutes (haste, night_vision, speed, "
                       "regeneration, fire_resistance, water_breathing, jump_boost, strength, resistance, "
                       "slow_falling, invisibility), or 'health' (back to full hearts) or 'food' (not hungry).",
                       {"effect": {"type": "string"},
                        "to": {"type": "string", "description": "another player's name; empty = the player"}},
                       ["effect"]),
    "command": _fn("command", "Run one of Minecraft's own commands (the old words the world obeys), as the player, "
                   "from where they stand; the game's exact answer comes back. Use it when it's the simplest way: building "
                   "in one go, gifts, enchanting, effects, and (all-powerful) mobs, teleporting, time, weather. Only what "
                   "they asked for; for another player only if that player asked, or playful things the player asked "
                   "for. Never @e, @a or @r; ~ coordinates are from the player (~ ~ ~ = their feet, ^ ^ ^3 = 3 ahead).\n"
                   "  /fill <x1 y1 z1> <x2 y2 z2> <block> [hollow|outline|replace|keep|destroy]  e.g. /fill ~-8 ~ ~-8 ~8 ~10 ~8 "
                   "air (clear everything around, from their feet up), /fill ~-6 ~-1 ~-6 ~6 ~-1 ~6 dirt (flatten the ground), "
                   "/fill ~2 ~ ~2 ~8 ~4 ~8 oak_planks hollow (a room), /fill ~-10 ~-3 ~-10 ~10 ~6 ~10 air replace fire (put out a fire)\n"
                   "  /setblock <x y z> <block>[states]  e.g. /setblock ^ ^ ^2 campfire\n"
                   "  /give <who> <item>[components] [count]  Minecraft 1.21 writes enchanted items like this: "
                   "/give @s netherite_sword[enchantments={levels:{sharpness:5,unbreaking:3,mending:1}}] (never the old "
                   "{Enchantments:[...]} form)\n"
                   "  /enchant <who> <enchantment> [level]  only the item in their hand: ask them to hold the tool first\n"
                   "  /item modify entity @s weapon.mainhand {function:\"minecraft:set_damage\",damage:1}  repairs the "
                   "item in their hand like new\n"
                   "  /xp add @s <n> levels  (all-powerful) experience levels, e.g. 'max XP': /xp add @s 100 levels\n"
                   "  /clone <x1 y1 z1> <x2 y2 z2> <x y z>   copy a build\n"
                   "  /give <player> <item> [count]  e.g. /give Walid golden_apple 2\n"
                   "  /enchant <player> <enchantment> [level]  the item in their hand, e.g. /enchant Walid efficiency 3\n"
                   "  /effect give <player> <effect> [seconds] [level]  e.g. /effect give Walid speed 60 1; harmful ones "
                   "(slowness, poison, levitation...) only if asked for by name, at most 10 s\n"
                   "  /particle <name> <x y z>, /playsound <sound> master <player>  for fun\n"
                   "  /locate structure <id> | biome <id>\n"
                   "  all-powerful only: /summon <mob> <x y z> (a few, never dangerous ones), /tp <player> <x y z | player>, "
                   "/time set day|noon|night|midnight, /weather clear|rain|thunder, /spawnpoint <player>",
                   {"command": {"type": "string", "description": "the command, e.g. /fill ~-3 ~ ~-3 ~3 ~ ~3 stone"}},
                   ["command"]),
    "find_flat": _fn("find_flat", "Find the flattest open, dry ground nearby (about 96 blocks around, what the world has loaded) "
                     "for something to build: 'a flat field', 'flat ground for a house'. Then guide leads there.",
                     {"size": {"type": "integer", "description": "how big a square, in blocks (12 by default)"}}),
    "find_player": _fn("find_player", "Find another player here in the world (a friend on the player's LAN world) "
                       "by name, even said roughly. Then guide can lead the way to them as they move.",
                       {"name": {"type": "string", "description": "their name, or 'player' for the player you live beside"}},
                       ["name"]),
    "follow_player": _fn("follow_player", "Float beside someone else for a while (another player here, when the "
                         "player asks you to stay with them), or 'me' to come back to the player.",
                         {"name": {"type": "string", "description": "a player's name, or 'me'"}}, ["name"]),
    "set_time": _fn("set_time", "Change the time of day for the whole world.",
                    {"time": {"type": "string", "enum": ["sunrise", "day", "noon", "sunset", "night", "midnight"]}},
                    ["time"]),
    "set_weather": _fn("set_weather", "Change the weather.",
                       {"weather": {"type": "string", "enum": ["clear", "rain", "thunder"]}}, ["weather"]),
}

MEMORY_TOOLS = [
    _fn("remember", "Remember something for good: about the player (what they like, their name, goals, what they "
        "asked you to remember), about yourself, or about this world. Short sentences.",
        {"fact": {"type": "string"},
         "about": {"type": "string", "enum": ["player", "self", "world"], "description": "default: player"}},
        ["fact"]),
    _fn("set_reminder", "Remind the player of something later. 'when' in plain words: 'in 10 minutes', 'in an hour', "
        "'at night', 'in the morning', 'next time we play', 'every night', 'every 20 minutes'.",
        {"text": {"type": "string", "description": "what to remind them of"}, "when": {"type": "string"}},
        ["text", "when"]),
    _fn("cancel_reminder", "Cancel reminders that mention something.", {"about": {"type": "string"}}, ["about"]),
    _fn("standing_request", "The player wants you to do something every time, on your own: 'always protect me' "
        "(what=protect) or 'tell me when we're near diamonds' (what=notify_ore, detail=the ore). Protection can be for "
        "a friend here ('follow and defend Walid': for=Walid) or for everyone ('protect us from everything': "
        "for=everyone). Or stop one.",
        {"what": {"type": "string", "enum": ["protect", "notify_ore"]},
         "detail": {"type": "string", "description": "for notify_ore: which ore"},
         "for": {"type": "string", "description": "protect: a friend's name, or 'everyone'; empty = the player"},
         "stop": {"type": "boolean", "description": "true to stop doing it"}}, ["what"]),
    _fn("listen_more", "Listen more closely to what the world remembers about the guide or thing you were just told "
        "about: the next part (what='next'), or a part by name (what='Step two', 'Collection system'...). Use it when "
        "what you know stops before what you need, instead of guessing.",
        {"what": {"type": "string", "description": "'next' or the name of a part"}}, ["what"]),
    _fn("forget", "Forget facts or named places that mention something, when the player asks you to forget.",
        {"about": {"type": "string"}}, ["about"]),
    _fn("name_place", "Remember where the player is standing under a name, when they say things like "
        "'this is my base' or 'remember this spot'. Use the full name they give ('pumpkin base', not 'base'). If "
        "that name is already used somewhere else it won't move it unless replace is true (only when they said so).",
        {"name": {"type": "string"}, "replace": {"type": "boolean", "description": "move the existing place here"}},
        ["name"]),
    _fn("rename_place", "Give a remembered place another name ('no, call it my pumpkin base').",
        {"old": {"type": "string"}, "new": {"type": "string"}}, ["old", "new"]),
]


FIND_BLUEPRINT = _fn("find_blueprint", "Look up the blueprints (buildings saved as files) you can build, by what they "
                     "are: Minecraft's own village buildings for each biome (plains, desert, savanna, taiga, snowy: small "
                     "and bigger houses, workshops like a smithy, a library, a temple, crop fields and animal pens, wells), "
                     "an igloo, ruined portals, shipwrecks, a pillager watchtower, circles to build on, and any the player "
                     "added. Search the way they asked ('a small desert house', 'something big', 'a house for three', "
                     "'the plains smithy', 'a ship'); you get a few, best first, each with what it is in plain words and "
                     "its size. If several fit or you aren't sure which they mean, describe the two or three best in a few "
                     "words (how they look, how big) and ask which one before building; for a big one (marked big), "
                     "confirm first. Then build it with blueprint, giving its exact name as 'what'.",
                     {"query": {"type": "string", "description": "what they asked for, in their words; empty = what "
                                "kinds there are"}})


def for_abilities(abilities):
    """The tool list to send the AI, given what the mod says is allowed."""
    extra = [FIND_BLUEPRINT] if "blueprint" in abilities else []
    return [ABILITY_TOOLS[a] for a in abilities if a in ABILITY_TOOLS] + extra + MEMORY_TOOLS
