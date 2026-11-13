package dev.kindredspirit.blueprint;

import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * "A cozy cottage for three": a house generated for how many people it's for, as a {@link Blueprint}
 * her building already knows how to place, turn, check and cost.
 *
 * <p>A cobblestone floor; plank walls three high with log corners; glass panes in every wall; the door
 * in the middle of the front, under the gable; a pitched stair roof with the ridge running front to
 * back, overhanging the sides and the front (a little porch); inside, a bed for each person against
 * the back wall (each its own colour), a chest, a crafting table and a furnace, and torches. The front
 * is the +z side (south), so placing it in front of a player turns the door toward them. Wider for
 * more people (up to 8). Plain Java.
 */
public final class House {
    private House() {}

    public static final Set<String> WOODS = Set.of("oak", "spruce", "birch", "jungle", "acacia", "dark_oak", "cherry", "mangrove");
    private static final List<String> BEDS = List.of("red", "light_blue", "yellow", "lime", "white", "purple", "orange", "pink");

    /** @param wood the walls' wood (oak if unknown); the roof is dark oak over oak, else the same wood */
    public static Blueprint cottage(int people, String wood) {
        int n = Math.max(1, Math.min(8, people));
        String w = wood(wood);
        String roof = w.equals("oak") ? "dark_oak" : w;
        int iw = Math.max(5, n + 2);
        if (iw % 2 == 0) iw++; // odd, so the door sits in the middle
        int il = 5;
        int bw = iw + 4, bl = il + 3; // walls at x=1 and bw-2, overhang at x=0 and bw-1; front wall z=il+1, porch z=il+2
        int layers = (bw - 1) / 2; // roof layers k = 0..layers (the last is the ridge)
        Blueprint.Builder b = Blueprint.builder(bw, 3 + layers + 1, bl).name("cozy cottage for " + n)
                .author("Pip").dataVersion(Blueprints.DATA_VERSION_1_21_1);
        int door = bw / 2, front = il + 1;

        BlockSpec cobble = BlockSpec.of("cobblestone"), planks = BlockSpec.of(w + "_planks"),
                log = BlockSpec.of(w + "_log").with("axis", "y"), air = BlockSpec.AIR;
        // floor, and the porch step in front of the door
        for (int x = 1; x <= bw - 2; x++) for (int z = 0; z <= front; z++) b.set(x, 0, z, cobble);
        b.set(door, 0, il + 2, cobble);
        // walls, corners, inside air
        for (int y = 1; y <= 3; y++) {
            for (int x = 1; x <= bw - 2; x++) {
                for (int z = 0; z <= front; z++) {
                    boolean wallX = x == 1 || x == bw - 2, wallZ = z == 0 || z == front;
                    if (wallX && wallZ) b.set(x, y, z, log);
                    else if (wallX || wallZ) b.set(x, y, z, planks);
                    else b.set(x, y, z, air);
                }
            }
            for (int x = 1; x <= bw - 2; x++) if (y <= 2) b.set(x, y, il + 2, air); // clear the porch
        }
        // the door, and windows (panes joined along their wall)
        BlockSpec doorLow = new BlockSpec(w + "_door", Map.of("facing", "north", "half", "lower", "hinge", "left",
                "open", "false", "powered", "false"));
        b.set(door, 1, front, doorLow).set(door, 2, front, doorLow.with("half", "upper"));
        BlockSpec paneX = pane(true), paneZ = pane(false);
        int mid = (il + 1) / 2 + 1;
        b.set(1, 2, mid, paneZ).set(bw - 2, 2, mid, paneZ); // side walls
        b.set(door, 2, 0, paneX);                          // back
        b.set(door - 2, 2, front, paneX).set(door + 2, 2, front, paneX); // either side of the door
        // the roof: stairs climbing from both sides to a slab ridge; gables front and back
        for (int k = 0; k <= layers; k++) {
            int y = 3 + k, xl = k, xr = bw - 1 - k;
            for (int z = 0; z < bl; z++) {
                if (xl < xr) {
                    b.set(xl, y, z, stair(roof, "east"));
                    b.set(xr, y, z, stair(roof, "west"));
                } else if (xl == xr) {
                    b.set(xl, y, z, new BlockSpec(roof + "_slab", Map.of("type", "bottom", "waterlogged", "false")));
                }
            }
            if (k >= 1) {
                for (int x = k + 1; x <= bw - 2 - k; x++) {
                    b.set(x, y, 0, planks).set(x, y, front, planks);
                    for (int z = 1; z <= il; z++) b.set(x, y, z, air);
                }
            }
        }
        // inside: a bed each against the back wall (head at the back), then chest, crafting table, furnace
        for (int i = 0; i < n; i++) {
            String bed = BEDS.get(i % BEDS.size()) + "_bed";
            b.set(2 + i, 1, 1, new BlockSpec(bed, Map.of("facing", "north", "part", "head", "occupied", "false")));
            b.set(2 + i, 1, 2, new BlockSpec(bed, Map.of("facing", "north", "part", "foot", "occupied", "false")));
        }
        int side = bw - 3;
        b.set(side, 1, 1, new BlockSpec("chest", Map.of("facing", "west", "type", "single", "waterlogged", "false")));
        b.set(side, 1, 2, BlockSpec.of("crafting_table"));
        b.set(side, 1, 3, new BlockSpec("furnace", Map.of("facing", "west", "lit", "false")));
        b.set(door, 2, 1, new BlockSpec("wall_torch", Map.of("facing", "south")));
        b.set(2, 2, il, new BlockSpec("wall_torch", Map.of("facing", "north")));
        b.set(bw - 3, 2, il, new BlockSpec("wall_torch", Map.of("facing", "north")));
        return b.build();
    }

    /** A "cottage", a "house", a "hut"...: the shapes this makes, by name. */
    public static boolean names(String what) {
        String w = what == null ? "" : what.toLowerCase(Locale.ROOT);
        return w.isBlank() || w.matches(".*\\b(cottage|house|home|hut|cabin|shelter|lodge)s?\\b.*");
    }

    static String wood(String wood) {
        String w = wood == null ? "" : wood.trim().toLowerCase(Locale.ROOT).replace(' ', '_').replace("minecraft:", "")
                .replaceAll("_(planks|log|wood)$", "");
        return WOODS.contains(w) ? w : "oak";
    }

    private static BlockSpec stair(String wood, String facing) {
        return new BlockSpec(wood + "_stairs", Map.of("facing", facing, "half", "bottom", "shape", "straight", "waterlogged", "false"));
    }

    /** A glass pane joined along x (front and back walls) or along z (side walls). */
    private static BlockSpec pane(boolean alongX) {
        return new BlockSpec("glass_pane", Map.of("east", alongX ? "true" : "false", "west", alongX ? "true" : "false",
                "north", alongX ? "false" : "true", "south", alongX ? "false" : "true", "waterlogged", "false"));
    }
}
