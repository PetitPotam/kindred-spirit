package dev.kindredspirit.blueprint;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * A blueprint put somewhere in the world: in front of a player, its front facing them, and the order
 * she builds it in. Plain Java (tested on its own); the game side turns the steps into blocks.
 *
 * <p><b>Where.</b> The origin is the spot the player looks at (the ground where the front row goes).
 * The build is turned so its front (see {@link Blueprint#frontTurns()}) faces the player, then
 * reaches away from them; {@link Anchor#FRONT_CENTER} centres the front on the origin (a house
 * with its door where you look), {@link Anchor#FRONT_LEFT} starts there and goes to the right (like
 * her simple shapes). The blueprint's bottom layer is at the origin's height.
 *
 * <p><b>Order.</b> First, if asked, the cells the template marks as air are cleared, top down, above its
 * bottom layer (which sits in the ground and never digs it) (a hill
 * where the house goes). Then the frame, bottom layer first, row by row back and forth so she drifts
 * smoothly instead of jumping. Then the details that hang on something or would flow (torches,
 * doors, beds, carpets, rails, redstone, plants, water), bottom up, once what they hang on is there.
 * The second half of a door, bed or tall flower is its own step (commands need it; placing like a
 * player makes it by itself, so a player-style builder skips {@link Kind#SECOND_HALF}).
 */
public final class Placement {

    public enum Anchor { FRONT_LEFT, FRONT_CENTER }

    public enum Kind { CLEAR, BLOCK, DETAIL, SECOND_HALF }

    /** One thing to do at a world position: place {@code state} (with its block entity data), or clear. */
    public record Step(int x, int y, int z, Kind kind, BlockSpec state, Map<String, Object> blockEntity) {}

    private final Blueprint turned;
    private final int turns;
    private final int dx, dy, dz; // world = blueprint cell + (dx, dy, dz)

    private Placement(Blueprint turned, int turns, int dx, int dy, int dz) {
        this.turned = turned;
        this.turns = turns;
        this.dx = dx;
        this.dy = dy;
        this.dz = dz;
    }

    /**
     * @param ox,oy,oz the spot the player looks at
     * @param fx,fz    the way the player faces (one of the four directions: north is 0,-1)
     */
    public static Placement inFront(Blueprint bp, int ox, int oy, int oz, int fx, int fz, Anchor anchor) {
        int front = bp.frontTurns();
        Blueprint facingSouth = bp.rotated(front); // front at +z, like a player facing north sees it
        int ax = anchor == Anchor.FRONT_CENTER ? facingSouth.width() / 2 : 0, az = facingSouth.length() - 1;
        int face = facingTurns(fx, fz);
        // follow the anchor cell through the player's turn
        int w = facingSouth.width(), l = facingSouth.length();
        for (int i = 0; i < face; i++) {
            int nx = l - 1 - az, nz = ax;
            ax = nx;
            az = nz;
            int t = w;
            w = l;
            l = t;
        }
        Blueprint turned = facingSouth.rotated(face);
        return new Placement(turned, Math.floorMod(front + face, 4), ox - ax, oy, oz - az);
    }

    /** At a fixed corner and turn, no guessing: what "remember this house" and /place-like uses need. */
    public static Placement at(Blueprint bp, int minX, int minY, int minZ, int quarterTurns) {
        return new Placement(bp.rotated(quarterTurns), Math.floorMod(quarterTurns, 4), minX, minY, minZ);
    }

    /** Quarter turns clockwise from facing north: north 0, east 1, south 2, west 3. */
    public static int facingTurns(int fx, int fz) {
        if (fx > 0) return 1;
        if (fz > 0) return 2;
        if (fx < 0) return 3;
        return 0;
    }

    /** The blueprint as it will stand (turned). */
    public Blueprint blueprint() {
        return turned;
    }

    /** Quarter turns clockwise applied to the file's own orientation (for the game's StructureTemplate). */
    public int turns() {
        return turns;
    }

    /** The world box it fills: {minX, minY, minZ, maxX, maxY, maxZ}, for the ghost outline and chunk checks. */
    public int[] box() {
        return new int[]{dx, dy, dz, dx + turned.width() - 1, dy + turned.height() - 1, dz + turned.length() - 1};
    }

    /** In the order she builds it. {@code clearAir}: also clear what's in the way where the template has air. */
    public List<Step> steps(boolean clearAir) {
        Blueprint b = turned;
        List<Step> clear = new ArrayList<>(), frame = new ArrayList<>(), details = new ArrayList<>();
        for (int y = 0; y < b.height(); y++) {
            for (int z = 0; z < b.length(); z++) {
                boolean back = (z % 2 == 1) ^ (y % 2 == 1); // back and forth, row by row
                for (int i = 0; i < b.width(); i++) {
                    int x = back ? b.width() - 1 - i : i;
                    BlockSpec s = b.at(x, y, z);
                    if (s == null) continue;
                    if (s.isAir()) {
                        // the bottom layer sits in the ground: air there leaves the ground as it is (a Litematica
                        // circle stores air in every empty cell: it would dig a square hole around itself)
                        if (clearAir && y > 0) clear.add(new Step(x + dx, y + dy, z + dz, Kind.CLEAR, s, null));
                        continue;
                    }
                    Kind kind = secondHalf(s) ? Kind.SECOND_HALF : needsSupport(s) ? Kind.DETAIL : Kind.BLOCK;
                    Step step = new Step(x + dx, y + dy, z + dz, kind, s, b.blockEntityAt(x, y, z));
                    (kind == Kind.BLOCK ? frame : details).add(step);
                }
            }
        }
        List<Step> out = new ArrayList<>(clear.size() + frame.size() + details.size());
        for (int i = clear.size() - 1; i >= 0; i--) out.add(clear.get(i)); // top down
        out.addAll(frame);
        out.addAll(details);
        return out;
    }

    static boolean secondHalf(BlockSpec s) {
        return "upper".equals(s.get("half")) || "head".equals(s.get("part"));
    }

    private static final String[] HANGS = {
            "torch", "lantern", "ladder", "_button", "lever", "_sign", "_banner", "_carpet", "rail", "redstone_wire",
            "repeater", "comparator", "_pressure_plate", "tripwire", "_door", "_bed", "vine", "lichen", "_head",
            "_skull", "bell", "cocoa", "candle", "sapling", "flower", "_tulip", "dandelion", "poppy", "orchid",
            "allium", "azure_bluet", "oxeye_daisy", "cornflower", "lily_of_the_valley", "wither_rose", "short_grass",
            "fern", "dead_bush", "sugar_cane", "cactus", "bamboo", "kelp", "seagrass", "sea_pickle", "lily_pad",
            "mushroom", "_coral", "_fan", "snow", "scaffolding", "chain", "end_rod", "pointed_dripstone", "amethyst_bud",
            "amethyst_cluster", "tall_grass", "large_fern", "sunflower", "lilac", "rose_bush", "peony", "wheat",
            "carrots", "potatoes", "beetroots", "_stem", "sweet_berry_bush", "nether_wart", "water", "lava", "fire",
            "frogspawn", "spore_blossom", "hanging_roots", "glow_berries", "cave_vines", "moss_carpet", "dripleaf",
            "pink_petals", "_trapdoor", "flower_pot", "potted_", "tripwire_hook", "daylight_detector"};

    private static final java.util.Set<String> SOLID = java.util.Set.of(
            "sea_lantern", "jack_o_lantern", "mushroom_stem", "bamboo_mosaic", "snow_block", "fire_coral_block");

    /** Hangs on something, stands on something fragile-looking, or would flow: placed after the frame. */
    static boolean needsSupport(BlockSpec s) {
        String p = s.path();
        if (p.endsWith("_block") || p.endsWith("_planks") || p.endsWith("_log") || p.endsWith("_wood")) return false;
        if (SOLID.contains(p) || p.endsWith("crimson_stem") || p.endsWith("warped_stem")) return false;
        for (String h : HANGS) if (p.contains(h)) return true;
        return false;
    }
}
