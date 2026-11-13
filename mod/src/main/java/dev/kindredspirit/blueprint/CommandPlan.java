package dev.kindredspirit.blueprint;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * A placed blueprint as Minecraft commands, for her magic building through the command powers
 * (act/Commands: allowlisted, logged, run as the player): runs of the same block in a row become one
 * {@code /fill}, everything else a {@code /setblock}, in the build order of {@link Placement}: clear top
 * down, the frame bottom up, then the details. A door's top half and a bed's head come right after
 * their other half, so the game never sees half a door and removes it. A cottage is about a hundred
 * commands instead of three hundred blocks. Plain Java.
 */
public final class CommandPlan {
    private CommandPlan() {}

    /** One command and the steps it does (the first: where she floats while it runs). */
    public record Command(String text, List<Placement.Step> steps) {
        public Placement.Step first() {
            return steps.get(0);
        }

        public int blocks() {
            return steps.size();
        }
    }

    public static List<Command> of(Placement placement, boolean clearAir) {
        List<Placement.Step> steps = placement.steps(clearAir);
        List<Command> out = new ArrayList<>();
        List<Placement.Step> clear = new ArrayList<>(), frame = new ArrayList<>(), details = new ArrayList<>();
        Map<String, Placement.Step> halves = new HashMap<>();
        for (Placement.Step s : steps) {
            switch (s.kind()) {
                case CLEAR -> clear.add(s);
                case BLOCK -> frame.add(s);
                case DETAIL -> details.add(s);
                case SECOND_HALF -> halves.put(key(s.x(), s.y(), s.z()), s);
            }
        }
        runs(clear, out, true);
        runs(frame, out, false);
        for (Placement.Step d : details) {
            out.add(new Command(setblock(d), List.of(d)));
            Placement.Step other = partner(d, halves);
            if (other != null) {
                halves.remove(key(other.x(), other.y(), other.z()));
                out.add(new Command(setblock(other), List.of(other)));
            }
        }
        for (Placement.Step rest : halves.values()) out.add(new Command(setblock(rest), List.of(rest))); // (no first half found)
        return out;
    }

    /** Runs of the same block along x or z (whichever is longer), within a layer, become one /fill. */
    private static void runs(List<Placement.Step> steps, List<Command> out, boolean clearing) {
        List<Placement.Step> sorted = new ArrayList<>(steps);
        // keep the layer order (top down for clearing, bottom up for the frame); rows in z, then x
        sorted.sort((a, b) -> {
            int c = clearing ? Integer.compare(b.y(), a.y()) : Integer.compare(a.y(), b.y());
            if (c != 0) return c;
            c = Integer.compare(a.z(), b.z());
            return c != 0 ? c : Integer.compare(a.x(), b.x());
        });
        Map<String, Placement.Step> at = new HashMap<>();
        for (Placement.Step s : sorted) at.put(key(s.x(), s.y(), s.z()), s);
        java.util.Set<String> used = new java.util.HashSet<>();
        for (Placement.Step a : sorted) {
            if (used.contains(key(a.x(), a.y(), a.z()))) continue;
            int alongX = extent(a, at, used, 1, 0, clearing), alongZ = extent(a, at, used, 0, 1, clearing);
            int dx = alongX >= alongZ ? 1 : 0, dz = 1 - dx, len = Math.max(alongX, alongZ);
            List<Placement.Step> cells = new ArrayList<>(len);
            for (int i = 0; i < len; i++) {
                used.add(key(a.x() + dx * i, a.y(), a.z() + dz * i));
                cells.add(at.get(key(a.x() + dx * i, a.y(), a.z() + dz * i)));
            }
            String block = clearing ? "minecraft:air" : a.state().toString();
            int ex = a.x() + dx * (len - 1), ez = a.z() + dz * (len - 1);
            out.add(new Command(len == 1 ? "setblock " + a.x() + " " + a.y() + " " + a.z() + " " + block
                    : "fill " + a.x() + " " + a.y() + " " + a.z() + " " + ex + " " + a.y() + " " + ez + " " + block, cells));
        }
    }

    /** How many cells from {@code a} in direction (dx, dz) hold the same unused block (no block entity). */
    private static int extent(Placement.Step a, Map<String, Placement.Step> at, java.util.Set<String> used, int dx, int dz,
                              boolean clearing) {
        int n = 1;
        if (a.blockEntity() != null) return 1;
        while (true) {
            Placement.Step s = at.get(key(a.x() + dx * n, a.y(), a.z() + dz * n));
            if (s == null || used.contains(key(s.x(), s.y(), s.z())) || s.blockEntity() != null
                    || (!clearing && !s.state().equals(a.state()))) return n;
            n++;
        }
    }

    private static String setblock(Placement.Step s) {
        return "setblock " + s.x() + " " + s.y() + " " + s.z() + " " + s.state();
    }

    /** The other half of a door (above) or a bed (the head, toward where it faces). */
    private static Placement.Step partner(Placement.Step d, Map<String, Placement.Step> halves) {
        BlockSpec st = d.state();
        if ("lower".equals(st.get("half"))) return halves.get(key(d.x(), d.y() + 1, d.z()));
        if ("foot".equals(st.get("part"))) {
            int[] f = switch (String.valueOf(st.get("facing"))) {
                case "north" -> new int[]{0, -1};
                case "south" -> new int[]{0, 1};
                case "east" -> new int[]{1, 0};
                case "west" -> new int[]{-1, 0};
                default -> new int[]{0, 0};
            };
            return halves.get(key(d.x() + f[0], d.y(), d.z() + f[1]));
        }
        return null;
    }

    private static String key(int x, int y, int z) {
        return x + "," + y + "," + z;
    }
}
