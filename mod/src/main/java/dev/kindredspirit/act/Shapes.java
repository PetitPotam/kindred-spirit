package dev.kindredspirit.act;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * Any geometric shape at any size (#58): each one is a test "is this block inside?" over its box, turned into blocks
 * from the bottom up. Flat ones lie on the ground (or stand up, {@code vertical}); 3D ones rise from it. Pure Java,
 * tested without the game. Adding a shape is a few lines in {@link #inside2d} or {@link #inside3d} and a name in
 * {@link #FORMS}.
 */
public final class Shapes {
    private Shapes() {}

    public static final int MAX_SIDE = 64;
    public static final int MAX_CELLS = 40_000;

    /** Every name she understands, and the shape it means (synonyms point to the same one). Ordered: flat, then 3D. */
    public static final Map<String, String> FORMS = new LinkedHashMap<>();
    static {
        for (String f : new String[]{"square", "rectangle", "triangle", "circle", "ring", "oval", "polygon", "pentagon",
                "hexagon", "octagon", "star", "heart", "cross", "spiral", "diamond"}) FORMS.put(f, f);
        FORMS.put("disc", "circle");
        FORMS.put("disk", "circle");
        FORMS.put("plus", "cross");
        FORMS.put("rhombus", "diamond");
        for (String f : new String[]{"cube", "box", "sphere", "dome", "cylinder", "cone", "pyramid", "stepped_pyramid",
                "torus", "arch", "ramp"}) FORMS.put(f, f);
        FORMS.put("ball", "sphere");
        FORMS.put("orb", "sphere");
        FORMS.put("tower", "cylinder");
        FORMS.put("column", "cylinder");
        FORMS.put("donut", "torus");
        FORMS.put("doughnut", "torus");
        FORMS.put("ziggurat", "stepped_pyramid");
        FORMS.put("temple", "stepped_pyramid");
        FORMS.put("slope", "ramp");
    }
    private static final Set<String> SOLID_3D = Set.of("cube", "box", "sphere", "dome", "cylinder", "cone", "pyramid",
            "stepped_pyramid", "torus", "arch", "ramp");

    /** The shape a word means ("ball" is a sphere), or null. */
    public static String of(String name) {
        return name == null ? null : FORMS.get(name.trim().toLowerCase(Locale.ROOT).replace(' ', '_').replace('-', '_'));
    }

    public static boolean is3d(String form) {
        return SOLID_3D.contains(form);
    }

    /** Its size when they don't say: {width, length, height}. */
    public static int[] defaults(String form) {
        return switch (form) {
            case "sphere" -> new int[]{9, 9, 9};
            case "dome" -> new int[]{11, 11, 6};
            case "cylinder" -> new int[]{7, 7, 10};
            case "cone" -> new int[]{9, 9, 9};
            case "pyramid", "stepped_pyramid" -> new int[]{11, 11, 6};
            case "torus" -> new int[]{13, 13, 3};
            case "arch" -> new int[]{9, 2, 6};
            case "ramp" -> new int[]{3, 6, 6};
            case "cube", "box" -> new int[]{5, 5, 5};
            case "rectangle" -> new int[]{11, 7, 1};
            default -> new int[]{9, 9, 1};
        };
    }

    /**
     * The blocks of a shape, as {right, up, forward} from the middle of its near edge on the ground, bottom up.
     *
     * @param vertical a flat shape standing up, facing you (a sign, a wall), instead of lying on the ground
     * @param sides    for a polygon: how many sides (3 to 12)
     * @param hollow   only its outline (flat) or shell (3D), {@code thickness} blocks thick
     */
    public static List<int[]> cells(String form, int width, int length, int height, boolean hollow, boolean vertical,
                                    int sides, int thickness) {
        int w = clamp(width, 1, MAX_SIDE), l = clamp(length, 1, MAX_SIDE), h = clamp(height, 1, MAX_SIDE);
        int t = clamp(thickness, 1, 8);
        Set<Long> in = new HashSet<>();
        List<int[]> raw = new ArrayList<>();
        if (is3d(form)) {
            for (int y = 0; y < h; y++) for (int f = 0; f < l; f++) for (int r = 0; r < w; r++) {
                if (inside3d(form, r, y, f, w, l, h)) raw.add(new int[]{r, y, f});
            }
        } else {
            for (int f = 0; f < l; f++) for (int r = 0; r < w; r++) {
                if (inside2d(form, r, f, w, l, sides)) raw.add(new int[]{r, 0, f});
            }
        }
        for (int[] c : raw) in.add(key(c[0], c[1], c[2]));
        List<int[]> out = new ArrayList<>();
        for (int[] c : raw) {
            if (hollow && !edge(in, c, t, is3d(form))) continue;
            int r = c[0] - w / 2, y = c[1], f = c[2];
            out.add(vertical && !is3d(form) ? new int[]{r, f, 0} : new int[]{r, y, f}); // (standing up: forward is up)
            if (out.size() >= MAX_CELLS) break;
        }
        out.sort((a, b) -> a[1] != b[1] ? Integer.compare(a[1], b[1]) : a[2] != b[2] ? Integer.compare(a[2], b[2])
                : Integer.compare(a[0], b[0]));
        return out;
    }

    /** A flat shape: is cell (r, f) of a w x l grid inside it? u and v run from -1 to 1 across it. */
    static boolean inside2d(String form, int r, int f, int w, int l, int sides) {
        double u = w == 1 ? 0 : (r - (w - 1) / 2.0) / ((w - 1) / 2.0 + 0.5);
        double v = l == 1 ? 0 : (f - (l - 1) / 2.0) / ((l - 1) / 2.0 + 0.5);
        return switch (form) {
            case "square", "rectangle" -> true;
            case "triangle" -> Math.abs(u) <= (1 - v) / 2 + 0.5 / Math.max(w, 2); // base near you, tip ahead
            case "circle", "oval", "ring" -> u * u + v * v <= 1.0;
            case "diamond" -> Math.abs(u) + Math.abs(v) <= 1.0 + 0.5 / Math.max(w, 2);
            case "cross" -> Math.abs(u) <= 0.34 || Math.abs(v) <= 0.34;
            case "polygon", "pentagon", "hexagon", "octagon" -> inPolygon(u, v, polygon(
                    form.equals("pentagon") ? 5 : form.equals("hexagon") ? 6 : form.equals("octagon") ? 8 : clamp(sides, 3, 12), 1.0, 1.0));
            case "star" -> inPolygon(u, v, polygon(5, 1.0, 0.42));
            case "heart" -> { // the classic curve: tip toward you on the ground, so standing up the lobes are on top
                double x = u * 1.2, y = v * 1.2 + 0.1;
                double a = x * x + y * y - 1;
                yield a * a * a - x * x * y * y * y <= 0;
            }
            case "spiral" -> { // an Archimedean spiral, 3 blocks between turns
                double dx = r - (w - 1) / 2.0, dz = f - (l - 1) / 2.0, rad = Math.sqrt(dx * dx + dz * dz);
                double b = 3.0 / (2 * Math.PI), theta = Math.atan2(dz, dx);
                if (theta < 0) theta += 2 * Math.PI;
                boolean hit = false;
                for (int k = 0; k < 40 && !hit; k++) hit = Math.abs(rad - b * (theta + 2 * Math.PI * k)) < 0.6;
                yield hit && rad <= Math.min(w, l) / 2.0;
            }
            default -> false;
        };
    }

    /** A 3D shape: is (r, y, f) of a w x h x l box inside it? */
    static boolean inside3d(String form, int r, int y, int f, int w, int l, int h) {
        double u = (r - (w - 1) / 2.0) / (w / 2.0), v = (f - (l - 1) / 2.0) / (l / 2.0);
        double t = h == 1 ? 0 : (y + 0.5) / h; // 0 at the bottom, 1 at the top
        return switch (form) {
            case "cube", "box" -> true;
            case "sphere" -> { double z = 2 * t - 1; yield u * u + v * v + z * z <= 1.0; }
            case "dome" -> u * u + v * v + t * t <= 1.0;
            case "cylinder" -> u * u + v * v <= 1.0;
            case "cone" -> Math.sqrt(u * u + v * v) <= 1.0 - t + 0.5 / h;
            case "pyramid" -> Math.max(Math.abs(u), Math.abs(v)) <= 1.0 - t + 0.5 / h;
            case "stepped_pyramid" -> { // each layer one block in from the last
                int half = Math.max(w, l) / 2;
                int dx = Math.abs(2 * r - (w - 1)) / 2, dz = Math.abs(2 * f - (l - 1)) / 2;
                yield Math.max(dx, dz) <= half - y;
            }
            case "torus" -> { double d = Math.sqrt(u * u + v * v) - 0.65, z = 2 * t - 1; yield d * d + z * z * 0.12 <= 0.35 * 0.35; }
            case "arch" -> { // a round arch across your view: a half ring in the (right, up) plane, l deep
                double dx = r - (w - 1) / 2.0, rad = Math.sqrt(dx * dx + y * y), outer = w / 2.0;
                yield rad <= outer && (rad >= outer - 2 || y >= h - 1 && rad <= outer) && y < Math.max(h, (int) Math.ceil(outer));
            }
            case "ramp" -> y <= (double) f * h / l;
            default -> false;
        };
    }

    private static boolean edge(Set<Long> in, int[] c, int t, boolean three) {
        int[][] dirs = three ? new int[][]{{1, 0, 0}, {-1, 0, 0}, {0, 1, 0}, {0, -1, 0}, {0, 0, 1}, {0, 0, -1}}
                : new int[][]{{1, 0, 0}, {-1, 0, 0}, {0, 0, 1}, {0, 0, -1}};
        for (int k = 1; k <= t; k++) {
            for (int[] d : dirs) {
                if (three && d[1] == -1 && c[1] - k < 0) continue; // (the floor of a hollow shape stays open to the ground)
                if (!in.contains(key(c[0] + d[0] * k, c[1] + d[1] * k, c[2] + d[2] * k))) return true;
            }
        }
        return false;
    }

    private static double[][] polygon(int n, double outer, double inner) {
        boolean star = inner < outer;
        int points = star ? n * 2 : n;
        double[][] p = new double[points][];
        for (int i = 0; i < points; i++) {
            double a = -Math.PI / 2 + i * 2 * Math.PI / points; // a point ahead of you
            double rad = star && i % 2 == 1 ? inner : outer;
            p[i] = new double[]{Math.cos(a) * rad, -Math.sin(a) * rad};
        }
        return p;
    }

    private static boolean inPolygon(double x, double y, double[][] p) {
        boolean in = false;
        for (int i = 0, j = p.length - 1; i < p.length; j = i++) {
            if ((p[i][1] > y) != (p[j][1] > y) && x < (p[j][0] - p[i][0]) * (y - p[i][1]) / (p[j][1] - p[i][1]) + p[i][0]) {
                in = !in;
            }
        }
        return in;
    }

    private static long key(int a, int b, int c) {
        return ((long) (a + 1000) << 40) | ((long) (b + 1000) << 20) | (c + 1000);
    }

    private static int clamp(int v, int lo, int hi) {
        return Math.max(lo, Math.min(hi, v));
    }
}
