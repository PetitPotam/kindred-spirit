package dev.kindredspirit.blueprint;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/** #181: the game's own village houses and structures, copied into a blueprint folder on the player's computer. */
class GameStructuresTest {
    @Test
    void templatesAreNamedTheWayPeopleAskForThem() {
        assertEquals("village_plains_small_house_1.nbt", GameStructures.fileName("village/plains/houses/plains_small_house_1.nbt"));
        assertEquals("village_snowy_fountain_01.nbt", GameStructures.fileName("village/snowy/town_centers/snowy_fountain_01.nbt"));
        assertEquals("village_taiga_tool_smith_1.nbt", GameStructures.fileName("village/taiga/houses/tool_smith_1.nbt"));
        assertNull(GameStructures.fileName("village/plains/zombie/houses/plains_small_house_1.nbt"), "zombie villages stay out");
        assertNull(GameStructures.fileName("village/plains/town_centers/plains_meeting_point_1_zombie.nbt"));
        assertNull(GameStructures.fileName("village/plains/streets/corner_01.nbt"), "streets aren't buildings");
        assertEquals("shipwreck_sideways_full.nbt", GameStructures.fileName("shipwreck/sideways_full.nbt"));
        assertEquals("shipwreck_with_mast.nbt", GameStructures.fileName("shipwreck/with_mast.nbt"));
        assertNull(GameStructures.fileName("shipwreck/sideways_full_degraded.nbt"));
        assertNull(GameStructures.fileName("shipwreck/rightsideup_fronthalf.nbt"), "half a ship isn't one");
        assertEquals("ruined_giant_portal_2.nbt", GameStructures.fileName("ruined_portal/giant_portal_2.nbt"));
        assertEquals("ruined_portal_10.nbt", GameStructures.fileName("ruined_portal/portal_10.nbt"));
        assertEquals("pillager_watchtower.nbt", GameStructures.fileName("pillager_outpost/watchtower.nbt"));
        assertEquals("igloo.nbt", GameStructures.fileName("igloo/top.nbt"));
        assertNull(GameStructures.fileName("igloo/bottom.nbt"));
        assertNull(GameStructures.fileName("end_city/ship.nbt"));
    }

    @Test
    void copiedOncePerGameVersionSoARemovedFileStaysRemoved(@TempDir Path tmp) throws Exception {
        Path game = tmp.resolve("structure"), out = tmp.resolve("blueprints-from-minecraft");
        for (String rel : List.of("village/plains/houses/plains_small_house_1.nbt", "igloo/top.nbt", "igloo/bottom.nbt",
                "end_city/ship.nbt")) {
            Files.createDirectories(game.resolve(rel).getParent());
            Files.write(game.resolve(rel), new byte[]{1, 2, 3});
        }
        assertEquals(2, GameStructures.copy(game, out, "26.3"));
        assertTrue(Files.exists(out.resolve("village_plains_small_house_1.nbt")) && Files.exists(out.resolve("igloo.nbt")));
        assertTrue(Files.readString(out.resolve("SOURCES.txt")).contains("Minecraft 26.3's own structure templates"));
        Files.delete(out.resolve("igloo.nbt"));
        assertEquals(0, GameStructures.copy(game, out, "26.3"));
        assertFalse(Files.exists(out.resolve("igloo.nbt")), "you removed it: it stays removed");
        assertEquals(2, GameStructures.copy(game, out, "26.4"), "a new game version: copied again");
        assertTrue(Files.exists(out.resolve("igloo.nbt")));
    }

    @Test
    void theSourcesLineDescribesThem(@TempDir Path tmp) throws Exception {
        Path game = tmp.resolve("structure");
        Files.createDirectories(game.resolve("igloo"));
        Files.write(game.resolve("igloo/top.nbt"), new byte[]{1});
        GameStructures.copy(game, tmp.resolve("out"), "1.21.1");
        var sources = Catalogue.sources(Files.readString(tmp.resolve("out/SOURCES.txt")));
        assertTrue(sources.of("village_plains_small_house_1.nbt").contains("Minecraft 1.21.1's own"));
        assertNull(sources.of("circle_10x10.litematic"));
    }

    @Test
    void templatesSavedByMinecraft26AreReadToo() throws Exception {
        // (26.x writes a palette entry as {id, properties}, 1.21.x as {Name, Properties})
        Map<String, Object> props = new LinkedHashMap<>(Map.of("axis", "y"));
        Map<String, Object> log = new LinkedHashMap<>(Map.of("id", "minecraft:spruce_log", "properties", props));
        Map<String, Object> dirt = new LinkedHashMap<>(Map.of("id", "minecraft:dirt"));
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("DataVersion", 5023);
        root.put("size", new ArrayList<>(List.of(1, 2, 1)));
        root.put("palette", new ArrayList<>(List.of(dirt, log)));
        root.put("blocks", new ArrayList<>(List.of(
                new LinkedHashMap<>(Map.of("pos", new ArrayList<>(List.of(0, 0, 0)), "state", 0)),
                new LinkedHashMap<>(Map.of("pos", new ArrayList<>(List.of(0, 1, 0)), "state", 1)))));
        root.put("entities", new ArrayList<>());
        Blueprint bp = Blueprints.read(Nbt.writeCompressed(root), "village_taiga_medium_house_1.nbt");
        assertEquals("minecraft:spruce_log", bp.at(0, 1, 0).name());
        assertEquals("y", bp.at(0, 1, 0).properties().get("axis"));
        assertEquals("minecraft:dirt", bp.at(0, 0, 0).name());
    }
}
