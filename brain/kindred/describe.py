"""Turns a game snapshot from the mod into a few plain lines the AI can read."""


def nice(item_id):
    """"minecraft:oak_log" -> "oak log"; keeps the namespace for other mods' items."""
    if not item_id:
        return ""
    ns, colon, name = item_id.partition(":")
    if not colon:
        return ns.replace("_", " ")
    name = name.replace("_", " ")
    return name if ns == "minecraft" else "%s (%s)" % (name, ns)


def clock(time_of_day):
    """Minecraft day ticks (0 = 6:00) -> ("14:30", "afternoon")."""
    minutes = int((time_of_day % 24000) / 1000 * 60 + 6 * 60) % (24 * 60)
    h, m = divmod(minutes, 60)
    if 5 <= h < 7:
        part = "dawn"
    elif 7 <= h < 12:
        part = "morning"
    elif 12 <= h < 17:
        part = "afternoon"
    elif 17 <= h < 19:
        part = "evening"
    else:
        part = "night"
    return "%02d:%02d" % (h, m), part


def hearts(points):
    v = points / 2
    return ("%d" % v) if v == int(v) else ("%.1f" % v)


def where_words(direction):
    return {
        "ahead": "ahead of you", "behind": "behind you", "left": "on your left", "right": "on your right",
        "ahead-left": "ahead on your left", "ahead-right": "ahead on your right",
        "behind-left": "behind you on the left", "behind-right": "behind you on the right", "here": "right here",
    }.get(direction, direction or "nearby")


def describe(s):
    if not s or "health" not in s:
        return "The player is not in a world right now."
    w, t = s.get("where", {}), s.get("time", {})
    lines = []
    if s.get("recent"):
        lines.append("Just happened: " + "; ".join(s["recent"]) + ".")
    lines.append("Health %s/%s hearts, hunger %s/10, armor %s. Game mode: %s." % (
        hearts(s.get("health", 0)), hearts(s.get("maxHealth", 20)), hearts(s.get("food", 0)),
        s.get("armor", 0), s.get("gamemode", "?")))
    dim = (w.get("dimension") or "").replace("minecraft:", "").replace("_", " ")
    light = w.get("light", 15)
    seeing = "bright" if light >= 11 else "dim" if light >= 6 else "dark, hard to see" if light >= 2 else "pitch dark"
    lines.append("Place: %s, biome %s, x %s y %s z %s, facing %s, %s, %s." % (
        dim, nice(w.get("biome")), w.get("x"), w.get("y"), w.get("z"), w.get("facing"),
        "under the open sky" if w.get("skyVisible") else "underground or under a roof", seeing))
    hhmm, part = clock(t.get("timeOfDay", 0))
    weather = "thunderstorm" if t.get("thundering") else "rain" if t.get("raining") else "clear"
    lines.append("Time: day %s, %s (%s), weather %s." % (t.get("day", "?"), part, hhmm, weather))
    hold = nice(s.get("holding")) or "nothing"
    off = nice(s.get("offhand"))
    wearing = ", ".join(nice(a) for a in s.get("wearing") or []) or "no armor"
    lines.append("Holding %s%s. Wearing %s." % (hold, (", off hand " + off) if off else "", wearing))
    inv = s.get("inventory") or {}
    if inv:
        lines.append("Inventory: " + ", ".join("%d %s" % (n, nice(i)) for i, n in list(inv.items())[:20]) + ".")
    else:
        lines.append("Inventory: empty.")
    look = s.get("lookingAt") or {}
    if look.get("block"):
        lines.append("Looking at: %s, %s blocks away." % (nice(look["block"]), look.get("distance", "?")))
    elif look.get("entity"):
        lines.append("Looking at: a %s." % nice(look["entity"]))
    mobs = s.get("hostiles") or []
    if mobs:
        lines.append("Hostile mobs near: " + "; ".join(
            "%s %s blocks %s" % (nice(m.get("type")), int(m.get("distance", 0)), where_words(m.get("direction")))
            for m in mobs[:6]) + ".")
    else:
        lines.append("No hostile mobs nearby.")
    for h in s.get("hazards") or []:
        kind = {"lava": "lava", "drop": "a drop of %s blocks" % h.get("depth"), "drop_water": "a drop of %s blocks "
                "into water" % h.get("depth"), "drop_lava": "a drop of %s blocks into lava" % h.get("depth")}.get(h["kind"])
        lines.append("Danger ahead: %s, %s blocks %s." % (kind, h.get("distance"), where_words(h.get("direction"))))
    animals = s.get("animals") or []
    if animals:  # grouped: "3 sheep, nearest 14 blocks ahead on your left"
        groups = {}
        for a in animals:
            groups.setdefault(nice(a.get("type")), []).append(a)
        parts = []
        for kind, group in sorted(groups.items(), key=lambda g: min(a.get("distance", 99) for a in g[1]))[:6]:
            near = min(group, key=lambda a: a.get("distance", 99))
            babies = sum(1 for a in group if a.get("baby"))
            pets = [a.get("name") or "a pet" for a in group if a.get("tamed")]
            parts.append("%d %s%s, nearest %d blocks %s%s" % (
                len(group), kind + ("s" if len(group) > 1 and not kind.endswith(("s", "sheep", "fish")) else ""), " (%d babies)" % babies if babies else "", int(near.get("distance", 0)),
                where_words(near.get("direction")), " (your pet: %s)" % ", ".join(pets) if pets else ""))
        lines.append("Animals within 32 blocks: " + "; ".join(parts) + ".")
    else:
        lines.append("No animals within 32 blocks.")
    fx = s.get("effects") or []
    if fx:
        lines.append("Effects: " + ", ".join("%s %s (%ss)" % (nice(e.get("id")), e.get("level"), e.get("seconds"))
                                             for e in fx) + ".")
    if s.get("onFire"):
        lines.append("The player is ON FIRE.")
    if s.get("air", 300) < s.get("maxAir", 300):
        left = s.get("air", 0) / max(1, s.get("maxAir", 300))
        lines.append("The player is underwater, %s." % ("almost out of air!" if left < 0.3 else "running out of air"
                                                          if left < 0.7 else "holding their breath"))
    return "\n".join(lines)
