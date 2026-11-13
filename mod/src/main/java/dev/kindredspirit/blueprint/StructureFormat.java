package dev.kindredspirit.blueprint;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Vanilla structure templates ({@code .nbt}): what a structure block saves, what {@code /place template}
 * places, what villages and every built-in structure are made of, and what Create's schematics are.
 *
 * <pre>
 * DataVersion: int
 * size: [int, int, int]
 * palette: [{Name: "minecraft:oak_stairs", Properties: {facing: "east", ...}}, ...]
 *   (or palettes: [[...], [...]], several looks of one shape, like shipwrecks; we take the first)
 * blocks: [{state: int (palette index), pos: [x, y, z], nbt: {...} (a block entity, optional)}, ...]
 * entities: [{pos: [double x3], blockPos: [int x3], nbt: {id: ..., ...}}, ...]
 * </pre>
 *
 * Cells not listed in {@code blocks} are left alone (that's how a structure void is saved).
 */
public final class StructureFormat {
    private StructureFormat() {}

    static boolean looksLike(Map<String, Object> root) {
        return root.get("size") instanceof List<?> && root.get("blocks") instanceof List<?>
                && (root.get("palette") instanceof List<?> || root.get("palettes") instanceof List<?>);
    }

    public static Blueprint read(Map<String, Object> root, String name) {
        int[] size = Nbt.triple(root.get("size"));
        if (size == null) throw new BlueprintException("structure file without a size");
        List<Object> paletteTags = Nbt.list(root, "palette");
        if (paletteTags.isEmpty()) {
            List<Object> palettes = Nbt.list(root, "palettes");
            if (!palettes.isEmpty() && palettes.get(0) instanceof List<?> first) paletteTags = new ArrayList<>(first);
        }
        List<BlockSpec> palette = new ArrayList<>(paletteTags.size());
        for (Object t : paletteTags) palette.add(state(t));

        Blueprint.Builder b = Blueprint.builder(size[0], size[1], size[2])
                .name(name).author(Nbt.string(root, "author", ""))
                .format(Blueprint.Format.STRUCTURE).dataVersion(Nbt.integer(root, "DataVersion", 0));
        for (Object o : Nbt.list(root, "blocks")) {
            if (!(o instanceof Map<?, ?>)) continue;
            @SuppressWarnings("unchecked") Map<String, Object> block = (Map<String, Object>) o;
            int[] pos = Nbt.triple(block.get("pos"));
            int st = Nbt.integer(block, "state", -1);
            if (pos == null || st < 0 || st >= palette.size()) {
                throw new BlueprintException("structure file with a broken block entry");
            }
            b.set(pos[0], pos[1], pos[2], palette.get(st));
            b.blockEntity(pos[0], pos[1], pos[2], Nbt.compound(block, "nbt"));
        }
        for (Object o : Nbt.list(root, "entities")) {
            if (!(o instanceof Map<?, ?>)) continue;
            @SuppressWarnings("unchecked") Map<String, Object> e = (Map<String, Object>) o;
            double[] pos = doubles(e.get("pos"));
            if (pos != null) b.entity(pos[0], pos[1], pos[2], Nbt.compound(e, "nbt"));
        }
        return b.build();
    }

    /** {Name, Properties} as structure files, Litematica palettes and the game's NbtUtils write it. */
    static BlockSpec state(Object tag) {
        if (!(tag instanceof Map<?, ?> m) || !(m.get("Name") instanceof String n)) {
            throw new BlueprintException("palette entry without a block name");
        }
        Map<String, String> props = new LinkedHashMap<>();
        if (m.get("Properties") instanceof Map<?, ?> p) {
            p.forEach((k, v) -> props.put(String.valueOf(k), String.valueOf(v)));
        }
        return Renames.apply(new BlockSpec(n, props));
    }

    static Map<String, Object> stateTag(BlockSpec s) {
        Map<String, Object> t = new LinkedHashMap<>();
        t.put("Name", s.name());
        if (!s.properties().isEmpty()) t.put("Properties", new LinkedHashMap<String, Object>(s.properties()));
        return t;
    }

    static double[] doubles(Object v) {
        if (v instanceof List<?> l && l.size() == 3 && l.get(0) instanceof Number) {
            return new double[]{((Number) l.get(0)).doubleValue(), ((Number) l.get(1)).doubleValue(),
                    ((Number) l.get(2)).doubleValue()};
        }
        return null;
    }

    /**
     * As a structure file, so what she remembers can be loaded by a structure block, placed with
     * {@code /place template}, printed by Create's schematicannon or opened by any schematic tool.
     * Cells to leave alone aren't listed; air is (it clears).
     */
    public static Map<String, Object> write(Blueprint bp, int dataVersion) {
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("DataVersion", dataVersion);
        root.put("size", List.of(bp.width(), bp.height(), bp.length()));
        List<Object> palette = new ArrayList<>();
        for (BlockSpec s : bp.palette()) palette.add(stateTag(s));
        root.put("palette", palette);
        Map<BlockSpec, Integer> ids = new LinkedHashMap<>();
        for (int i = 0; i < bp.palette().size(); i++) ids.put(bp.palette().get(i), i);
        List<Object> blocks = new ArrayList<>();
        for (int y = 0; y < bp.height(); y++) {
            for (int z = 0; z < bp.length(); z++) {
                for (int x = 0; x < bp.width(); x++) {
                    BlockSpec s = bp.at(x, y, z);
                    if (s == null) continue;
                    Map<String, Object> block = new LinkedHashMap<>();
                    block.put("state", ids.get(s));
                    block.put("pos", List.of(x, y, z));
                    Map<String, Object> be = bp.blockEntityAt(x, y, z);
                    if (be != null) block.put("nbt", be);
                    blocks.add(block);
                }
            }
        }
        root.put("blocks", blocks);
        List<Object> entities = new ArrayList<>();
        for (Blueprint.Entity e : bp.entities()) {
            Map<String, Object> t = new LinkedHashMap<>();
            t.put("pos", List.of(e.x(), e.y(), e.z()));
            t.put("blockPos", List.of((int) Math.floor(e.x()), (int) Math.floor(e.y()), (int) Math.floor(e.z())));
            t.put("nbt", e.nbt());
            entities.add(t);
        }
        root.put("entities", entities);
        return root;
    }
}
