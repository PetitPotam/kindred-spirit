package dev.kindredspirit.blueprint;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Village houses, shipwrecks, the pillager watchtower, the igloo and ruined portals, straight from the game (#181):
 * Minecraft's own structure templates ({@code data/minecraft/structure/} inside the game) are copied, on the player's
 * computer, into a blueprint folder of their own, so every player has them, on every Minecraft version, and the
 * catalogue describes and pictures them like any other blueprint. Nothing of Mojang's is shipped with the mod.
 * Copied again only when the game's version changes, so a file you remove from the folder stays removed. Plain Java.
 */
public final class GameStructures {
    private GameStructures() {}

    public static final String FOLDER = "blueprints-from-minecraft", STAMP = ".copied-from";

    private static final Pattern VILLAGE = Pattern.compile("village/(plains|desert|savanna|taiga|snowy)/(houses|town_centers)/([a-z0-9_]+)\\.nbt");
    private static final Pattern SHIPWRECK = Pattern.compile("shipwreck/([a-z0-9_]+)\\.nbt");
    private static final Pattern PORTAL = Pattern.compile("ruined_portal/(giant_)?portal_(\\d+)\\.nbt");

    /**
     * The blueprint file a template becomes, named as people ask for it ({@code village_plains_small_house_1.nbt}),
     * or null when it isn't one to build on its own (a village's zombie version, a broken-up shipwreck half, the
     * igloo's basement).
     *
     * @param rel the template's path under {@code data/minecraft/structure/}
     */
    public static String fileName(String rel) {
        String r = rel.replace('\\', '/');
        Matcher m = VILLAGE.matcher(r);
        if (m.matches()) {
            String name = m.group(3), biome = m.group(1);
            if (name.contains("zombie")) return null;
            return "village_" + (name.startsWith(biome + "_") ? name : biome + "_" + name) + ".nbt";
        }
        m = SHIPWRECK.matcher(r);
        if (m.matches()) {
            String name = m.group(1);
            return name.endsWith("_full") || name.equals("with_mast") ? "shipwreck_" + name + ".nbt" : null;
        }
        m = PORTAL.matcher(r);
        if (m.matches()) return "ruined_" + (m.group(1) == null ? "" : "giant_") + "portal_" + m.group(2) + ".nbt";
        if (r.equals("pillager_outpost/watchtower.nbt")) return "pillager_watchtower.nbt";
        if (r.equals("igloo/top.nbt")) return "igloo.nbt";
        return null;
    }

    /**
     * Copies the templates from {@code structures} (the game's {@code data/minecraft/structure} folder, inside its
     * jar) into {@code out}, unless they were already copied from this version of the game. Returns how many.
     */
    public static int copy(Path structures, Path out, String gameVersion) throws IOException {
        Path stamp = out.resolve(STAMP);
        if (Files.exists(stamp) && Files.readString(stamp, StandardCharsets.UTF_8).trim().equals(gameVersion)) return 0;
        List<Path> templates = new ArrayList<>();
        try (var walk = Files.walk(structures)) {
            walk.filter(Files::isRegularFile).forEach(templates::add);
        }
        Files.createDirectories(out);
        int n = 0;
        for (Path t : templates) {
            String name = fileName(structures.relativize(t).toString());
            if (name == null) continue;
            Files.copy(t, out.resolve(name), StandardCopyOption.REPLACE_EXISTING);
            n++;
        }
        Files.writeString(out.resolve("SOURCES.txt"), """
                Where these blueprints come from

                - village_*, igloo, ruined_*, shipwreck_*, pillager_watchtower: Minecraft %s's own structure templates,
                  copied from the game on this computer by Kindred Spirit (for playing here, not for sharing).
                """.formatted(gameVersion), StandardCharsets.UTF_8);
        Files.writeString(stamp, gameVersion, StandardCharsets.UTF_8);
        return n;
    }
}
