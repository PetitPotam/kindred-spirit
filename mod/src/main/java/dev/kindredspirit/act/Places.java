package dev.kindredspirit.act;

import java.util.Locale;

/** Small word helpers for finding things; no Minecraft classes, so they are unit-tested. */
public final class Places {
    private Places() {}

    /** "Diamonds", "diamond ore", "minecraft:diamond_ore" -> "diamond". */
    public static String oreKind(String ore) {
        String o = ore.toLowerCase(Locale.ROOT).replace("minecraft:", "").replace("deepslate_", "")
                .replace(" ore", "").replace("_ore", "").trim().replace(' ', '_');
        if (o.endsWith("s") && !o.equals("ancient_debris")) o = o.substring(0, o.length() - 1);
        return o;
    }

    /** Is this block (its id without "minecraft:") an ore of that kind? Deepslate variants count. */
    public static boolean isOre(String path, String kind) {
        if (kind.equals("ancient_debris") || kind.equals("debris") || kind.equals("netherite")) return path.equals("ancient_debris");
        if (kind.equals("quartz")) return path.equals("nether_quartz_ore");
        if (kind.equals("gold")) return path.equals("gold_ore") || path.equals("deepslate_gold_ore") || path.equals("nether_gold_ore");
        return path.equals(kind + "_ore") || path.equals("deepslate_" + kind + "_ore");
    }

    /** "Sheeps", "a cow", "minecraft:wolves" -> "sheep", "cow", "wolf". */
    public static String creatureKind(String what) {
        String w = what.toLowerCase(Locale.ROOT).replace("minecraft:", "").trim();
        w = w.replaceFirst("^(an?|the|some) ", "").replace(' ', '_');
        return switch (w) {
            case "wolves" -> "wolf";
            case "sheeps" -> "sheep";
            case "foxes" -> "fox";
            case "mice", "animals", "animal", "creatures" -> "animal";
            case "villagers", "people", "villager" -> "villager";
            default -> w.endsWith("ies") ? w.substring(0, w.length() - 3) + "y"
                    : w.endsWith("s") && !w.endsWith("ss") ? w.substring(0, w.length() - 1) : w;
        };
    }

    /** Is this entity (its id without "minecraft:") the kind asked for? "animal" means any animal. */
    public static boolean isCreature(String path, String kind) {
        if (kind.equals("animal")) return ANIMALS.contains(path);
        if (kind.equals("villager")) return path.equals("villager") || path.equals("wandering_trader");
        if (kind.equals("horse")) return path.equals("horse") || path.equals("donkey") || path.equals("mule");
        return path.equals(kind);
    }

    static final java.util.Set<String> ANIMALS = java.util.Set.of("sheep", "cow", "pig", "chicken", "horse", "donkey",
            "mule", "rabbit", "goat", "llama", "fox", "wolf", "cat", "ocelot", "parrot", "panda", "bee", "turtle",
            "frog", "axolotl", "camel", "sniffer", "armadillo", "mooshroom", "polar_bear", "strider");

    /** Compass word for a direction on the map (north is -Z in Minecraft). */
    public static String compass(double dx, double dz) {
        String[] n = {"south", "south-west", "west", "north-west", "north", "north-east", "east", "south-east"};
        double a = Math.toDegrees(Math.atan2(-dx, dz)); // 0 = south (+Z), 90 = west, like Minecraft yaw
        return n[Math.floorMod(Math.round(a / 45.0), 8)];
    }
}
