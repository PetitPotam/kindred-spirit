"""Ready-made snapshots, shaped exactly like the ones the mod sends."""
import copy

CALM = {
    "type": "snapshot", "health": 20.0, "maxHealth": 20.0, "food": 20, "saturation": 5.0, "armor": 0,
    "air": 300, "maxAir": 300, "onFire": False, "gamemode": "survival", "effects": [],
    "where": {"x": 12, "y": 70, "z": -30, "dimension": "minecraft:overworld", "biome": "minecraft:plains",
              "facing": "north", "yaw": 180.0, "skyVisible": True, "light": 15},
    "time": {"day": 2, "timeOfDay": 6000, "raining": False, "thundering": False},
    "holding": "minecraft:iron_pickaxe", "offhand": "", "inventory": {"minecraft:cobblestone": 32, "minecraft:oak_log": 12},
    "wearing": [], "lookingAt": {"block": "minecraft:oak_log", "distance": 3.2}, "hostiles": [],
}


def snap(**changes):
    s = copy.deepcopy(CALM)
    for k, v in changes.items():
        s[k] = v
    return s


def creeper(distance=5.0, direction="behind"):
    return {"type": "minecraft:creeper", "distance": distance, "direction": direction, "above": 0.0}


def zombie(distance=10.0, direction="ahead"):
    return {"type": "minecraft:zombie", "distance": distance, "direction": direction, "above": 0.0}
