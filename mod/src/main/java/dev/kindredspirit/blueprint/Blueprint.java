package dev.kindredspirit.blueprint;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Something to build, whatever file it came from: a box of {@code width x height x length} cells,
 * each holding a block (an index into the palette) or {@link #LEAVE} (leave the world as it is there:
 * a structure void, or a cell the file doesn't cover). Air is a real block here: in a template it
 * means "clear this", like the inside of a house.
 *
 * <p>Axes are the file's own: x east, y up, z south. The <b>front</b> is the +z side (south) unless
 * {@link #frontTurns()} finds a door on another side; placing it in front of a player turns it so its
 * front faces them (see {@link Placement}).
 *
 * <p>Cells are stored densely (one int each, indexed {@code x + z*width + y*width*length} like Sponge
 * schematics), so a 128-block cube is 8 MB, and turning or looking up a cell is cheap. Block entities
 * (a chest's items, a sign's words) are kept as raw NBT by cell; entities (item frames, armor stands,
 * animals) as raw NBT with their position in the box. Plain Java, no game classes.
 */
public final class Blueprint {

    public static final int LEAVE = -1;
    /** A 128-block cube: bigger than any house, small enough to hold in memory and preview. */
    public static final int MAX_VOLUME = 128 * 128 * 128;

    public enum Format { STRUCTURE, SPONGE, LITEMATIC }

    /** An entity in the box: position in blueprint coordinates (doubles, as in the files), its raw NBT. */
    public record Entity(double x, double y, double z, Map<String, Object> nbt) {
        public String id() {
            return nbt != null && nbt.get("id") instanceof String s ? s : "";
        }
    }

    private final String name;
    private final String author;
    private final Format format;
    private final int dataVersion;
    private final int width, height, length;
    private final List<BlockSpec> palette;
    private final int[] cells;
    private final Map<Integer, Map<String, Object>> blockEntities;
    private final List<Entity> entities;

    private Blueprint(String name, String author, Format format, int dataVersion, int width, int height, int length,
                      List<BlockSpec> palette, int[] cells, Map<Integer, Map<String, Object>> blockEntities,
                      List<Entity> entities) {
        this.name = name == null ? "" : name;
        this.author = author == null ? "" : author;
        this.format = format;
        this.dataVersion = dataVersion;
        this.width = width;
        this.height = height;
        this.length = length;
        this.palette = List.copyOf(palette);
        this.cells = cells;
        this.blockEntities = Collections.unmodifiableMap(blockEntities);
        this.entities = List.copyOf(entities);
    }

    public String name() { return name; }
    public String author() { return author; }
    public Format format() { return format; }
    /** The game data version the file was saved with (1.21.1 is 3955); 0 when the file doesn't say. */
    public int dataVersion() { return dataVersion; }
    public int width() { return width; }
    public int height() { return height; }
    public int length() { return length; }
    public List<BlockSpec> palette() { return palette; }
    public List<Entity> entities() { return entities; }

    public int index(int x, int y, int z) {
        return x + z * width + y * width * length;
    }

    public boolean inside(int x, int y, int z) {
        return x >= 0 && y >= 0 && z >= 0 && x < width && y < height && z < length;
    }

    /** The block at a cell, or null to leave the world as it is there. */
    public BlockSpec at(int x, int y, int z) {
        if (!inside(x, y, z)) return null;
        int s = cells[index(x, y, z)];
        return s == LEAVE ? null : palette.get(s);
    }

    /** The block entity data at a cell (a chest's items, a sign's text), or null. */
    public Map<String, Object> blockEntityAt(int x, int y, int z) {
        return inside(x, y, z) ? blockEntities.get(index(x, y, z)) : null;
    }

    public int blockEntityCount() {
        return blockEntities.size();
    }

    /** How many cells hold a real block (not air, not left alone). */
    public int solidBlocks() {
        int n = 0;
        for (int s : cells) if (s != LEAVE && !palette.get(s).isAir()) n++;
        return n;
    }

    /**
     * What it takes to build, as items: {@code minecraft:oak_planks -> 64}, most first. A door or a bed
     * counts once, a double slab twice, a wall torch is a torch, water a bucket (see {@link Materials}).
     */
    public Map<String, Integer> materials() {
        int[] perState = new int[palette.size()];
        for (int s : cells) if (s != LEAVE) perState[s]++;
        Map<String, Integer> total = new HashMap<>();
        for (int i = 0; i < perState.length; i++) {
            if (perState[i] == 0) continue;
            for (Map.Entry<String, Integer> e : Materials.of(palette.get(i)).entrySet()) {
                total.merge(e.getKey(), e.getValue() * perState[i], Integer::sum);
            }
        }
        List<Map.Entry<String, Integer>> sorted = new ArrayList<>(total.entrySet());
        sorted.sort(Map.Entry.<String, Integer>comparingByValue().reversed().thenComparing(Map.Entry.comparingByKey()));
        Map<String, Integer> out = new LinkedHashMap<>();
        for (Map.Entry<String, Integer> e : sorted) out.put(e.getKey(), e.getValue());
        return out;
    }

    /**
     * Turned {@code quarterTurns} times clockwise seen from above (negative: the other way), blocks
     * and all: a cell (x, z) goes to (length-1-z, x), width and length swap, stairs and doors turn
     * with it. Entities move with the box (their own facing isn't turned yet).
     */
    public Blueprint rotated(int quarterTurns) {
        int k = Math.floorMod(quarterTurns, 4);
        if (k == 0) return this;
        Blueprint b = this;
        for (int i = 0; i < k; i++) b = b.turnedOnce();
        return b;
    }

    private Blueprint turnedOnce() {
        int w2 = length, l2 = width; // the new box
        int[] c2 = new int[cells.length];
        Map<Integer, Map<String, Object>> be2 = new HashMap<>();
        for (int y = 0; y < height; y++) {
            for (int z = 0; z < length; z++) {
                for (int x = 0; x < width; x++) {
                    int nx = length - 1 - z, nz = x;
                    int from = index(x, y, z), to = nx + nz * w2 + y * w2 * l2;
                    c2[to] = cells[from];
                    Map<String, Object> be = blockEntities.get(from);
                    if (be != null) be2.put(to, be);
                }
            }
        }
        List<BlockSpec> p2 = new ArrayList<>(palette.size());
        for (BlockSpec s : palette) p2.add(s.rotated(1));
        List<Entity> e2 = new ArrayList<>(entities.size());
        for (Entity e : entities) e2.add(new Entity(length - e.z(), e.y(), e.x(), e.nbt()));
        return new Blueprint(name, author, format, dataVersion, w2, height, l2, p2, c2, be2, e2);
    }

    /**
     * Quarter turns (clockwise) that bring its front to +z: the side of the box nearest to a door,
     * since that's where people come in. 0 when there's no door (keep the file's own south as front).
     */
    public int frontTurns() {
        int[] near = new int[4]; // doors closest to the north, east, south, west side
        for (int y = 0; y < height; y++) {
            for (int z = 0; z < length; z++) {
                for (int x = 0; x < width; x++) {
                    BlockSpec s = at(x, y, z);
                    if (s == null || !s.path().endsWith("_door") || "upper".equals(s.get("half"))) continue;
                    int[] d = {z, width - 1 - x, length - 1 - z, x};
                    int best = 0;
                    for (int i = 1; i < 4; i++) if (d[i] < d[best]) best = i;
                    near[best]++;
                }
            }
        }
        int side = 2;
        for (int i = 0; i < 4; i++) if (near[i] > near[side]) side = i;
        return near[side] == 0 ? 0 : Math.floorMod(2 - side, 4); // north 2, east 1, south 0, west 3
    }

    public Blueprint named(String newName) {
        return new Blueprint(newName, author, format, dataVersion, width, height, length, palette, cells,
                blockEntities, entities);
    }

    @Override
    public String toString() {
        return "Blueprint[" + (name.isEmpty() ? "?" : name) + " " + width + "x" + height + "x" + length + ", "
                + solidBlocks() + " blocks, " + palette.size() + " states, from " + format + "]";
    }

    // --- making one ------------------------------------------------------------------------------

    public static Builder builder(int width, int height, int length) {
        return new Builder(width, height, length);
    }

    /** Fills a blueprint cell by cell (the readers use it, and so will "remember this house"). */
    public static final class Builder {
        private final int width, height, length;
        private final int[] cells;
        private final List<BlockSpec> palette = new ArrayList<>();
        private final Map<BlockSpec, Integer> ids = new HashMap<>();
        private final Map<Integer, Map<String, Object>> blockEntities = new HashMap<>();
        private final List<Entity> entities = new ArrayList<>();
        private String name = "", author = "";
        private Format format = Format.STRUCTURE;
        private int dataVersion;

        private Builder(int width, int height, int length) {
            if (width <= 0 || height <= 0 || length <= 0) {
                throw new BlueprintException("a blueprint needs a size, not " + width + "x" + height + "x" + length);
            }
            long volume = (long) width * height * length;
            if (volume > MAX_VOLUME) {
                throw new BlueprintException("too big to build: " + width + "x" + height + "x" + length
                        + " (at most " + MAX_VOLUME + " cells, a 128-block cube)");
            }
            this.width = width;
            this.height = height;
            this.length = length;
            this.cells = new int[(int) volume];
            java.util.Arrays.fill(cells, LEAVE);
        }

        public Builder name(String n) { name = n; return this; }
        public Builder author(String a) { author = a; return this; }
        public Builder format(Format f) { format = f; return this; }
        public Builder dataVersion(int v) { dataVersion = v; return this; }

        /** Sets a cell; a structure void (or null) means leave it. Outside the box is an error. */
        public Builder set(int x, int y, int z, BlockSpec state) {
            int i = idx(x, y, z);
            if (state == null || state.isVoid()) {
                cells[i] = LEAVE;
                return this;
            }
            cells[i] = ids.computeIfAbsent(state, s -> {
                palette.add(s);
                return palette.size() - 1;
            });
            return this;
        }

        public BlockSpec get(int x, int y, int z) {
            int s = cells[idx(x, y, z)];
            return s == LEAVE ? null : palette.get(s);
        }

        public Builder blockEntity(int x, int y, int z, Map<String, Object> nbt) {
            if (nbt != null && !nbt.isEmpty()) blockEntities.put(idx(x, y, z), nbt);
            return this;
        }

        public Builder entity(double x, double y, double z, Map<String, Object> nbt) {
            entities.add(new Entity(x, y, z, nbt == null ? Map.of() : nbt));
            return this;
        }

        private int idx(int x, int y, int z) {
            if (x < 0 || y < 0 || z < 0 || x >= width || y >= height || z >= length) {
                throw new BlueprintException("block at " + x + " " + y + " " + z + " is outside the "
                        + width + "x" + height + "x" + length + " box");
            }
            return x + z * width + y * width * length;
        }

        public Blueprint build() {
            // only the states still used (a reader may overwrite cells), in first-use order
            List<BlockSpec> used = new ArrayList<>();
            int[] remap = new int[palette.size()];
            java.util.Arrays.fill(remap, -1);
            int[] c = cells.clone();
            for (int i = 0; i < c.length; i++) {
                if (c[i] == LEAVE) continue;
                if (remap[c[i]] < 0) {
                    remap[c[i]] = used.size();
                    used.add(palette.get(c[i]));
                }
                c[i] = remap[c[i]];
            }
            Map<Integer, Map<String, Object>> be = new HashMap<>();
            blockEntities.forEach((i, nbt) -> { if (c[i] != LEAVE) be.put(i, nbt); });
            return new Blueprint(name, author, format, dataVersion, width, height, length, used, c, be, entities);
        }
    }
}
