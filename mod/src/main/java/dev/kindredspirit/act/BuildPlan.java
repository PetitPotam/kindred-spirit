package dev.kindredspirit.act;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * Where the blocks go for something she builds with you: a pillar, a pillar on each corner, a wall,
 * a floor, an outline. Positions start at an origin (the spot you're looking at) and extend forward
 * (the way you face) and to your right; they're ordered from the bottom up, one layer at a time, so
 * it rises like someone building it. Plain Java, no game classes (tested on its own).
 */
public final class BuildPlan {
    private BuildPlan() {}

    public static final int MAX_BLOCKS = 256;
    public static final int MAX_SIDE = 32;
    public static final int MAX_HEIGHT = 64;

    public enum Shape {
        PILLAR, CORNERS, WALL, FLOOR, OUTLINE;

        public static Shape of(String s) {
            String k = s == null ? "" : s.trim().toLowerCase(Locale.ROOT);
            return switch (k) {
                case "pillar", "column", "tower", "stack", "pole" -> PILLAR;
                case "corners", "corner", "corner_pillars", "four_pillars" -> CORNERS;
                case "wall", "line", "row", "fence" -> WALL;
                case "floor", "square", "platform", "rectangle" -> FLOOR;
                case "outline", "ring", "border", "frame", "walls", "pen", "room" -> OUTLINE;
                default -> null;
            };
        }
    }

    /**
     * @param fx,fz  forward (unit, one of the four directions); right is (-fz, fx)
     * @param width  to the right; length: forward; height: up (each clamped to sensible limits)
     * @return positions {x, y, z}, bottom layer first, at most MAX_BLOCKS
     */
    public static List<int[]> positions(Shape shape, int ox, int oy, int oz, int fx, int fz,
                                        int width, int length, int height) {
        int w = clamp(width, 1, MAX_SIDE), l = clamp(length, 1, MAX_SIDE), h = clamp(height, 1, MAX_HEIGHT);
        int rx = -fz, rz = fx;
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
            case OUTLINE -> { // around the edge, walking it in order
                for (int r = 0; r < w; r++) layer.add(new int[]{r, 0});
                for (int f = 1; f < l; f++) layer.add(new int[]{w - 1, f});
                if (l > 1) for (int r = w - 2; r >= 0; r--) layer.add(new int[]{r, l - 1});
                if (w > 1) for (int f = l - 2; f >= 1; f--) layer.add(new int[]{0, f});
            }
        }
        List<int[]> out = new ArrayList<>();
        for (int y = 0; y < h && out.size() < MAX_BLOCKS; y++) {
            for (int[] c : layer) {
                if (out.size() >= MAX_BLOCKS) break;
                out.add(new int[]{ox + c[0] * rx + c[1] * fx, oy + y, oz + c[0] * rz + c[1] * fz});
            }
        }
        return out;
    }

    static int clamp(int v, int lo, int hi) {
        return Math.max(lo, Math.min(hi, v));
    }
}
