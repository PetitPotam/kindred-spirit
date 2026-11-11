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

    /** Compass word for a direction on the map (north is -Z in Minecraft). */
    public static String compass(double dx, double dz) {
        String[] n = {"south", "south-west", "west", "north-west", "north", "north-east", "east", "south-east"};
        double a = Math.toDegrees(Math.atan2(-dx, dz)); // 0 = south (+Z), 90 = west, like Minecraft yaw
        return n[(int) Math.floorMod(Math.round(a / 45.0), 8)];
    }
}
