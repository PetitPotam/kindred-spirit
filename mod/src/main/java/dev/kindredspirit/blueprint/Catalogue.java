package dev.kindredspirit.blueprint;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * What a blueprint is, in words she (and the player) can use to find the right one: a category (house,
 * workshop, farm, well, decoration, portal, ship, tower, shape...), a style or biome, a plain description
 * ("a plains smithy, the armorer's, with a blast furnace; 9 x 8, 8 high"), beds, size, block count, main
 * materials, tags, and what to say to her to build it. From the file's name (Minecraft's own templates
 * follow a clear scheme: village_<biome>_<building>_<n>) checked against what's really in it (a smithy is
 * only said to have a blast furnace if one is there). Plain Java.
 */
public final class Catalogue {
    private Catalogue() {}

    public static final List<String> BIOMES = List.of("plains", "desert", "savanna", "taiga", "snowy");
    public static final List<String> CATEGORIES = List.of("house", "workshop", "farm", "well", "decoration", "portal", "ship",
            "tower", "castle", "shape", "other");

    /** A village building's kind: [category, words for it, its job block or null]. */
    private record Kind(String category, String words, String jobBlock) {}

    private static final Map<String, Kind> VILLAGE = Map.ofEntries(
            Map.entry("small_house", new Kind("house", "small house", null)),
            Map.entry("medium_house", new Kind("house", "house", null)),
            Map.entry("big_house", new Kind("house", "big house", null)),
            Map.entry("armorer", new Kind("workshop", "smithy (the armorer's)", "blast_furnace")),
            Map.entry("armorer_house", new Kind("workshop", "smithy (the armorer's)", "blast_furnace")),
            Map.entry("weaponsmith", new Kind("workshop", "weaponsmith's forge", "grindstone")),
            Map.entry("weapon_smith", new Kind("workshop", "weaponsmith's forge", "grindstone")),
            Map.entry("tool_smith", new Kind("workshop", "toolsmith's workshop", "smithing_table")),
            Map.entry("butcher_shop", new Kind("workshop", "butcher's shop", "smoker")),
            Map.entry("butchers_shop", new Kind("workshop", "butcher's shop", "smoker")),
            Map.entry("cartographer", new Kind("workshop", "mapmaker's house (the cartographer's)", "cartography_table")),
            Map.entry("cartographer_house", new Kind("workshop", "mapmaker's house (the cartographer's)", "cartography_table")),
            Map.entry("fisher", new Kind("workshop", "fisher's cottage", "barrel")),
            Map.entry("fisher_cottage", new Kind("workshop", "fisher's cottage", "barrel")),
            Map.entry("fletcher_house", new Kind("workshop", "fletcher's house (arrows)", "fletching_table")),
            Map.entry("library", new Kind("workshop", "library", "lectern")),
            Map.entry("mason", new Kind("workshop", "mason's house", "stonecutter")),
            Map.entry("masons_house", new Kind("workshop", "mason's house", "stonecutter")),
            Map.entry("shepherd", new Kind("workshop", "shepherd's house", "loom")),
            Map.entry("shepherd_house", new Kind("workshop", "shepherd's house", "loom")),
            Map.entry("shepherds_house", new Kind("workshop", "shepherd's house", "loom")),
            Map.entry("tannery", new Kind("workshop", "tannery (the leatherworker's)", "cauldron")),
            Map.entry("temple", new Kind("workshop", "temple (the cleric's)", "brewing_stand")),
            Map.entry("farm", new Kind("farm", "crop field", "composter")),
            Map.entry("small_farm", new Kind("farm", "small crop field", "composter")),
            Map.entry("large_farm", new Kind("farm", "big crop field", "composter")),
            Map.entry("animal_pen", new Kind("farm", "animal pen", null)),
            Map.entry("stable", new Kind("farm", "stable", null)),
            Map.entry("meeting_point", new Kind("well", "village square", null)),
            Map.entry("fountain", new Kind("well", "fountain", null)),
            Map.entry("accessory", new Kind("decoration", "little decoration", null)));

    /** Who made it and its licence, matched by file name from SOURCES.txt. */
    public interface Sources {
        String of(String fileName);
    }

