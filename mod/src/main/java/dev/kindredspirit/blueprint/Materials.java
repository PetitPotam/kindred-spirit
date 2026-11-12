package dev.kindredspirit.blueprint;

import java.util.Map;
import java.util.Set;

/**
 * What a placed block costs in items, for the material list she reads out in grounded style ("we'll
 * need 120 oak planks, 30 glass, a door") and for taking blocks from the player's pockets.
 *
 * <p>Most blocks are their own item. The exceptions, from how the game places things: the second half
 * of a door, a bed or a tall flower comes with the first; a double slab is two slabs; a torch on a wall
 * is a torch, a sign on a wall a sign; crops are their seeds; a potted flower is a pot and the flower;
 * water and lava are buckets (only their sources: flowing water comes by itself); candles, sea pickles,
 * snow layers and turtle eggs count as many as there are. Things nobody can carry (fire, portals, a
 * moving piston, the barrier and light blocks) cost nothing and aren't placed from materials.
 */
public final class Materials {
    private Materials() {}

    private static final Set<String> NOTHING = Set.of(
            "air", "cave_air", "void_air", "structure_void", "fire", "soul_fire", "moving_piston", "piston_head",
            "nether_portal", "end_portal", "end_gateway", "bubble_column", "frosted_ice", "barrier", "light",
            "jigsaw", "structure_block", "command_block", "chain_command_block", "repeating_command_block");

    private static final Map<String, String> ITEM = Map.ofEntries(
            Map.entry("wall_torch", "torch"), Map.entry("soul_wall_torch", "soul_torch"),
            Map.entry("redstone_wall_torch", "redstone_torch"), Map.entry("redstone_wire", "redstone"),
            Map.entry("tripwire", "string"), Map.entry("cocoa", "cocoa_beans"), Map.entry("carrots", "carrot"),
            Map.entry("potatoes", "potato"), Map.entry("beetroots", "beetroot_seeds"), Map.entry("wheat", "wheat_seeds"),
            Map.entry("melon_stem", "melon_seeds"), Map.entry("attached_melon_stem", "melon_seeds"),
            Map.entry("pumpkin_stem", "pumpkin_seeds"), Map.entry("attached_pumpkin_stem", "pumpkin_seeds"),
            Map.entry("sweet_berry_bush", "sweet_berries"), Map.entry("cave_vines", "glow_berries"),
            Map.entry("cave_vines_plant", "glow_berries"), Map.entry("kelp_plant", "kelp"),
            Map.entry("twisting_vines_plant", "twisting_vines"), Map.entry("weeping_vines_plant", "weeping_vines"),
            Map.entry("bamboo_sapling", "bamboo"), Map.entry("big_dripleaf_stem", "big_dripleaf"),
            Map.entry("tall_seagrass", "seagrass"), Map.entry("farmland", "dirt"), Map.entry("dirt_path", "dirt"),
            Map.entry("torchflower_crop", "torchflower_seeds"), Map.entry("pitcher_crop", "pitcher_pod"),
            Map.entry("powder_snow", "powder_snow_bucket"), Map.entry("water", "water_bucket"),
            Map.entry("lava", "lava_bucket"), Map.entry("water_cauldron", "cauldron"),
            Map.entry("lava_cauldron", "cauldron"), Map.entry("powder_snow_cauldron", "cauldron"));

    /** Items for one block, {@code minecraft:torch -> 1}; empty when it costs nothing. */
    public static Map<String, Integer> of(BlockSpec s) {
        String ns = s.name().substring(0, s.name().indexOf(':') + 1);
        String p = s.path();
        if (NOTHING.contains(p)) return Map.of();
        if ("upper".equals(s.get("half")) || "head".equals(s.get("part"))) return Map.of(); // comes with its other half
        if ((p.equals("water") || p.equals("lava")) && !"0".equals(s.get("level")) && s.get("level") != null) return Map.of();
        if (p.startsWith("potted_")) return Map.of(ns + "flower_pot", 1, ns + p.substring("potted_".length()), 1);
        String item = ITEM.get(p);
        if (item == null) {
            item = p.replace("_wall_hanging_sign", "_hanging_sign").replace("_wall_sign", "_sign")
                    .replace("_wall_banner", "_banner").replace("_wall_head", "_head").replace("_wall_skull", "_skull")
                    .replace("_wall_fan", "_fan");
        }
        int n = 1;
        if ("double".equals(s.get("type")) && p.endsWith("_slab")) n = 2;
        for (String counted : new String[]{"candles", "pickles", "layers", "eggs", "flower_amount", "segment_amount"}) {
            if (s.get(counted) != null) n = parse(s.get(counted), 1);
        }
        return Map.of(ns + item, n);
    }

    private static int parse(String v, int fallback) {
        try {
            return Math.max(1, Integer.parseInt(v));
        } catch (NumberFormatException e) {
            return fallback;
        }
    }
}
