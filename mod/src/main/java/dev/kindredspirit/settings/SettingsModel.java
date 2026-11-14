package dev.kindredspirit.settings;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonPrimitive;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * The in-game settings screen's data (#5), without Minecraft: every setting her dashboard can change (its
 * {@code /api/settings/editable} list: label, help, type, choices, range, value, default), in the same sections as the
 * dashboard's Settings page, and the rules for showing and changing a value. A friend's game, whose Pip runs on
 * another computer, gets only the mod's own settings ({@link #fromFields}).
 */
public final class SettingsModel {
    private SettingsModel() {}

    /** The dashboard's sections, in its order: key, title, where it's saved and when it applies. */
    public static final String[][] GROUPS = {
            {"who", "Who she is", "her brain: her next reply"}, {"ai", "Her AI", "her brain: her next reply"},
            {"voice", "Her voice", "her brain: her next reply"}, {"behaviour", "How she behaves", "her brain: her next reply"},
            {"heart", "Her heart", "her brain: her next reply"}, {"gateway", "AI, voice and hearing", "the gateway: its next call"},
            {"mod", "In game", "this game: at once"}, {"life", "Her liveliness in game", "this game: at once"},
            {"other", "Other", ""}};

    public static final class Entry {
        public final String where, path, label, help, type;
        public final List<String> choices;
        public final double[] range; // min, max, step (or null)
        public JsonElement value;
        public final JsonElement fallback; // the default (or null)

        public Entry(String where, String path, String label, String help, String type, List<String> choices,
                     double[] range, JsonElement value, JsonElement fallback) {
            this.where = where;
            this.path = path;
            this.label = label;
            this.help = help;
            this.type = type;
            this.choices = choices;
            this.range = range;
            this.value = value;
            this.fallback = fallback;
        }

        public String group() {
            return groupOf(where, path);
        }

        public boolean isDefault() {
            return fallback != null && fallback.equals(value);
        }
    }

    /** Which section a setting is in (the dashboard's own rule). */
    public static String groupOf(String where, String path) {
        if (where.equals("gateway")) return "gateway";
        if (where.equals("mod") || where.equals("local")) return path.startsWith("life.") ? "life" : "mod";
        String top = path.split("\\.")[0];
        if (top.equals("name") || top.equals("personality")) return "who";
        for (String[] g : GROUPS) if (g[0].equals(top)) return top;
        return "other";
    }

    public static String title(String group) {
        for (String[] g : GROUPS) if (g[0].equals(group)) return g[1];
        return group;
    }

    public static String appliesWhen(String group) {
        for (String[] g : GROUPS) if (g[0].equals(group)) return g[2];
        return "";
    }

    /** The dashboard's list, read. Anything it doesn't know how to show is left out. */
    public static List<Entry> fromDashboard(JsonObject editable) {
        List<Entry> out = new ArrayList<>();
        JsonArray all = editable.has("settings") ? editable.getAsJsonArray("settings") : new JsonArray();
        for (JsonElement el : all) {
            if (!el.isJsonObject()) continue;
            JsonObject o = el.getAsJsonObject();
            String type = str(o, "type");
            if (!(type.equals("bool") || type.equals("choice") || type.equals("int") || type.equals("float")
                    || type.equals("text") || type.equals("longtext"))) continue;
            List<String> choices = new ArrayList<>();
            if (o.has("choices") && o.get("choices").isJsonArray()) {
                for (JsonElement c : o.getAsJsonArray("choices")) choices.add(c.isJsonNull() ? "" : c.getAsString());
            }
            if (type.equals("choice") && choices.isEmpty()) continue;
            double[] range = null;
            if (o.has("range") && o.get("range").isJsonArray() && o.getAsJsonArray("range").size() == 3) {
                JsonArray r = o.getAsJsonArray("range");
                range = new double[]{r.get(0).getAsDouble(), r.get(1).getAsDouble(), r.get(2).getAsDouble()};
            }
            out.add(new Entry(str(o, "where"), str(o, "path"), str(o, "label"), o.has("help") && !o.get("help").isJsonNull()
                    ? o.get("help").getAsString() : "", type, choices, range, o.get("value"),
                    o.has("default") && !o.get("default").isJsonNull() ? o.get("default") : null));
        }
        return out;
    }

    /** The mod's own settings, from its fields (a friend's game: her brain and dashboard are on another computer). */
    public static List<Entry> fromFields(Object config, Object defaults) {
        List<Entry> out = new ArrayList<>();
        for (java.lang.reflect.Field f : config.getClass().getFields()) {
            int m = f.getModifiers();
            if (java.lang.reflect.Modifier.isStatic(m) || java.lang.reflect.Modifier.isTransient(m)) continue;
            String type = f.getType() == boolean.class ? "bool" : f.getType() == int.class ? "int"
                    : f.getType() == float.class || f.getType() == double.class ? "float" : f.getType() == String.class ? "text" : null;
            if (type == null || HIDDEN_HERE.contains(f.getName())) continue;
            try {
                out.add(new Entry("local", f.getName(), words(f.getName()), "", type, List.of(), null,
                        json(f.get(config)), defaults == null ? null : json(f.get(defaults))));
            } catch (IllegalAccessException ignored) {
            }
        }
        return out;
    }

