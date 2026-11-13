package dev.kindredspirit.job;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.function.Predicate;

/**
 * Which blocks a mining job takes, in which order: the nearest matching block within the radius,
 * then the rest of its vein (ores come in clusters, trees in trunks), then the next nearest vein,
 * until there are enough. Plain Java over a block lookup, so it's tested without the game.
 */
public final class Dig {
    private Dig() {}

    /** The block id at a position ("minecraft:iron_ore"), or "" where nothing is known (unloaded). */
    public interface World {
        String block(int x, int y, int z);
    }

    private static final int[][] FACES = {{1, 0, 0}, {-1, 0, 0}, {0, 1, 0}, {0, -1, 0}, {0, 0, 1}, {0, 0, -1}};

    /** Connected blocks that match (faces, or the 26 neighbours with {@code diagonal}), nearest first, at most {@code max}. */
    public static List<int[]> vein(World w, int x, int y, int z, Predicate<String> match, int max, boolean diagonal) {
        List<int[]> out = new ArrayList<>();
        if (!match.test(w.block(x, y, z))) return out;
        Set<Long> seen = new HashSet<>();
        Deque<int[]> queue = new ArrayDeque<>();
        queue.add(new int[]{x, y, z});
        seen.add(key(x, y, z));
        while (!queue.isEmpty() && out.size() < max) {
            int[] p = queue.poll();
            out.add(p);
            for (int[] d : neighbours(diagonal)) {
                int nx = p[0] + d[0], ny = p[1] + d[1], nz = p[2] + d[2];
                if (seen.add(key(nx, ny, nz)) && match.test(w.block(nx, ny, nz))) queue.add(new int[]{nx, ny, nz});
            }
        }
        return out;
    }

    /**
     * Up to {@code want} matching blocks within {@code radius} of the centre: veins in order of their
     * nearest block, each vein whole (so she doesn't leave half an ore cluster behind), never outside
     * the radius.
     */
    public static List<int[]> find(World w, int cx, int cy, int cz, int radius, Predicate<String> match, int want) {
        List<int[]> candidates = new ArrayList<>();
        int r2 = radius * radius;
        for (int dx = -radius; dx <= radius; dx++)
            for (int dy = -radius; dy <= radius; dy++)
                for (int dz = -radius; dz <= radius; dz++) {
                    if (dx * dx + dy * dy + dz * dz > r2) continue;
                    if (match.test(w.block(cx + dx, cy + dy, cz + dz))) candidates.add(new int[]{cx + dx, cy + dy, cz + dz});
                }
        candidates.sort(Comparator.comparingInt(p -> dist2(p, cx, cy, cz)));
        Set<Long> taken = new HashSet<>();
        List<int[]> out = new ArrayList<>();
        Predicate<String> any = match;
        for (int[] c : candidates) {
            if (out.size() >= want) break;
            if (taken.contains(key(c[0], c[1], c[2]))) continue;
            for (int[] p : vein(w, c[0], c[1], c[2], any, 256, true)) {
                if (dist2(p, cx, cy, cz) > r2 || !taken.add(key(p[0], p[1], p[2]))) continue;
                out.add(p);
                if (out.size() >= want) break;
            }
        }
        return out;
    }

    private static int[][] neighbours(boolean diagonal) {
        if (!diagonal) return FACES;
        int[][] all = new int[26][];
        int i = 0;
        for (int dx = -1; dx <= 1; dx++)
            for (int dy = -1; dy <= 1; dy++)
                for (int dz = -1; dz <= 1; dz++)
                    if (dx != 0 || dy != 0 || dz != 0) all[i++] = new int[]{dx, dy, dz};
        return all;
    }

    static int dist2(int[] p, int x, int y, int z) {
        int dx = p[0] - x, dy = p[1] - y, dz = p[2] - z;
        return dx * dx + dy * dy + dz * dz;
    }

    private static long key(int x, int y, int z) {
        return ((long) (x & 0x3FFFFFF) << 38) | ((long) (z & 0x3FFFFFF) << 12) | (y & 0xFFF);
    }

    /** "iron" → iron ore of both kinds; "diamonds" → diamond ore; "coal", "logs", "stone"... as block ids. */
    public static Predicate<String> kind(String what) {
        String w = what == null ? "" : what.trim().toLowerCase(java.util.Locale.ROOT).replace(' ', '_');
        if (w.endsWith("s") && !w.endsWith("ss")) w = w.substring(0, w.length() - 1);
        String bare = w.replace("minecraft:", "");
        if (bare.equals("log") || bare.equals("wood") || bare.equals("tree")) return id -> id.endsWith("_log") || id.endsWith("_stem");
        if (bare.equals("ore")) return id -> id.endsWith("_ore") || id.equals("minecraft:ancient_debris");
        if (bare.equals("debris") || bare.equals("netherite") || bare.equals("ancient_debri")) return id -> id.equals("minecraft:ancient_debris");
        final String b = bare.endsWith("_ore") ? bare.substring(0, bare.length() - 4) : bare;
        return id -> {
            String p = id.substring(id.indexOf(':') + 1);
            return p.equals(b + "_ore") || p.equals("deepslate_" + b + "_ore") || p.equals("nether_" + b + "_ore")
                    || (!b.isEmpty() && p.equals(b) && !p.equals("air"));
        };
    }
}
