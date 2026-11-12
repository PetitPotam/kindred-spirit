package dev.kindredspirit.blueprint;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Sponge schematics ({@code .schem}), what WorldEdit and FastAsyncWorldEdit save and most build sites
 * offer. Versions 1, 2 and 3 (https://github.com/SpongePowered/Schematic-Specification).
 *
 * <pre>
 * v3: {Schematic: {Version: 3, DataVersion, Width, Height, Length (unsigned shorts), Offset, Metadata,
 *      Blocks: {Palette: {"minecraft:oak_stairs[facing=east]": int, ...}, Data: varints (byte array),
 *               BlockEntities: [{Pos: int[3], Id, Data: {...}}]},
 *      Entities: [{Pos: [double x3], Id, Data: {...}}]}}
 * v2: the same at the root, flat: Palette, PaletteMax, BlockData, BlockEntities [{Pos, Id, ...rest}]
 * v1: like v2, block entities under TileEntities
 * </pre>
 *
 * Every cell has a block, indexed {@code x + z*Width + y*Width*Length} (the order {@link Blueprint}
 * uses), as unsigned varints of 7 bits per byte, low bits first.
 */
public final class SpongeFormat {
    private SpongeFormat() {}

    static boolean looksLike(Map<String, Object> root) {
        return root.get("Schematic") instanceof Map<?, ?>
                || (root.containsKey("Version") && root.containsKey("Width") && root.containsKey("Length")
                && (root.containsKey("BlockData") || root.containsKey("Blocks")) && !root.containsKey("Materials"));
    }

    public static Blueprint read(Map<String, Object> root, String name) {
        Map<String, Object> s = Nbt.compound(root, "Schematic");
        if (s == null) s = root;
        int version = Nbt.integer(s, "Version", 1);
        if (version > 3) throw new BlueprintException("a Sponge schematic of version " + version + ": I only know versions 1 to 3");
        int w = Nbt.integer(s, "Width", 0) & 0xFFFF, h = Nbt.integer(s, "Height", 0) & 0xFFFF,
                l = Nbt.integer(s, "Length", 0) & 0xFFFF;
        Map<String, Object> meta = Nbt.compound(s, "Metadata");
        String title = meta == null ? "" : Nbt.string(meta, "Name", "");
        Blueprint.Builder b = Blueprint.builder(w, h, l)
                .name(title.isEmpty() ? name : title)
                .author(meta == null ? "" : Nbt.string(meta, "Author", ""))
                .format(Blueprint.Format.SPONGE).dataVersion(Nbt.integer(s, "DataVersion", 0));

        Map<String, Object> container = version >= 3 ? Nbt.compound(s, "Blocks") : s;
        if (container == null) return b.build(); // v3 without blocks (only biomes or entities)
        Map<String, Object> paletteTag = Nbt.compound(container, "Palette");
        if (paletteTag == null) paletteTag = Nbt.compound(container, "BlockPalette"); // v3 changelog's name
        if (paletteTag == null) throw new BlueprintException("a Sponge schematic without a palette (old numeric ids aren't supported)");
        int max = -1;
        for (Object v : paletteTag.values()) if (v instanceof Number n) max = Math.max(max, n.intValue());
        if (max < 0 || max > 1 << 20) throw new BlueprintException("a Sponge schematic with a broken palette");
        BlockSpec[] palette = new BlockSpec[max + 1];
        for (Map.Entry<String, Object> e : paletteTag.entrySet()) {
            if (e.getValue() instanceof Number n && n.intValue() >= 0) {
                palette[n.intValue()] = Renames.apply(BlockSpec.parse(e.getKey()));
            }
        }
        Object raw = container.get(version >= 3 ? "Data" : "BlockData");
        if (!(raw instanceof byte[] data)) throw new BlueprintException("a Sponge schematic without block data");

        int volume = w * h * l, i = 0, pos = 0;
        while (i < volume) {
            if (pos >= data.length) throw new BlueprintException("a Sponge schematic with too little block data");
            int value = 0, shift = 0, bt;
            do {
                if (pos >= data.length || shift > 28) throw new BlueprintException("a Sponge schematic with broken block data");
                bt = data[pos++] & 0xFF;
                value |= (bt & 0x7F) << shift;
                shift += 7;
            } while ((bt & 0x80) != 0);
            if (value >= palette.length || palette[value] == null) {
                throw new BlueprintException("a Sponge schematic using a block missing from its palette");
            }
            int x = i % w, z = (i / w) % l, y = i / (w * l);
            b.set(x, y, z, palette[value]);
            i++;
        }

        List<Object> bes = Nbt.list(container, "BlockEntities");
        if (bes.isEmpty() && version == 1) bes = Nbt.list(s, "TileEntities");
        for (Object o : bes) {
            if (!(o instanceof Map<?, ?>)) continue;
            @SuppressWarnings("unchecked") Map<String, Object> be = (Map<String, Object>) o;
            int[] p = Nbt.triple(be.get("Pos"));
            if (p == null || !inside(p, w, h, l)) continue;
            b.blockEntity(p[0], p[1], p[2], version >= 3 ? withId(Nbt.compound(be, "Data"), be) : rest(be, "Pos"));
        }
        for (Object o : Nbt.list(s, "Entities")) {
            if (!(o instanceof Map<?, ?>)) continue;
            @SuppressWarnings("unchecked") Map<String, Object> e = (Map<String, Object>) o;
            double[] p = StructureFormat.doubles(e.get("Pos"));
            if (p == null) continue;
            b.entity(p[0], p[1], p[2], version >= 3 ? withId(Nbt.compound(e, "Data"), e) : rest(e, "Pos"));
        }
        return b.build();
    }

    private static boolean inside(int[] p, int w, int h, int l) {
        return p[0] >= 0 && p[1] >= 0 && p[2] >= 0 && p[0] < w && p[1] < h && p[2] < l;
    }

    /** v3 keeps the data apart from Id; we keep it the game's way, with {@code id} inside. */
    private static Map<String, Object> withId(Map<String, Object> data, Map<String, Object> outer) {
        Map<String, Object> m = new LinkedHashMap<>(data == null ? Map.of() : data);
        String id = Nbt.string(outer, "Id", "");
        if (!id.isEmpty()) m.put("id", id);
        return m;
    }

    /** v1/v2 keep everything flat beside Pos and Id. */
    private static Map<String, Object> rest(Map<String, Object> flat, String... drop) {
        Map<String, Object> m = new LinkedHashMap<>(flat);
        for (String d : drop) m.remove(d);
        Object id = m.remove("Id");
        if (id instanceof String s && !s.isEmpty()) m.put("id", s);
        return m;
    }

    /** Unsigned varints, 7 bits per byte, low bits first (as the game's network code and Sponge write them). */
    static byte[] varints(int[] values) {
        List<Byte> out = new ArrayList<>(values.length);
        for (int v : values) {
            while ((v & ~0x7F) != 0) {
                out.add((byte) ((v & 0x7F) | 0x80));
                v >>>= 7;
            }
            out.add((byte) v);
        }
        byte[] a = new byte[out.size()];
        for (int i = 0; i < a.length; i++) a[i] = out.get(i);
        return a;
    }
}