    // (where her brain is and how the game reaches it: changed by hand, not from a list)
    private static final List<String> HIDDEN_HERE = List.of("brainHost", "brainPort", "dashboardPort", "tokenFile", "follow");

    /** "voiceVolume" → "voice volume". */
    static String words(String field) {
        return field.replaceAll("([a-z])([A-Z])", "$1 $2").toLowerCase(Locale.ROOT);
    }

    static JsonElement json(Object v) {
        if (v instanceof Boolean b) return new JsonPrimitive(b);
        if (v instanceof Number n) return new JsonPrimitive(n);
        return v == null ? null : new JsonPrimitive(String.valueOf(v));
    }

    /** How a value reads on a button: on/off, (empty), a number without needless decimals. */
    public static String show(Entry e, JsonElement v) {
        if (v == null || v.isJsonNull()) return "?";
        if (e.type.equals("bool")) return v.getAsBoolean() ? "on" : "off";
        if (e.type.equals("float")) {
            double d = v.getAsDouble();
            return d == Math.rint(d) ? String.valueOf((long) d) : String.format(Locale.ROOT, "%.2f", d).replaceAll("0$", "");
        }
        String s = v.getAsString();
        return s.isEmpty() ? (e.type.equals("choice") ? "(same / default)" : "(empty)") : s;
    }

    /** A choice button pressed: the next one (shift: the one before), round. */
    public static String nextChoice(Entry e, boolean back) {
        String now = e.value == null || e.value.isJsonNull() ? "" : e.value.getAsString();
        int i = e.choices.indexOf(now), n = e.choices.size();
        return e.choices.get(i < 0 ? 0 : Math.floorMod(i + (back ? -1 : 1), n));
    }

    /** A number pressed (+ or −): one step, kept in its range. */
    public static JsonElement step(Entry e, int direction) {
        double now = e.value == null || e.value.isJsonNull() ? 0 : e.value.getAsDouble();
        double step = e.range != null ? e.range[2] : e.type.equals("int") ? 1 : 0.1;
        double v = Math.round((now + direction * step) / step) * step;
        if (e.range != null) v = Math.max(e.range[0], Math.min(e.range[1], v));
        if (e.type.equals("int")) return new JsonPrimitive(Math.round(v));
        return new JsonPrimitive(Math.round(v * 1000) / 1000.0);
    }

    /** Typed text for a number or a text: the value to save, or null when it isn't one (it's left as it was). */
    public static JsonElement parse(Entry e, String typed) {
        String t = typed.trim();
        try {
            return switch (e.type) {
                case "int" -> new JsonPrimitive(clamp(e, Long.parseLong(t)));
                case "float" -> new JsonPrimitive(clamp(e, Double.parseDouble(t.replace(',', '.'))));
                case "text", "longtext" -> new JsonPrimitive(typed.length() > (e.type.equals("text") ? 80 : 2000)
                        ? typed.substring(0, e.type.equals("text") ? 80 : 2000) : typed);
                default -> null;
            };
        } catch (NumberFormatException x) {
            return null;
        }
    }

    private static long clamp(Entry e, long v) {
        return e.range == null ? v : (long) Math.max(e.range[0], Math.min(e.range[1], v));
    }

    private static double clamp(Entry e, double v) {
        return e.range == null ? v : Math.max(e.range[0], Math.min(e.range[1], v));
    }

    /** The settings of one section, a page at a time. */
    public static List<Entry> page(List<Entry> all, String group, int page, int perPage) {
        List<Entry> in = all.stream().filter(e -> e.group().equals(group)).toList();
        int from = Math.min(in.size(), Math.max(0, page) * perPage);
        return in.subList(from, Math.min(in.size(), from + perPage));
    }

    public static int pages(List<Entry> all, String group, int perPage) {
        long n = all.stream().filter(e -> e.group().equals(group)).count();
        return (int) Math.max(1, (n + perPage - 1) / perPage);
    }

    /** The sections that have settings, in order. */
    public static List<String> groups(List<Entry> all) {
        List<String> out = new ArrayList<>();
        for (String[] g : GROUPS) if (all.stream().anyMatch(e -> e.group().equals(g[0]))) out.add(g[0]);
        return out;
    }

    /** One change, as the dashboard takes it ({"changes": [...]}): a value, or back to the default. */
    public static JsonObject change(Entry e, JsonElement value) {
        JsonObject ch = new JsonObject();
        ch.addProperty("where", e.where);
        ch.addProperty("path", e.path);
        if (value == null) ch.addProperty("default", true);
        else ch.add("value", value);
        JsonArray list = new JsonArray();
        list.add(ch);
        JsonObject body = new JsonObject();
        body.add("changes", list);
        return body;
    }

    private static String str(JsonObject o, String k) {
        return o.has(k) && !o.get(k).isJsonNull() ? o.get(k).getAsString() : "";
    }
}
