package dev.kindredspirit.blueprint;

import java.util.Collections;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;

/**
 * A block with its properties, as every modern schematic format stores it: {@code minecraft:oak_stairs}
 * with {@code facing=east, half=bottom}. Written the way commands and Sponge palettes write it:
 * {@code minecraft:oak_stairs[facing=east,half=bottom]} (properties sorted, so equal states are equal
 * strings, as /setblock accepts them).
 *
 * <p>Turning a state with the building (a quarter turn clockwise, seen from above) changes the
 * properties that name a direction: {@code facing}, {@code axis}, the 16-step {@code rotation} of signs
 * and banners, the {@code north/east/south/west} sides of fences, walls, panes, vines and redstone,
 * rail {@code shape}s and the {@code orientation} of jigsaws and crafters. That covers vanilla's
 * directional blocks; in the game the block's own {@code BlockState.rotate} is still the authority
 * (modded blocks), this is for plain-Java previews, tests and command strings.
 */
public record BlockSpec(String name, Map<String, String> properties) {

    public static final BlockSpec AIR = new BlockSpec("minecraft:air", Map.of());

    public BlockSpec {
        name = normalize(name);
        properties = Collections.unmodifiableMap(new TreeMap<>(properties == null ? Map.of() : properties));
    }

    public static BlockSpec of(String name) {
        return new BlockSpec(name, Map.of());
    }

    /** Parses {@code minecraft:oak_stairs[facing=east,half=bottom]} (namespace optional, spaces allowed). */
    public static BlockSpec parse(String s) {
        if (s == null || s.isBlank()) throw new IllegalArgumentException("empty block state");
        String t = s.trim();
        int open = t.indexOf('[');
        if (open < 0) return of(t);
        if (!t.endsWith("]")) throw new IllegalArgumentException("bad block state: " + s);
        Map<String, String> props = new TreeMap<>();
        String inner = t.substring(open + 1, t.length() - 1).trim();
        if (!inner.isEmpty()) {
            for (String kv : inner.split(",")) {
                int eq = kv.indexOf('=');
                if (eq <= 0) throw new IllegalArgumentException("bad block state property in " + s);
                props.put(kv.substring(0, eq).trim(), kv.substring(eq + 1).trim());
            }
        }
        return new BlockSpec(t.substring(0, open), props);
    }

    static String normalize(String name) {
        String n = name == null ? "" : name.trim().toLowerCase(Locale.ROOT);
        if (n.isEmpty()) throw new IllegalArgumentException("block without a name");
        return n.contains(":") ? n : "minecraft:" + n;
    }

    /** The path without the namespace: {@code oak_stairs}. */
    public String path() {
        return name.substring(name.indexOf(':') + 1);
    }

    public String get(String property) {
        return properties.get(property);
    }

    public BlockSpec with(String property, String value) {
        Map<String, String> p = new TreeMap<>(properties);
        p.put(property, value);
        return new BlockSpec(name, p);
    }

    /** Air of any kind: nothing to place (but in a template, something to clear). */
    public boolean isAir() {
        return name.equals("minecraft:air") || name.equals("minecraft:cave_air") || name.equals("minecraft:void_air");
    }

    /** The structure void: "leave whatever is there". Never placed. */
    public boolean isVoid() {
        return name.equals("minecraft:structure_void");
    }

    @Override
    public String toString() {
        if (properties.isEmpty()) return name;
        StringBuilder b = new StringBuilder(name).append('[');
        boolean first = true;
        for (Map.Entry<String, String> e : properties.entrySet()) {
            if (!first) b.append(',');
            b.append(e.getKey()).append('=').append(e.getValue());
            first = false;
        }
        return b.append(']').toString();
    }

    // --- turning ---------------------------------------------------------------------------------

    private static final String[] HORIZONTAL = {"north", "east", "south", "west"}; // clockwise

    /** The state turned {@code quarterTurns} times clockwise (seen from above); negative turns go the other way. */
    public BlockSpec rotated(int quarterTurns) {
        int k = Math.floorMod(quarterTurns, 4);
        if (k == 0 || properties.isEmpty()) return this;
        Map<String, String> p = new TreeMap<>(properties);
        for (String key : new String[]{"facing", "horizontal_facing"}) {
            if (p.containsKey(key)) p.put(key, turn(p.get(key), k));
        }
        if (p.containsKey("axis") && (k % 2 == 1)) {
            String a = p.get("axis");
            p.put("axis", a.equals("x") ? "z" : a.equals("z") ? "x" : a);
        }
        if (p.containsKey("rotation")) {
            try {
                p.put("rotation", Integer.toString(Math.floorMod(Integer.parseInt(p.get("rotation")) + 4 * k, 16)));
            } catch (NumberFormatException ignored) {
                // not a number: leave it
            }
        }
        // sides: fences, walls, panes, vines, redstone wire, mushroom blocks, glow lichen...
        String[] sides = new String[4];
        boolean anySide = false;
        for (int i = 0; i < 4; i++) {
            sides[i] = properties.get(HORIZONTAL[i]);
            anySide |= sides[i] != null;
        }
        if (anySide) {
            for (int i = 0; i < 4; i++) {
                String to = HORIZONTAL[(i + k) % 4];
                if (sides[i] == null) p.remove(to);
                else p.put(to, sides[i]);
            }
        }
        if (p.containsKey("shape") && name.endsWith("rail")) p.put("shape", turnRail(p.get("shape"), k));
        if (p.containsKey("orientation")) p.put("orientation", turnEach(p.get("orientation"), k));
        return new BlockSpec(name, p);
    }

    static String turn(String dir, int k) {
        for (int i = 0; i < 4; i++) if (HORIZONTAL[i].equals(dir)) return HORIZONTAL[(i + k) % 4];
        return dir; // up, down, or not a direction
    }

    private static String turnEach(String joined, int k) {
        String[] parts = joined.split("_");
        for (int i = 0; i < parts.length; i++) parts[i] = turn(parts[i], k);
        return String.join("_", parts);
    }

    /** Rails: north_south, east_west, ascending_east, and the curves south_east, south_west, north_west, north_east. */
    static String turnRail(String shape, int k) {
        if (shape.startsWith("ascending_")) return "ascending_" + turn(shape.substring("ascending_".length()), k);
        String[] ab = shape.split("_");
        if (ab.length != 2) return shape;
        String a = turn(ab[0], k), b = turn(ab[1], k);
        boolean straight = (a.equals("north") || a.equals("south")) == (b.equals("north") || b.equals("south"));
        if (straight) return (a.equals("north") || a.equals("south")) ? "north_south" : "east_west";
        // curves are written north/south first, then east/west
        return (a.equals("north") || a.equals("south")) ? a + "_" + b : b + "_" + a;
    }
}
