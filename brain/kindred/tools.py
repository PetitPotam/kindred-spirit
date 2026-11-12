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
                   "another player here if 'to' names them. Use when they're in danger or ask for help with monsters.",
                   {"to": {"type": "string", "description": "another player's name; empty = the player"}}),
    "harvest": _fn("harvest", "Break what the player is looking at, within 6 blocks: a whole tree (all its logs) "
                   "if they look at a log, else that one block. What drops goes into their inventory, as if mined "
                   "with what they hold. Use when they ask you to chop a tree, cut wood, mine or break a block. "
                   "Never for animals, chests or anything that holds things."),
    "build": _fn("build", "Build with the player: place blocks in a shape, one by one, a few per second, starting "
                 "at the spot they're looking at (or just in front of them) and going forward (the way they face) "
                 "and to their right. In grounded style each block comes from their inventory (you place what they "
                 "have). Shapes: pillar (a stack, 'height' high), corners (a pillar on each corner of a rectangle "
                 "'width' x 'length', 'height' high), wall (a row 'width' long, 'height' high), floor ('width' x "
                 "'length', flat), outline (the border of 'width' x 'length', 'height' high, like a pen or room). "
                 "'stop' stops a build. One block where they look: a pillar of height 1. If the size they want isn't "
                 "clear, ask before building. At most 256 blocks.",
                 {"shape": {"type": "string", "enum": ["pillar", "corners", "wall", "floor", "outline", "stop"]},
                  "block": {"type": "string", "description": "the block to use, e.g. cobblestone, oak_planks; empty = "
                            "the block in their hand (or the one they have most of)"},
                  "height": {"type": "integer"}, "width": {"type": "integer", "description": "to their right"},
                  "length": {"type": "integer", "description": "forward"}}, ["shape"]),
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
        "a friend here ('follow and defend Robin': for=Robin) or for everyone ('protect us from everything': "
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


def for_abilities(abilities):
    """The tool list to send the AI, given what the mod says is allowed."""
    return [ABILITY_TOOLS[a] for a in abilities if a in ABILITY_TOOLS] + MEMORY_TOOLS
