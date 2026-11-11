package dev.kindredspirit.skin;

import com.google.gson.JsonObject;

import java.util.Locale;

/**
 * How the companion looks: a shape, an optional texture, and a few colors. Read from a small
 * JSON file; every field is optional, so a skin can be as short as {"shape": "cube"}.
 *
 * <pre>
 * {
 *   "name": "Strawberry",            shown in /kindred skins
 *   "shape": "ball",                 ball | cube | wisp
 *   "texture": "strawberry.png",     wrapped around the body (2:1 image; the front is at 1/4 across)
 *   "tint": "none",                  mood (color follows its mood) | none | "#RRGGBB"
 *   "shell": false,                  glassy outer shell with a darker core inside
 *   "shellOpacity": 0.8,
 *   "face": true,                    draw eyes, mouth and cheeks (false if your texture has a face)
 *   "eyes": "#1E1A2E", "mouth": "#3A1A2A", "cheeks": "#FF8FAB" (or "none"),
 *   "size": 1.0,
 *   "glow": false                    ignores darkness, like a little light
 * }
 * </pre>
 * Pure data: no Minecraft classes, so parsing is unit-tested.
 */
public record Skin(String id, String name, Shape shape, String texture, Tint tint, int color, boolean shell,
                   float shellOpacity, boolean face, int eyes, int mouth, int cheeks, float size, boolean glow) {

    public enum Shape { BALL, CUBE, WISP }

    public enum Tint { MOOD, NONE, FIXED }

    public static final int NO_CHEEKS = -1;

    public static Skin fallback() {
        return parse("slime", new JsonObject());
    }

    public static Skin parse(String id, JsonObject o) {
        Shape shape = enumOf(Shape.class, str(o, "shape", "ball"), Shape.BALL);
        boolean wisp = shape == Shape.WISP;
        String tintText = str(o, "tint", "mood");
        Tint tint = tintText.startsWith("#") ? Tint.FIXED : enumOf(Tint.class, tintText, Tint.MOOD);
        String cheeks = str(o, "cheeks", wisp ? "none" : "#FF8FAB");
        return new Skin(
                id,
                str(o, "name", id),
                shape,
                str(o, "texture", ""),
                tint,
                tint == Tint.FIXED ? color(tintText, 0xFFFFFF) : 0xFFFFFF,
                bool(o, "shell", true),
                (float) Math.max(0.05, Math.min(1, num(o, "shellOpacity", wisp ? 0.55 : 0.8))),
                bool(o, "face", true),
                color(str(o, "eyes", "#1E1A2E"), 0x1E1A2E),
                color(str(o, "mouth", "#3A1A2A"), 0x3A1A2A),
                cheeks.equalsIgnoreCase("none") ? NO_CHEEKS : color(cheeks, 0xFF8FAB),
                (float) Math.max(0.3, Math.min(3, num(o, "size", wisp ? 0.8 : 1.0))),
                bool(o, "glow", wisp));
    }

    private static String str(JsonObject o, String k, String d) {
        return o.has(k) && o.get(k).isJsonPrimitive() ? o.get(k).getAsString().trim() : d;
    }

    private static boolean bool(JsonObject o, String k, boolean d) {
        return o.has(k) && o.get(k).isJsonPrimitive() ? o.get(k).getAsBoolean() : d;
    }

    private static double num(JsonObject o, String k, double d) {
        try {
            return o.has(k) ? o.get(k).getAsDouble() : d;
        } catch (RuntimeException e) {
            return d;
        }
    }

    static int color(String s, int d) {
        if (s == null) return d;
        s = s.trim();
        if (s.startsWith("#")) s = s.substring(1);
        if (s.length() != 6) return d;
        try {
            return Integer.parseInt(s, 16);
        } catch (NumberFormatException e) {
            return d;
        }
    }

    private static <E extends Enum<E>> E enumOf(Class<E> type, String s, E d) {
        try {
            return Enum.valueOf(type, s.toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException e) {
            return d;
        }
    }
}
