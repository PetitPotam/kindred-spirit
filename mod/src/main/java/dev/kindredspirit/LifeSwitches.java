package dev.kindredspirit;

import dev.kindredspirit.life.Behavior;

import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Reads and changes the liveliness switches ({@link Behavior.Settings}) by name, for
 * /kindred life. Works on the very object the companion uses, so a change shows at once.
 */
public final class LifeSwitches {
    private LifeSwitches() {}

    private static final Map<String, String> HELP = Map.ofEntries(
            Map.entry("wander", "wanders around you when you stand still"),
            Map.entry("drift", "gentle drifting beside you: 0 still, 1 normal, 2 lively"),
            Map.entry("switchSides", "switches shoulders now and then"),
            Map.entry("glances", "glances at animals, items and around"),
            Map.entry("lookBack", "looks back at you when you look at it"),
            Map.entry("eyeContactReactions", "gets happy or shy when you hold its gaze"),
            Map.entry("petting", "sneak while looking at it to pet it"),
            Map.entry("watchThreats", "turns to watch nearby monsters"),
            Map.entry("moodGestures", "hops when excited, looks up while thinking"),
            Map.entry("aiGestures", "plays the gestures the AI adds to its replies"),
            Map.entry("dozeAfterSeconds", "dozes off after this many quiet seconds, 0 = never"),
            Map.entry("turnSlack", "degrees you can turn before it floats back to your side, 0 = always at your side"),
            Map.entry("keepOutOfView", "never parks in the middle of your view"));

    public static List<String> names() {
        List<String> out = new ArrayList<>();
        for (Field f : fields()) out.add(f.getName());
        return out;
    }

    public static String help(String name) {
        return HELP.getOrDefault(name, "");
    }

    public static String describe(Behavior.Settings s) {
        StringBuilder b = new StringBuilder();
        for (Field f : fields()) {
            if (!b.isEmpty()) b.append(", ");
            b.append(f.getName()).append('=').append(get(s, f.getName()));
        }
        return b.toString();
    }

    public static String get(Behavior.Settings s, String name) {
        Field f = field(name);
        if (f == null) return null;
        try {
            Object v = f.get(s);
            if (v instanceof Boolean bo) return bo ? "on" : "off";
            if (v instanceof Double d && d == Math.rint(d)) return String.valueOf(d.longValue());
            return String.valueOf(v);
        } catch (IllegalAccessException e) {
            return null;
        }
    }

    public static List<String> suggestions(String name) {
        Field f = field(name);
        if (f == null) return List.of();
        if (f.getType() == boolean.class) return List.of("on", "off");
        return switch (name) {
            case "drift" -> List.of("0", "0.5", "1", "1.5", "2");
            case "dozeAfterSeconds" -> List.of("0", "60", "90", "180", "300");
            case "turnSlack" -> List.of("0", "20", "32", "45", "60");
            default -> List.of();
        };
    }

    /** @return null when it worked, otherwise what was wrong (for the player). */
    public static String set(Behavior.Settings s, String name, String value) {
        Field f = field(name);
        if (f == null) return "No switch called " + name + ". Try: " + String.join(", ", names());
        String v = value.trim().toLowerCase(Locale.ROOT);
        try {
            if (f.getType() == boolean.class) {
                if (v.matches("on|true|yes|1")) f.setBoolean(s, true);
                else if (v.matches("off|false|no|0")) f.setBoolean(s, false);
                else return name + " is on or off";
            } else if (f.getType() == int.class) {
                int n = Integer.parseInt(v);
                if (n < 0 || n > 3600) return name + " goes from 0 to 3600";
                f.setInt(s, n);
            } else if (f.getType() == double.class) {
                double d = Double.parseDouble(v);
                double max = name.equals("turnSlack") ? 120 : 3;
                if (d < 0 || d > max) return name + " goes from 0 to " + (int) max;
                f.setDouble(s, d);
            }
            return null;
        } catch (NumberFormatException e) {
            return name + " needs a number";
        } catch (IllegalAccessException e) {
            return "cannot change " + name;
        }
    }

    /** Puts every switch back to its default, in place (the companion keeps the same object). */
    public static void reset(Behavior.Settings s) {
        Behavior.Settings d = new Behavior.Settings();
        for (Field f : fields()) {
            try {
                f.set(s, f.get(d));
            } catch (IllegalAccessException ignored) {
            }
        }
    }

    private static Field field(String name) {
        for (Field f : fields()) if (f.getName().equalsIgnoreCase(name)) return f;
        return null;
    }

    private static List<Field> fields() {
        List<Field> out = new ArrayList<>();
        for (Field f : Behavior.Settings.class.getFields()) {
            if (!Modifier.isStatic(f.getModifiers())) out.add(f);
        }
        return out;
    }
}
