package dev.kindredspirit.blueprint;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Litematica schematics ({@code .litematic}), the Fabric world's favourite (ghost previews, material
 * lists). Checked against Litematica's own source (LitematicaSchematic, LitematicaBlockStateContainer,
 * LitematicaBitArray; schematic version 7 since 1.21, 6 before):
 *
 * <pre>
 * {MinecraftDataVersion, Version, SubVersion, Metadata: {Name, Author, EnclosingSize, ...},
 *  Regions: {"name": {Position: {x, y, z}, Size: {x, y, z} (may be negative),
 *                     BlockStatePalette: [{Name, Properties}], BlockStates: long[],
 *                     TileEntities: [{x, y, z, ...}] (from the region's min corner),
 *                     Entities: [{Pos: [double x3], ...}] (from the region's Position)}}}
 * </pre>
 *
 * A negative size means the region reaches back from its Position: it covers Position+Size+1 to
 * Position on that axis. Each cell's palette index takes {@code max(2, bits for palette size - 1)}
 * bits, packed low bits first into the longs, an entry may run over into the next long; the cell
 * order is {@code y*sizeX*sizeZ + z*sizeX + x}. Several regions become one blueprint (their union).
 */
public final class LitematicFormat {
    private LitematicFormat() {}

    static boolean looksLike(Map<String, Object> root) {
        return root.get("Regions") instanceof Map<?, ?> && root.containsKey("MinecraftDataVersion");
    }

    private record Region(Map<String, Object> tag, int[] pos, int[] min, int[] size) {}

    public static Blueprint read(Map<String, Object> root, String name) {
        int version = Nbt.integer(root, "Version", 0);
        if (version < 2) throw new BlueprintException("a very old Litematica schematic (version " + version + ")");
        Map<String, Object> regionsTag = Nbt.compound(root, "Regions");
        List<Region> regions = new ArrayList<>();
        int[] lo = {Integer.MAX_VALUE, Integer.MAX_VALUE, Integer.MAX_VALUE};
        int[] hi = {Integer.MIN_VALUE, Integer.MIN_VALUE, Integer.MIN_VALUE};
        for (Object o : regionsTag.values()) {
            if (!(o instanceof Map<?, ?>)) continue;
            @SuppressWarnings("unchecked") Map<String, Object> r = (Map<String, Object>) o;
            int[] pos = Nbt.triple(r.get("Position")), size = Nbt.triple(r.get("Size"));
            if (pos == null || size == null) throw new BlueprintException("a Litematica region without a position or size");
            int[] min = new int[3], abs = new int[3];
            for (int a = 0; a < 3; a++) {
                if (size[a] == 0) throw new BlueprintException("a Litematica region of size 0");
                int end = pos[a] + (size[a] > 0 ? size[a] - 1 : size[a] + 1);
                min[a] = Math.min(pos[a], end);
                abs[a] = Math.abs(size[a]);
                lo[a] = Math.min(lo[a], min[a]);
                hi[a] = Math.max(hi[a], min[a] + abs[a] - 1);
            }
            regions.add(new Region(r, pos, min, abs));
        }
        if (regions.isEmpty()) throw new BlueprintException("a Litematica schematic without regions");
        Map<String, Object> meta = Nbt.compound(root, "Metadata");
        String title = meta == null ? "" : Nbt.string(meta, "Name", "");
        Blueprint.Builder b = Blueprint.builder(hi[0] - lo[0] + 1, hi[1] - lo[1] + 1, hi[2] - lo[2] + 1)
                .name(title.isEmpty() ? name : title)
                .author(meta == null ? "" : Nbt.string(meta, "Author", ""))
                .format(Blueprint.Format.LITEMATIC).dataVersion(Nbt.integer(root, "MinecraftDataVersion", 0));

        for (Region r : regions) {
            List<Object> paletteTags = Nbt.list(r.tag(), "BlockStatePalette");
            if (paletteTags.isEmpty()) continue;
            BlockSpec[] palette = new BlockSpec[paletteTags.size()];
            for (int i = 0; i < palette.length; i++) palette[i] = StructureFormat.state(paletteTags.get(i));
            if (!(r.tag().get("BlockStates") instanceof long[] longs)) {
                throw new BlueprintException("a Litematica region without block states");
            }
            int bits = Math.max(2, Integer.SIZE - Integer.numberOfLeadingZeros(palette.length - 1));
            int sx = r.size()[0], sy = r.size()[1], sz = r.size()[2];
            long volume = (long) sx * sy * sz;
            if ((volume * bits + 63) / 64 > longs.length) {
                throw new BlueprintException("a Litematica region with too little block data");
            }
            int ox = r.min()[0] - lo[0], oy = r.min()[1] - lo[1], oz = r.min()[2] - lo[2];
            long mask = (1L << bits) - 1;
            for (long i = 0; i < volume; i++) {
                int id = entry(longs, bits, mask, i);
                if (id >= palette.length) throw new BlueprintException("a Litematica region using a block missing from its palette");
                BlockSpec s = palette[id];
                int x = (int) (i % sx), z = (int) ((i / sx) % sz), y = (int) (i / ((long) sx * sz));
                // overlapping regions: a real block wins over another region's air
                if (s.isAir() && b.get(ox + x, oy + y, oz + z) != null) continue;
                b.set(ox + x, oy + y, oz + z, s);
            }
            for (Object o : Nbt.list(r.tag(), "TileEntities")) {
                if (!(o instanceof Map<?, ?>)) continue;
                @SuppressWarnings("unchecked") Map<String, Object> be = new java.util.LinkedHashMap<>((Map<String, Object>) o);
                int[] p = Nbt.triple(be);
                if (p == null || p[0] < 0 || p[1] < 0 || p[2] < 0 || p[0] >= sx || p[1] >= sy || p[2] >= sz) continue;
                be.remove("x");
                be.remove("y");
                be.remove("z");
                b.blockEntity(ox + p[0], oy + p[1], oz + p[2], be);
            }
            for (Object o : Nbt.list(r.tag(), "Entities")) {
                if (!(o instanceof Map<?, ?>)) continue;
                @SuppressWarnings("unchecked") Map<String, Object> e = (Map<String, Object>) o;
                double[] p = StructureFormat.doubles(e.get("Pos"));
                // entities are saved relative to the region's Position (block entities: to its min corner)
                if (p != null) b.entity(r.pos()[0] - lo[0] + p[0], r.pos()[1] - lo[1] + p[1], r.pos()[2] - lo[2] + p[2], e);
            }
        }
        return b.build();
    }

    /** Entry {@code i} of a packed array (Litematica's LitematicaBitArray.getAt). */
    static int entry(long[] longs, int bits, long mask, long i) {
        long start = i * bits;
        int startLong = (int) (start >> 6);
        int endLong = (int) (((i + 1) * bits - 1) >> 6);
        int offset = (int) (start & 63);
        if (startLong == endLong) return (int) (longs[startLong] >>> offset & mask);
        return (int) ((longs[startLong] >>> offset | longs[endLong] << (64 - offset)) & mask);
    }

    /** The other way round, for tests and (later) writing: values packed as Litematica packs them. */
    static long[] pack(int[] values, int bits) {
        long[] longs = new long[(int) (((long) values.length * bits + 63) / 64)];
        long mask = (1L << bits) - 1;
        for (int i = 0; i < values.length; i++) {
            long start = (long) i * bits;
            int startLong = (int) (start >> 6);
            int endLong = (int) (((long) (i + 1) * bits - 1) >> 6);
            int offset = (int) (start & 63);
            longs[startLong] |= (values[i] & mask) << offset;
            if (startLong != endLong) longs[endLong] |= (values[i] & mask) >>> (64 - offset);
        }
        return longs;
    }
}
