package dev.kindredspirit.act;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * What she builds with you, as steps: where each block goes (or goes away), in the order she does it.
 * Shapes start at an origin (the spot you're looking at) and extend forward (the way you face) and to
 * your right. Placing goes from the bottom up, one layer at a time, so it rises like someone building
 * it; clearing goes from the top down. Plain Java, no game classes (tested on its own).
 *
 * <ul>
 *   <li>pillar, corners, wall, floor, outline: one block kind, as before</li>
 *   <li>place: one block or item where you look, placed like a player would (a bed, a campfire, a door)</li>
 *   <li>house: a floor, walls with a doorway (and a door if there is one), a flat roof; sized for N people</li>
 *   <li>portal: a nether portal frame (obsidian, no corners), then lit</li>
 *   <li>clear: everything in an area goes, from a level up (trees, hills); flatten: the same, and holes
 *       in the ground at that level are filled</li>
 * </ul>
 */
public final class BuildPlan {
    private BuildPlan() {}

    public static final int MAX_BLOCKS = 256;
    /** Bigger things (a house, clearing ground): still bounded, so a misheard number can't eat the world. */
    public static final int MAX_BIG = 4096;
    public static final int MAX_SIDE = 32;
    public static final int MAX_HEIGHT = 64;

    /** B: place the block; F: place it only where there's nothing (filling holes); X: take away what's
     *  there; D: a door (or nothing) in a doorway; L: light it (a portal); P: place an item like a player. */
    public record Step(int x, int y, int z, char kind, String block) {
        Step(int x, int y, int z, char kind) {
            this(x, y, z, kind, null);
        }
    }

    public enum Shape {
        PILLAR, CORNERS, WALL, FLOOR, OUTLINE, PLACE, HOUSE, PORTAL, CLEAR, FLATTEN;

        public static Shape of(String s) {
            String k = s == null ? "" : s.trim().toLowerCase(Locale.ROOT).replace(' ', '_');
            return switch (k) {
                case "pillar", "column", "tower", "stack", "pole" -> PILLAR;
                case "corners", "corner", "corner_pillars", "four_pillars" -> CORNERS;
                case "wall", "line", "row", "fence" -> WALL;
                case "floor", "square", "platform", "rectangle" -> FLOOR;
                case "outline", "ring", "border", "frame", "walls", "pen", "room" -> OUTLINE;
                case "place", "one", "single", "block", "put", "item" -> PLACE;
                case "house", "home", "hut", "cabin", "shelter", "cottage" -> HOUSE;
                case "portal", "nether_portal" -> PORTAL;
                case "clear", "remove", "dig", "erase", "empty" -> CLEAR;
                case "flatten", "level", "flat", "squash" -> FLATTEN;
                default -> null;
            };
        }

        /** Shapes that take blocks away (the rest place them). */
        public boolean clears() {
            return this == CLEAR || this == FLATTEN;
        }
    }

    /** The shapes she knows, in words, for an honest "I can't build that". */
    public static final String KNOWN = "a pillar, corners, a wall, a floor, an outline, one block or item where you look, "
            + "a house, a nether portal, or clearing / flattening an area";

    /** As before: positions only (the simple shapes). */
    public static List<int[]> positions(Shape shape, int ox, int oy, int oz, int fx, int fz,
                                        int width, int length, int height) {
        List<int[]> out = new ArrayList<>();
        for (Step s : steps(shape, ox, oy, oz, fx, fz, width, length, height, 1, Integer.MIN_VALUE)) {
            out.add(new int[]{s.x(), s.y(), s.z()});
        }
        return out;
    }

    /**
     * @param fx,fz  forward (unit, one of the four directions); right is (-fz, fx)
     * @param width  to the right; length: forward; height: up (each clamped to sensible limits)
     * @param people a house for this many (1 to 6)
     * @param level  clear / flatten: the ground level (an absolute Y), or Integer.MIN_VALUE for "where you look"
     */
    public static List<Step> steps(Shape shape, int ox, int oy, int oz, int fx, int fz,
                                   int width, int length, int height, int people, int level) {
        int rx = -fz, rz = fx;
        List<Step> out = new ArrayList<>();
        switch (shape) {
            case PLACE -> out.add(new Step(ox, oy, oz, 'P'));
            case HOUSE -> {
                int n = clamp(people, 1, 6);
                int w = clamp(width > 1 ? width : 5 + 2 * (n - 1), 5, 15), l = clamp(length > 1 ? length : w, 5, 15);
                int h = clamp(height > 1 ? height : 3, 3, 5);
                int door = w / 2;
                for (int f = 0; f < l; f++) for (int r = 0; r < w; r++) out.add(at(ox, oy, oz, rx, rz, fx, fz, r, f, 0, 'B'));
                for (int y = 1; y <= h; y++) {
                    for (int[] c : ring(w, l)) {
                        boolean doorway = c[1] == 0 && c[0] == door && y <= 2;
                        out.add(at(ox, oy, oz, rx, rz, fx, fz, c[0], c[1], y, doorway ? (y == 1 ? 'D' : 'X') : 'B'));
                    }
                }
                for (int f = 0; f < l; f++) for (int r = 0; r < w; r++) out.add(at(ox, oy, oz, rx, rz, fx, fz, r, f, h + 1, 'B'));
            }
            case PORTAL -> { // in the plane to your right and up: 4 wide, 5 high, no corners (10 obsidian)
                for (int y = 0; y < 5; y++) {
                    for (int r = 0; r < 4; r++) {
                        boolean edge = y == 0 || y == 4 || r == 0 || r == 3;
                        boolean corner = (y == 0 || y == 4) && (r == 0 || r == 3);
                        if (edge && !corner) out.add(at(ox, oy, oz, rx, rz, fx, fz, r, 0, y, 'B', "obsidian"));
                        else if (!edge) out.add(at(ox, oy, oz, rx, rz, fx, fz, r, 0, y, 'X')); // (room for the portal)
                    }
                }
                out.add(at(ox, oy, oz, rx, rz, fx, fz, 1, 0, 1, 'L'));
            }
            case CLEAR, FLATTEN -> {
                int w = clamp(width > 1 ? width : 8, 1, MAX_SIDE), l = clamp(length > 1 ? length : 8, 1, MAX_SIDE);
                int base = level == Integer.MIN_VALUE ? oy : level + 1; // (the first layer that goes)
                int h = clamp(height > 1 ? height : 12, 1, MAX_HEIGHT);
                for (int y = base + h - 1; y >= base; y--) { // from the top down
                    for (int f = 0; f < l; f++) for (int r = 0; r < w; r++) {
                        out.add(new Step(ox + r * rx + f * fx, y, oz + r * rz + f * fz, 'X'));
                    }
                }
                if (shape == Shape.FLATTEN) {
                    for (int f = 0; f < l; f++) for (int r = 0; r < w; r++) {
                        out.add(new Step(ox + r * rx + f * fx, base - 1, oz + r * rz + f * fz, 'F'));
                    }
                }
            }
            default -> {
                int w = clamp(width, 1, MAX_SIDE), l = clamp(length, 1, MAX_SIDE), h = clamp(height, 1, MAX_HEIGHT);
                List<int[]> layer = new ArrayList<>(); // (right, forward) cells of one layer
                switch (shape) {
                    case PILLAR -> layer.add(new int[]{0, 0});
                    case CORNERS -> {
                        layer.add(new int[]{0, 0});
                        if (w > 1) layer.add(new int[]{w - 1, 0});
                        if (l > 1) layer.add(new int[]{0, l - 1});
                        if (w > 1 && l > 1) layer.add(new int[]{w - 1, l - 1});
                    }
                    case WALL -> { for (int i = 0; i < w; i++) layer.add(new int[]{i, 0}); }
                    case FLOOR -> {
                        h = 1;
                        for (int f = 0; f < l; f++) for (int r = 0; r < w; r++) layer.add(new int[]{r, f});
                    }
                    case OUTLINE -> layer.addAll(ring(w, l));
                    default -> { }
                }
                for (int y = 0; y < h && out.size() < MAX_BLOCKS; y++) {
                    for (int[] c : layer) {
                        if (out.size() >= MAX_BLOCKS) break;
                        out.add(at(ox, oy, oz, rx, rz, fx, fz, c[0], c[1], y, 'B'));
                    }
                }
            }
        }
        return out.size() > MAX_BIG ? new ArrayList<>(out.subList(0, MAX_BIG)) : out;
    }

    /** Around the edge of w x l, walking it in order. */
    static List<int[]> ring(int w, int l) {
        List<int[]> c = new ArrayList<>();
        for (int r = 0; r < w; r++) c.add(new int[]{r, 0});
        for (int f = 1; f < l; f++) c.add(new int[]{w - 1, f});
        if (l > 1) for (int r = w - 2; r >= 0; r--) c.add(new int[]{r, l - 1});
        if (w > 1) for (int f = l - 2; f >= 1; f--) c.add(new int[]{0, f});
        return c;
    }

    private static Step at(int ox, int oy, int oz, int rx, int rz, int fx, int fz, int r, int f, int y, char kind) {
        return at(ox, oy, oz, rx, rz, fx, fz, r, f, y, kind, null);
    }

    private static Step at(int ox, int oy, int oz, int rx, int rz, int fx, int fz, int r, int f, int y, char kind, String block) {
        return new Step(ox + r * rx + f * fx, oy + y, oz + r * rz + f * fz, kind, block);
    }

    static int clamp(int v, int lo, int hi) {
        return Math.max(lo, Math.min(hi, v));
    }
}
