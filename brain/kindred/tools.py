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
    "locate": _fn("locate", "Find the nearest structure or biome in this world (uses the world seed, any distance). "
                  "Structures: " + STRUCTURES + ". Or any biome, like cherry_grove or mushroom_fields.",
                  {"what": {"type": "string"}}, ["what"]),
    "guide": _fn("guide", "Float ahead and lead the player to a place until they arrive. Usually call it with no "
                 "arguments: it goes to what you just found or located. Or set 'to' to the name of a place you "
                 "remember (like 'base'). Give x/z only if the player said exact coordinates.",
                 {"to": {"type": "string", "description": "'last' (default) or a remembered place name"},
                  "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"}}),
    "stop_guide": _fn("stop_guide", "Stop leading the way and float beside the player again."),
    "protect": _fn("protect", "Push every hostile mob within 8 blocks away from the player (no damage). "
                   "Use when they're in danger or ask for help with monsters."),
    "place_torch": _fn("place_torch", "Place a torch at or right next to the player's feet (in grounded style it "
                       "uses one of their torches)."),
    "give_item": _fn("give_item", "Make items appear in the player's inventory (magic). Use Minecraft item ids.",
                     {"item": {"type": "string", "description": "e.g. bread, torch, oak_log, diamond_pickaxe"},
                      "count": {"type": "integer", "description": "how many, up to four stacks"}},
                     ["item"]),
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
    _fn("forget", "Forget facts or named places that mention something, when the player asks you to forget.",
        {"about": {"type": "string"}}, ["about"]),
    _fn("name_place", "Remember where the player is standing under a name, when they say things like "
        "'this is my base' or 'remember this spot'.", {"name": {"type": "string"}}, ["name"]),
]


def for_abilities(abilities):
    """The tool list to send the AI, given what the mod says is allowed."""
    return [ABILITY_TOOLS[a] for a in abilities if a in ABILITY_TOOLS] + MEMORY_TOOLS