    public static JsonObject describe(String fileName, Blueprint bp, Sources sources) {
        String base = Blueprints.baseName(fileName);
        String low = base.toLowerCase(Locale.ROOT);
        Map<String, Integer> mats = bp.materials();
        String category = "other", style = "", what;
        Set<String> tags = new LinkedHashSet<>();
        String job = null;

        if (low.startsWith("village_")) {
            String rest = low.substring("village_".length());
            String biome = BIOMES.stream().filter(b -> rest.startsWith(b + "_")).findFirst().orElse("");
            String building = rest.substring(biome.isEmpty() ? 0 : biome.length() + 1).replaceAll("_?\\d+$", "");
            Kind k = VILLAGE.get(building);
            if (k == null) k = new Kind(guessCategory(building), building.replace('_', ' '), null);
            category = k.category();
            style = biome;
            String words = k.words();
            if (building.equals("meeting_point") || building.equals("fountain")) {
                boolean water = mats.containsKey("minecraft:water_bucket"), bell = mats.containsKey("minecraft:bell");
                words = water && bell ? "village well with a bell" : water ? "village well" : bell ? "village square with a bell" : words;
            }
            // "a small desert house", "a big taiga crop field", "a plains library"
            String size = words.startsWith("small ") ? "small " : words.startsWith("big ") ? "big " : "";
            what = article(size + biome + " " + words.substring(size.length()));
            if (k.jobBlock() != null && mats.containsKey("minecraft:" + k.jobBlock())) {
                job = k.jobBlock();
                what += ", with a " + k.jobBlock().replace('_', ' ');
            }
            tags.add("village");
            tags.add(biome);
            for (String w : words.replaceAll("[()',]", " ").split("\\s+")) if (w.length() > 2) tags.add(w);
        } else if (low.startsWith("ruined_giant_portal")) {
            category = "portal"; style = "ruined"; what = "a big ruined nether portal";
        } else if (low.startsWith("ruined_portal")) {
            category = "portal"; style = "ruined"; what = "a ruined nether portal";
        } else if (low.startsWith("shipwreck")) {
            category = "ship"; style = "wreck";
            what = low.contains("mast") ? "a shipwreck with its mast" : low.contains("upsidedown") ? "a shipwreck, upside down"
                    : low.contains("sideways") ? "a shipwreck lying on its side" : "a shipwreck, upright";
        } else if (low.equals("igloo") || low.startsWith("igloo_")) {
            category = "house"; style = "snowy"; what = "an igloo (a snow dome home)";
        } else if (low.contains("watchtower") || low.contains("outpost")) {
            category = "tower"; style = "pillager"; what = "a pillager watchtower (dark oak and birch)";
        } else if (low.matches("circle_\\d+x\\d+")) {
            category = "shape"; style = "circle";
            what = "a circle " + bp.width() + " blocks across (an outline to build on)";
        } else {
            category = guessCategory(low);
            what = article(low.replaceAll("_?\\d+$", "").replace('_', ' ').replace('-', ' ').trim());
        }

        int beds = 0;
        for (Map.Entry<String, Integer> e : mats.entrySet()) if (e.getKey().endsWith("_bed")) beds += e.getValue();
        if (beds > 0 && !category.equals("shape")) what += beds == 1 ? " (a bed)" : " (beds for " + beds + ")";

        String sizeClass = sizeClass(bp);
        tags.add(category);
        if (!style.isEmpty()) tags.add(style);
        tags.add(sizeClass);
        String wood = mainWood(mats);
        if (wood != null) tags.add(wood);
        if (job != null) tags.add(job.replace('_', ' '));

        JsonObject o = new JsonObject();
        o.addProperty("file", fileName);
        o.addProperty("name", base);
        o.addProperty("category", category);
        o.addProperty("style", style);
        o.addProperty("what", what);
        o.addProperty("width", bp.width());
        o.addProperty("length", bp.length());
        o.addProperty("height", bp.height());
        o.addProperty("size", sizeClass);
        o.addProperty("blocks", bp.solidBlocks());
        o.addProperty("beds", beds);
        JsonArray m = new JsonArray();
        int i = 0;
        for (Map.Entry<String, Integer> e : mats.entrySet()) {
            if (i++ >= 6) break;
            JsonArray pair = new JsonArray();
            pair.add(e.getKey().replace("minecraft:", ""));
            pair.add(e.getValue());
            m.add(pair);
        }
        o.add("materials", m);
        JsonArray t = new JsonArray();
        tags.forEach(t::add);
        o.add("tags", t);
        o.addProperty("say", "Pip, build " + say(base, category, style, what) + " (" + base + ")");
        String src = sources == null ? null : sources.of(fileName);
        if (src != null) o.addProperty("source", src);
        o.addProperty("summary", summary(what, bp));
        return o;
    }

