package dev.kindredspirit.blueprint;

import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class CatalogueTest {

    /** A small box of one block, with a few extra blocks inside. */
    static Blueprint box(int w, int h, int l, String block, String... extras) {
        Blueprint.Builder b = Blueprint.builder(w, h, l);
        for (int x = 0; x < w; x++) for (int z = 0; z < l; z++) b.set(x, 0, z, BlockSpec.of(block));
        int i = 0;
        for (String e : extras) b.set(i++ % w, 1, i % l, BlockSpec.parse(e));
        return b.build();
    }

    static final String SOURCES = """
            Where these blueprints come from

            - village_*, igloo, ruined_*, shipwreck_*, pillager_watchtower: Minecraft 1.21.1's own structure templates,
              extracted from the game files on this computer for personal use (not for sharing).
            - circle_*: Greaby/minecraft-circles-schematics, CC0-1.0 (public domain),
              https://github.com/Greaby/minecraft-circles-schematics
            """;

    @Test
    void villageBuildingsByTheirTrade() {
        JsonObject e = Catalogue.describe("village_plains_armorer_house_1.nbt",
                box(9, 8, 8, "cobblestone", "blast_furnace[facing=north,lit=false]", "red_bed[part=foot,facing=north]"),
                Catalogue.sources(SOURCES));
        assertEquals("workshop", e.get("category").getAsString());
        assertEquals("plains", e.get("style").getAsString());
        assertEquals("a plains smithy (the armorer's), with a blast furnace (a bed)", e.get("what").getAsString());
        assertTrue(e.get("source").getAsString().startsWith("Minecraft 1.21.1's own structure templates, extracted"),
                "a source line, continued on the next line: " + e.get("source"));
        assertEquals("Pip, build a plains smithy (the armorer's) (village_plains_armorer_house_1)", e.get("say").getAsString());
        assertTrue(e.get("summary").getAsString().endsWith(": 9 x 8, 8 high, " + e.get("blocks").getAsInt() + " blocks"));
        List<String> tags = new java.util.ArrayList<>();
        e.getAsJsonArray("tags").forEach(t -> tags.add(t.getAsString()));
        assertTrue(tags.containsAll(List.of("village", "plains", "smithy", "armorer", "workshop", "small", "stone", "blast furnace")), tags.toString());

        JsonObject noFurnace = Catalogue.describe("village_desert_armorer_1.nbt", box(7, 3, 7, "smooth_sandstone"), null);
        assertEquals("a desert smithy (the armorer's)", noFurnace.get("what").getAsString(), "only what's really there");
        assertFalse(noFurnace.has("source"));
    }

    @Test
    void housesWellsAndTheRest() {
        assertEquals("a small desert house (beds for 2)", Catalogue.describe("village_desert_small_house_3.nbt",
                box(6, 3, 5, "sandstone", "red_bed[part=foot]", "blue_bed[part=foot]"), null).get("what").getAsString());
        assertEquals("a big taiga crop field, with a composter", Catalogue.describe("village_taiga_large_farm_1.nbt",
                box(10, 3, 10, "farmland", "composter"), null).get("what").getAsString());
        assertEquals("well", Catalogue.describe("village_plains_meeting_point_2.nbt", box(9, 3, 9, "cobblestone"), null)
                .get("category").getAsString());
        assertEquals("a plains village well with a bell", Catalogue.describe("village_plains_meeting_point_2.nbt",
                box(9, 3, 9, "cobblestone", "water[level=0]", "bell"), null).get("what").getAsString());
        JsonObject circle = Catalogue.describe("circle_12x12.litematic", box(12, 1, 12, "stone"), Catalogue.sources(SOURCES));
        assertEquals("shape", circle.get("category").getAsString());
        assertTrue(circle.get("source").getAsString().contains("CC0-1.0"));
        assertEquals("portal", Catalogue.describe("ruined_giant_portal_2.nbt", box(11, 5, 16, "obsidian"), null).get("category").getAsString());
        assertEquals("ship", Catalogue.describe("shipwreck_sideways_full.nbt", box(9, 5, 28, "oak_planks"), null).get("category").getAsString());
        JsonObject mine = Catalogue.describe("Our_Cherry-Castle 2.schem", box(30, 12, 30, "cherry_planks"), null);
        assertEquals("castle", mine.get("category").getAsString(), "a player's own file, by its words");
        assertEquals("a our cherry castle", mine.get("what").getAsString().replace("an our", "a our"));
        assertEquals("big", mine.get("size").getAsString());
    }

    @Test
    void sizeClasses() {
        assertEquals("tiny", Catalogue.sizeClass(box(3, 2, 3, "stone")));
        assertEquals("small", Catalogue.sizeClass(box(9, 3, 8, "stone")));
        assertEquals("medium", Catalogue.sizeClass(box(16, 3, 12, "stone")));
        assertEquals("big", Catalogue.sizeClass(box(28, 3, 12, "stone")));
        assertEquals("medium", Catalogue.sizeClass(box(20, 2, 20, "air", "stone", "stone")), "a wide but thin outline isn't big");
    }

    @Test
    void picturesArePngsTheRightSize() throws IOException {
        Blueprint b = House.cottage(2, "oak");
        BufferedImage top = ImageIO.read(new ByteArrayInputStream(Picture.top(b, Picture::guessColor)));
        BufferedImage front = ImageIO.read(new ByteArrayInputStream(Picture.front(b, Picture::guessColor)));
        int s = Picture.scale(Math.max(b.width(), b.length()));
        assertEquals(b.width() * s, top.getWidth());
        assertEquals(b.length() * s, top.getHeight());
        assertEquals(b.height() * Picture.scale(Math.max(b.width(), b.height())), front.getHeight());
        assertEquals(255, (top.getRGB(top.getWidth() / 2, top.getHeight() / 2) >>> 24), "the roof is drawn");
        // the porch overhang's empty corners are see-through from the front... at least one pixel is transparent
        boolean clear = false;
        for (int x = 0; x < front.getWidth() && !clear; x++) clear = (front.getRGB(x, 0) >>> 24) == 0;
        assertTrue(clear, "the sky around the roof's peak is transparent");
    }

    @Test
    void theIndexFollowsTheFolder(@TempDir Path dir) throws IOException {
        Files.writeString(dir.resolve("SOURCES.txt"), SOURCES);
        Blueprints.writeStructure(box(9, 8, 8, "cobblestone", "blast_furnace"), dir.resolve("village_plains_armorer_house_1.nbt"), 3955);
        Blueprints.writeStructure(box(12, 1, 12, "stone"), dir.resolve("circle_12x12.nbt"), 3955);
        Files.writeString(dir.resolve("broken.schem"), "not a schematic");
        assertTrue(CatalogueIndex.stale(dir));
        JsonObject idx = CatalogueIndex.refresh(dir, Picture::guessColor);
        assertEquals(2, idx.getAsJsonArray("entries").size());
        assertEquals(1, idx.getAsJsonArray("errors").size(), "an unreadable file is listed, not hidden");
        assertEquals(1, idx.getAsJsonObject("categories").get("workshop").getAsInt());
        JsonObject first = idx.getAsJsonArray("entries").get(0).getAsJsonObject();
        assertTrue(Files.exists(dir.resolve(first.get("top").getAsString())));
        assertTrue(Files.exists(dir.resolve(first.get("front").getAsString())));
        // (mtime precision: make the index clearly newer than the files)
        Files.setLastModifiedTime(dir.resolve(CatalogueIndex.INDEX), FileTime.fromMillis(System.currentTimeMillis() + 5000));
        Files.delete(dir.resolve("broken.schem"));
        assertTrue(CatalogueIndex.stale(dir), "a file went away");
        idx = CatalogueIndex.refresh(dir, Picture::guessColor);
        Files.setLastModifiedTime(dir.resolve(CatalogueIndex.INDEX), FileTime.fromMillis(System.currentTimeMillis() + 5000));
        assertFalse(CatalogueIndex.stale(dir));
        // removed to the trash (as the dashboard does): its entry and pictures go
        Files.createDirectories(dir.resolve(CatalogueIndex.TRASH));
        Files.move(dir.resolve("circle_12x12.nbt"), dir.resolve(CatalogueIndex.TRASH).resolve("circle_12x12.nbt"));
        assertTrue(CatalogueIndex.stale(dir));
        idx = CatalogueIndex.refresh(dir, Picture::guessColor);
        assertEquals(1, idx.getAsJsonArray("entries").size());
        assertFalse(Files.exists(dir.resolve(".catalogue/circle_12x12.top.png")));
        assertTrue(idx.get("sources").getAsString().contains("Greaby"));
    }

    @Test
    void jigsawsBecomeWhatTheGamePutsThere(@TempDir Path dir) throws IOException {
        // a village piece: a jigsaw that turns into a stair, one that means "leave it", and a data marker
        Map<String, Object> root = StructureFormat.write(box(3, 2, 3, "cobblestone"), 3955);
        @SuppressWarnings("unchecked") List<Object> palette = (List<Object>) root.get("palette");
        @SuppressWarnings("unchecked") List<Object> blocks = (List<Object>) root.get("blocks");
        int jig = palette.size();
        palette.add(Map.of("Name", "minecraft:jigsaw", "Properties", Map.of("orientation", "north_up")));
        palette.add(Map.of("Name", "minecraft:structure_block", "Properties", Map.of("mode", "data")));
        blocks.add(new LinkedHashMap<>(Map.of("state", jig, "pos", List.of(0, 1, 0),
                "nbt", Map.of("final_state", "minecraft:oak_stairs[facing=east]", "id", "minecraft:jigsaw"))));
        blocks.add(new LinkedHashMap<>(Map.of("state", jig, "pos", List.of(1, 1, 0),
                "nbt", Map.of("final_state", "minecraft:structure_void", "id", "minecraft:jigsaw"))));
        blocks.add(new LinkedHashMap<>(Map.of("state", jig + 1, "pos", List.of(2, 1, 0),
                "nbt", Map.of("metadata", "Chest", "id", "minecraft:structure_block"))));
        Blueprint b = Blueprints.read(Nbt.writeCompressed(root), "village_piece.nbt");
        assertEquals(BlockSpec.parse("oak_stairs[facing=east]"), b.at(0, 1, 0));
        assertNull(b.at(1, 1, 0), "structure void: left as it is");
        assertTrue(b.at(2, 1, 0).isAir(), "a data marker becomes air");
        assertNull(b.blockEntityAt(0, 1, 0), "no jigsaw data left behind");
        assertFalse(b.materials().containsKey("minecraft:jigsaw"));
    }
}