    /** "a plains smithy (the armorer's), with a blast furnace: 9 x 8, 8 high, 239 blocks" */
    static String summary(String what, Blueprint bp) {
        return what + ": " + bp.width() + " x " + bp.length() + ", " + bp.height() + " high, " + bp.solidBlocks() + " blocks";
    }

    /** tiny / small / medium / big, from the footprint and the number of blocks. */
    public static String sizeClass(Blueprint bp) {
        int side = Math.max(bp.width(), bp.length()), n = bp.solidBlocks();
        if (n < 40 && side <= 6) return "tiny";
        if (side <= 10 && n <= 300) return "small";
        if (n > 900 || side > 18 && n > 300) return "big";
        return "medium";
    }

    static String guessCategory(String words) {
        String w = " " + words.replace('_', ' ').replace('-', ' ') + " ";
        if (w.matches(".*\\b(house|home|hut|cabin|cottage|lodge|villa|mansion|igloo|shack|tent)s?\\b.*")) return "house";
        if (w.matches(".*\\b(castle|keep|fort|fortress|palace)s?\\b.*")) return "castle";
        if (w.matches(".*\\b(tower|lighthouse|windmill)s?\\b.*")) return "tower";
        if (w.matches(".*\\b(farm|pen|stable|barn|field|garden|coop)s?\\b.*")) return "farm";
        if (w.matches(".*\\b(well|fountain|pond|pool)s?\\b.*")) return "well";
        if (w.matches(".*\\b(portal)s?\\b.*")) return "portal";
        if (w.matches(".*\\b(ship|boat|wreck)s?\\b.*")) return "ship";
        if (w.matches(".*\\b(circle|sphere|dome|ring|square|shape)s?\\b.*")) return "shape";
        if (w.matches(".*\\b(statue|tree|lamp|bench|garden|decoration|arch|bridge)s?\\b.*")) return "decoration";
        if (w.matches(".*\\b(smith|forge|library|shop|workshop|mill|tannery|temple|church)s?\\b.*")) return "workshop";
        return "other";
    }

    private static final List<String> WOODS = List.of("dark_oak", "oak", "spruce", "birch", "jungle", "acacia", "cherry",
            "mangrove", "bamboo", "crimson", "warped");

    /** The wood or stone that most of it is made of, as a tag ("oak", "sandstone", "spruce"). */
    static String mainWood(Map<String, Integer> mats) {
        for (String item : mats.keySet()) {
            String p = item.replace("minecraft:", "");
            for (String w : WOODS) if (p.startsWith(w + "_")) return w;
            if (p.contains("sandstone")) return "sandstone";
            if (p.contains("terracotta")) return "terracotta";
            if (p.startsWith("cobblestone") || p.startsWith("stone")) return "stone";
            if (p.startsWith("snow")) return "snow";
        }
        return null;
    }

    /** What to say to her: what it is, without the details ("a plains smithy (the armorer's)"). */
    static String say(String base, String category, String style, String what) {
        String w = what.replaceFirst(",? with .*$", "").replaceFirst(" \\((a bed|beds for \\d+)\\)$", "").trim();
        return w.isEmpty() ? base : w;
    }

    private static String article(String words) {
        String w = words.trim();
        return (w.matches("^[aeiou].*") ? "an " : "a ") + w;
    }

    /** Parses SOURCES.txt: lines "- prefix_*, other, x_*: where they come from, licence". */
    public static Sources sources(String text) {
        List<String[]> rules = new ArrayList<>();
        if (text != null) {
            String current = null;
            StringBuilder about = new StringBuilder();
            for (String line : text.split("\\R")) {
                if (line.startsWith("- ")) {
                    if (current != null) rules.add(new String[]{current, about.toString().trim()});
                    int colon = line.indexOf(':');
                    if (colon < 0) { current = null; continue; }
                    current = line.substring(2, colon);
                    about = new StringBuilder(line.substring(colon + 1).trim());
                } else if (current != null && line.startsWith(" ") && !line.isBlank()) {
                    about.append(' ').append(line.trim());
                }
            }
            if (current != null) rules.add(new String[]{current, about.toString().trim()});
        }
        return fileName -> {
            String base = Blueprints.baseName(fileName).toLowerCase(Locale.ROOT);
            for (String[] r : rules) {
                for (String pat : r[0].split(",")) {
                    String p = pat.trim().toLowerCase(Locale.ROOT);
                    if (p.isEmpty()) continue;
                    boolean match = p.endsWith("*") ? base.startsWith(p.substring(0, p.length() - 1)) : base.equals(p);
                    if (match) return r[1];
                }
            }
            return null;
        };
    }
}
