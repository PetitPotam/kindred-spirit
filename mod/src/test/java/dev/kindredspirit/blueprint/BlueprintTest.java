package dev.kindredspirit.blueprint;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;

import static org.junit.jupiter.api.Assertions.*;

/**
 * The readers against sample files written by an independent encoder (src/test/resources/blueprint/
 * make_samples.py): the same little cottage as a structure file, Sponge v2 and v3, and Litematica.
 */
class BlueprintTest {

    static Blueprint sample(String file) throws IOException {
        try (InputStream in = BlueprintTest.class.getResourceAsStream("/blueprint/" + file)) {
            assertNotNull(in, "missing sample " + file);
            return Blueprints.read(in.readAllBytes(), file);
        }
    }

    static final Map<String, Integer> COTTAGE_MATERIALS = Map.of(
            "minecraft:oak_planks", 29, "minecraft:oak_slab", 26, "minecraft:cobblestone", 25,
            "minecraft:oak_door", 1, "minecraft:glass", 1, "minecraft:torch", 1, "minecraft:chest", 1);

    /** What every format must agree on. */
    static void assertCottage(Blueprint bp) {
        assertEquals(5, bp.width());
        assertEquals(5, bp.length());
        assertEquals(3955, bp.dataVersion());
        assertEquals("minecraft:cobblestone", bp.at(0, 0, 0).name());
        assertEquals("minecraft:oak_planks", bp.at(0, 1, 0).name());
        assertTrue(bp.at(2, 1, 2).isAir(), "inside is air: it clears");
        BlockSpec door = bp.at(2, 1, 4);
        assertEquals("minecraft:oak_door", door.name());
        assertEquals("lower", door.get("half"));
        assertEquals("north", door.get("facing"));
        assertEquals("upper", bp.at(2, 2, 4).get("half"));
        assertEquals(BlockSpec.parse("minecraft:wall_torch[facing=south]"), bp.at(2, 2, 1));
        assertEquals("double", bp.at(2, 3, 2).get("type"));
        assertEquals("minecraft:chest", bp.at(1, 1, 1).name());

        Map<String, Object> chest = bp.blockEntityAt(1, 1, 1);
        assertNotNull(chest, "the chest keeps its contents");
        assertEquals("minecraft:chest", chest.get("id"));
        List<?> items = (List<?>) chest.get("Items");
        assertEquals("minecraft:bread", ((Map<?, ?>) items.get(0)).get("id"));
        assertEquals(1, bp.blockEntityCount());

        assertEquals(1, bp.entities().size());
        Blueprint.Entity stand = bp.entities().get(0);
        assertEquals("minecraft:armor_stand", stand.id());
        assertEquals(1.5, stand.x(), 1e-9);
        assertEquals(1.0, stand.y(), 1e-9);
        assertEquals(3.5, stand.z(), 1e-9);
    }

    @Test
    void readsAVanillaStructureFile() throws IOException {
        Blueprint bp = sample("cottage.nbt");
        assertEquals(Blueprint.Format.STRUCTURE, bp.format());
        assertEquals("cottage", bp.name());
        assertEquals(4, bp.height());
        assertCottage(bp);
        assertNull(bp.at(3, 1, 3), "a cell the file doesn't list is left alone (structure void)");
        assertEquals(COTTAGE_MATERIALS, bp.materials());
    }

    @Test
    void readsSpongeVersion2And3() throws IOException {
        for (String f : new String[]{"cottage_v2.schem", "cottage_v3.schem"}) {
            Blueprint bp = sample(f);
            assertEquals(Blueprint.Format.SPONGE, bp.format(), f);
            assertEquals("Cozy cottage", bp.name(), f);
            assertEquals("Pip's tests", bp.author(), f);
            assertEquals(4, bp.height(), f);
            assertCottage(bp);
            assertNull(bp.at(3, 1, 3), f + ": the structure void in the palette means leave it");
            assertEquals(COTTAGE_MATERIALS, bp.materials(), f);
            assertFalse(bp.palette().stream().anyMatch(s -> s.path().startsWith("unused")),
                    "states the file lists but never uses aren't kept");
        }
    }

    @Test
    void readsLitematicaWithANegativeRegionAndTwoRegions() throws IOException {
        Blueprint bp = sample("cottage.litematic");
        assertEquals(Blueprint.Format.LITEMATIC, bp.format());
        assertEquals(6, bp.height(), "the chimney region makes it taller");
        assertCottage(bp);
        assertTrue(bp.at(3, 1, 3).isAir(), "Litematica has no structure void: air");
        assertEquals("minecraft:bricks", bp.at(4, 4, 0).name());
        assertEquals("minecraft:bricks", bp.at(4, 5, 0).name());
        assertNull(bp.at(0, 4, 0), "outside every region: left alone");
        Map<String, Integer> m = new LinkedHashMap<>(COTTAGE_MATERIALS);
        m.put("minecraft:bricks", 2);
        assertEquals(m, bp.materials());
    }

    @Test
    void materialsComeMostFirst() throws IOException {
        List<String> order = new ArrayList<>(sample("cottage.nbt").materials().keySet());
        assertEquals(List.of("minecraft:oak_planks", "minecraft:oak_slab", "minecraft:cobblestone"), order.subList(0, 3));
    }

    // --- turning -----------------------------------------------------------------------------------

    @Test
    void statesTurnWithTheBuilding() {
        assertEquals("east", BlockSpec.parse("oak_stairs[facing=north,half=bottom]").rotated(1).get("facing"));
        assertEquals("west", BlockSpec.parse("oak_stairs[facing=north]").rotated(-1).get("facing"));
        assertEquals("up", BlockSpec.parse("piston[facing=up]").rotated(1).get("facing"));
        assertEquals("z", BlockSpec.parse("oak_log[axis=x]").rotated(1).get("axis"));
        assertEquals("y", BlockSpec.parse("oak_log[axis=y]").rotated(1).get("axis"));
        assertEquals("x", BlockSpec.parse("oak_log[axis=x]").rotated(2).get("axis"));
        assertEquals("2", BlockSpec.parse("oak_sign[rotation=14]").rotated(1).get("rotation"));
        BlockSpec fence = BlockSpec.parse("oak_fence[north=true,east=false,south=false,west=true]").rotated(1);
        assertEquals("true", fence.get("east"));
        assertEquals("true", fence.get("north"));
        assertEquals("false", fence.get("south"));
        assertEquals("false", fence.get("west"));
        assertEquals("east_west", BlockSpec.parse("rail[shape=north_south]").rotated(1).get("shape"));
        assertEquals("south_west", BlockSpec.parse("rail[shape=south_east]").rotated(1).get("shape"));
        assertEquals("north_west", BlockSpec.parse("rail[shape=south_west]").rotated(1).get("shape"));
        assertEquals("ascending_south", BlockSpec.parse("rail[shape=ascending_east]").rotated(1).get("shape"));
        assertEquals("east_up", BlockSpec.parse("jigsaw[orientation=north_up]").rotated(1).get("orientation"));
        assertEquals("inner_left", BlockSpec.parse("oak_stairs[facing=north,shape=inner_left]").rotated(1).get("shape"),
                "stair shapes are relative to the stair: unchanged by turning");
        BlockSpec s = BlockSpec.parse("minecraft:oak_stairs[facing=north,half=top,shape=straight,waterlogged=false]");
        assertEquals(s, s.rotated(4));
    }

    @Test
    void blockStatesReadAndWriteLikeCommands() {
        BlockSpec s = BlockSpec.parse(" oak_stairs[half=bottom, facing=east] ");
        assertEquals("minecraft:oak_stairs[facing=east,half=bottom]", s.toString());
        assertEquals("minecraft:stone", BlockSpec.parse("STONE").toString());
        assertEquals(s, BlockSpec.parse(s.toString()));
        assertThrows(IllegalArgumentException.class, () -> BlockSpec.parse("oak_stairs[facing]"));
    }

    @Test
    void theWholeBlueprintTurns() throws IOException {
        Blueprint bp = sample("cottage.nbt");
        Blueprint once = bp.rotated(1);
        assertEquals(bp.length(), once.width());
        assertEquals(bp.width(), once.length());
        // cell (x, z) goes to (length-1-z, x): the door (2, 1, 4) to (0, 1, 2), now on the west side
        assertEquals("minecraft:oak_door", once.at(0, 1, 2).name());
        assertEquals("east", once.at(0, 1, 2).get("facing"));
        assertNotNull(once.blockEntityAt(3, 1, 1), "the chest's contents move with it");
        assertEquals(bp.materials(), once.materials());
        Blueprint back = once.rotated(3);
        for (int y = 0; y < bp.height(); y++)
            for (int z = 0; z < bp.length(); z++)
                for (int x = 0; x < bp.width(); x++)
                    assertEquals(bp.at(x, y, z), back.at(x, y, z), "at " + x + " " + y + " " + z);
        assertEquals(1.5, back.entities().get(0).x(), 1e-9);
        assertEquals(3.5, back.entities().get(0).z(), 1e-9);
    }

    @Test
    void theFrontIsWhereTheDoorIs() throws IOException {
        Blueprint bp = sample("cottage.nbt");
        assertEquals(0, bp.frontTurns(), "the door is on the south side already");
        for (int k = 1; k < 4; k++) {
            Blueprint turned = bp.rotated(k);
            assertEquals(Math.floorMod(-k, 4), turned.frontTurns(), "turned " + k);
        }
        Blueprint noDoor = Blueprint.builder(3, 1, 3).set(1, 0, 1, BlockSpec.of("stone")).build();
        assertEquals(0, noDoor.frontTurns());
    }

    // --- placing -----------------------------------------------------------------------------------

    @Test
    void placedInFrontOfThePlayerWithTheDoorFacingThem() throws IOException {
        Blueprint bp = sample("cottage.nbt").rotated(1); // as if saved with the door on the west side
        int ox = 10, oy = 64, oz = -20;
        int[][] facings = {{0, -1}, {1, 0}, {0, 1}, {-1, 0}};
        String[] doorFacing = {"north", "east", "south", "west"};
        for (int i = 0; i < 4; i++) {
            int fx = facings[i][0], fz = facings[i][1];
            Placement p = Placement.inFront(bp, ox, oy, oz, fx, fz, Placement.Anchor.FRONT_CENTER);
            List<Placement.Step> steps = p.steps(false);
            Placement.Step door = steps.stream()
                    .filter(s -> s.state().path().equals("oak_door") && "lower".equals(s.state().get("half")))
                    .findFirst().orElseThrow();
            assertEquals(List.of(ox, oy + 1, oz), List.of(door.x(), door.y(), door.z()),
                    "the door is where the player looks, facing " + doorFacing[i]);
            assertEquals(doorFacing[i], door.state().get("facing"), "the door turns with the house");
            for (Placement.Step s : steps) {
                int ahead = (s.x() - ox) * fx + (s.z() - oz) * fz;
                assertTrue(ahead >= 0, "every block is in front of the player: " + s);
            }
            int[] box = p.box();
            assertEquals(5, box[3] - box[0] + 1);
            assertEquals(5, box[5] - box[2] + 1);
            assertEquals(oy, box[1]);
        }
    }

    @Test
    void frontLeftStartsWhereYouLookAndGoesRight() throws IOException {
        Blueprint bp = sample("cottage.nbt");
        // facing north: right is east (+x), forward is -z
        int[] box = Placement.inFront(bp, 0, 70, 0, 0, -1, Placement.Anchor.FRONT_LEFT).box();
        assertArrayEquals(new int[]{0, 70, -4, 4, 73, 0}, box);
        // facing south: right is west (-x), forward is +z
        box = Placement.inFront(bp, 0, 70, 0, 0, 1, Placement.Anchor.FRONT_LEFT).box();
        assertArrayEquals(new int[]{-4, 70, 0, 0, 73, 4}, box);
    }

    @Test
    void sheBuildsTheFrameBottomUpThenTheDetails() throws IOException {
        Blueprint bp = sample("cottage.nbt");
        List<Placement.Step> steps = Placement.inFront(bp, 0, 64, 0, 0, -1, Placement.Anchor.FRONT_CENTER).steps(true);
        int firstFrame = -1, firstDetail = -1, lastClearY = Integer.MAX_VALUE, lastFrameY = Integer.MIN_VALUE;
        int clears = 0;
        for (int i = 0; i < steps.size(); i++) {
            Placement.Step s = steps.get(i);
            switch (s.kind()) {
                case CLEAR -> {
                    assertEquals(-1, firstFrame, "clearing comes first");
                    assertTrue(s.y() <= lastClearY, "clearing goes top down");
                    lastClearY = s.y();
                    clears++;
                }
                case BLOCK -> {
                    if (firstFrame < 0) firstFrame = i;
                    assertEquals(-1, firstDetail, "the frame before the details");
                    assertTrue(s.y() >= lastFrameY, "the frame rises layer by layer");
                    lastFrameY = s.y();
                }
                case DETAIL, SECOND_HALF -> { if (firstDetail < 0) firstDetail = i; }
            }
        }
        assertEquals(7 + 8, clears, "the air inside (the void cell isn't cleared)");
        assertEquals(1, steps.stream().filter(s -> s.kind() == Placement.Kind.SECOND_HALF).count(), "the door's top");
        assertTrue(steps.stream().anyMatch(s -> s.kind() == Placement.Kind.DETAIL && s.state().path().equals("wall_torch")));
        assertTrue(steps.stream().anyMatch(s -> s.kind() == Placement.Kind.BLOCK && s.state().path().equals("chest")));
        assertNotNull(steps.stream().filter(s -> s.state().path().equals("chest")).findFirst().orElseThrow().blockEntity());
        assertEquals(bp.solidBlocks(), steps.size() - clears);
        assertEquals(bp.solidBlocks(), steps(bp, false).size(), "without clearing: only the blocks");
    }

    private static List<Placement.Step> steps(Blueprint bp, boolean clear) {
        return Placement.inFront(bp, 0, 64, 0, 0, -1, Placement.Anchor.FRONT_CENTER).steps(clear);
    }

    @Test
    void neighbouringRowsGoBackAndForth() {
        Blueprint.Builder b = Blueprint.builder(3, 1, 2);
        for (int z = 0; z < 2; z++) for (int x = 0; x < 3; x++) b.set(x, 0, z, BlockSpec.of("stone"));
        List<Placement.Step> steps = Placement.at(b.build(), 0, 0, 0, 0).steps(false);
        List<Integer> xs = steps.stream().map(Placement.Step::x).toList();
        assertEquals(List.of(0, 1, 2, 2, 1, 0), xs);
    }

    // --- saving what she builds ----------------------------------------------------------------------

    @Test
    void whatSheSavesReadsBackTheSame(@TempDir Path dir) throws IOException {
        Blueprint bp = sample("cottage.litematic");
        Path file = dir.resolve("our_house.nbt");
        Blueprints.writeStructure(bp, file, Blueprints.DATA_VERSION_1_21_1);
        Blueprint again = Blueprints.read(file);
        assertEquals(Blueprint.Format.STRUCTURE, again.format());
        assertEquals("our_house", again.name());
        assertEquals(bp.width(), again.width());
        assertEquals(bp.height(), again.height());
        for (int y = 0; y < bp.height(); y++)
            for (int z = 0; z < bp.length(); z++)
                for (int x = 0; x < bp.width(); x++)
                    assertEquals(bp.at(x, y, z), again.at(x, y, z), "at " + x + " " + y + " " + z);
        assertEquals(bp.blockEntityAt(1, 1, 1), again.blockEntityAt(1, 1, 1));
        assertEquals(bp.entities().get(0).x(), again.entities().get(0).x(), 1e-9);
        assertEquals(bp.materials(), again.materials());
    }

    @Test
    void theGameReadsWhatWeWrite(@TempDir Path dir) throws IOException {
        // the game's own NBT code (no game start needed) agrees with ours, both ways
        Path ours = dir.resolve("ours.nbt");
        Blueprints.writeStructure(sample("cottage.nbt"), ours, Blueprints.DATA_VERSION_1_21_1);
        net.minecraft.nbt.CompoundTag tag = net.minecraft.nbt.NbtIo.readCompressed(ours, net.minecraft.nbt.NbtAccounter.unlimitedHeap());
        assertEquals(3955, tag.getInt("DataVersion"));
        assertEquals(5, tag.getList("size", 3).getInt(0));
        net.minecraft.nbt.ListTag palette = tag.getList("palette", 10);
        assertTrue(palette.stream().anyMatch(t -> ((net.minecraft.nbt.CompoundTag) t).getString("Name").equals("minecraft:oak_door")));

        Path theirs = dir.resolve("theirs.nbt");
        net.minecraft.nbt.NbtIo.writeCompressed(tag, theirs);
        Blueprint back = Blueprints.read(theirs);
        assertCottage(back);
    }

    // --- broken and unsupported files ----------------------------------------------------------------

    @Test
    void brokenFilesFailWithAReason() throws IOException {
        byte[] good;
        try (InputStream in = getClass().getResourceAsStream("/blueprint/cottage_v3.schem")) {
            good = in.readAllBytes();
        }
        byte[] cut = java.util.Arrays.copyOf(good, good.length / 2);
        assertThrows(BlueprintException.class, () -> Blueprints.read(cut, "cut.schem"));
        assertThrows(BlueprintException.class, () -> Blueprints.read("hello".getBytes(), "hello.nbt"));
        byte[] noise = new byte[256];
        new Random(7).nextBytes(noise);
        assertThrows(BlueprintException.class, () -> Blueprints.read(noise, "noise.litematic"));
    }

    @Test
    void oldSchematicsGetAnHonestAnswer() throws IOException {
        Map<String, Object> legacy = new LinkedHashMap<>();
        legacy.put("Width", (short) 1);
        legacy.put("Height", (short) 1);
        legacy.put("Length", (short) 1);
        legacy.put("Materials", "Alpha");
        legacy.put("Blocks", new byte[]{1});
        legacy.put("Data", new byte[]{0});
        BlueprintException e = assertThrows(BlueprintException.class,
                () -> Blueprints.read(Nbt.writeCompressed(legacy), "castle.schematic"));
        assertTrue(e.getMessage().contains("1.13"), e.getMessage());
    }

    @Test
    void hugeBlueprintsAreRefusedBeforeTakingMemory() throws IOException {
        Map<String, Object> s = new LinkedHashMap<>();
        s.put("Version", 2);
        s.put("Width", (short) -1); // 65535 as an unsigned short
        s.put("Height", (short) 256);
        s.put("Length", (short) -1);
        s.put("Palette", Map.of("minecraft:stone", 0));
        s.put("BlockData", new byte[]{0});
        BlueprintException e = assertThrows(BlueprintException.class,
                () -> Blueprints.read(Nbt.writeCompressed(s), "world.schem"));
        assertTrue(e.getMessage().contains("too big"), e.getMessage());
    }

    @Test
    void spongeVarintsAndLitematicaBitsRoundTrip() {
        Random r = new Random(42);
        for (int bits = 1; bits <= 20; bits++) {
            int[] values = new int[257];
            for (int i = 0; i < values.length; i++) values[i] = r.nextInt(1 << bits);
            long[] packed = LitematicFormat.pack(values, bits);
            long mask = (1L << bits) - 1;
            for (int i = 0; i < values.length; i++) {
                assertEquals(values[i], LitematicFormat.entry(packed, bits, mask, i), "bits " + bits + " entry " + i);
            }
        }
        byte[] v = SpongeFormat.varints(new int[]{0, 127, 128, 300, 1 << 20});
        assertArrayEquals(new byte[]{0, 127, (byte) 0x80, 1, (byte) 0xAC, 2, (byte) 0x80, (byte) 0x80, 0x40}, v);
    }

    @Test
    void materialRules() {
        assertEquals(Map.of("minecraft:oak_slab", 2), Materials.of(BlockSpec.parse("oak_slab[type=double]")));
        assertEquals(Map.of(), Materials.of(BlockSpec.parse("oak_door[half=upper]")));
        assertEquals(Map.of(), Materials.of(BlockSpec.parse("red_bed[part=head]")));
        assertEquals(Map.of("minecraft:red_bed", 1), Materials.of(BlockSpec.parse("red_bed[part=foot]")));
        assertEquals(Map.of("minecraft:oak_trapdoor", 1), Materials.of(BlockSpec.parse("oak_trapdoor[half=top]")),
                "a trapdoor's top half is a whole trapdoor");
        assertEquals(Map.of("minecraft:oak_sign", 1), Materials.of(BlockSpec.parse("oak_wall_sign[facing=east]")));
        assertEquals(Map.of("minecraft:flower_pot", 1, "minecraft:poppy", 1), Materials.of(BlockSpec.of("potted_poppy")));
        assertEquals(Map.of("minecraft:water_bucket", 1), Materials.of(BlockSpec.parse("water[level=0]")));
        assertEquals(Map.of(), Materials.of(BlockSpec.parse("water[level=3]")));
        assertEquals(Map.of("minecraft:candle", 3), Materials.of(BlockSpec.parse("candle[candles=3,lit=false]")));
        assertEquals(Map.of("minecraft:wheat_seeds", 1), Materials.of(BlockSpec.parse("wheat[age=7]")));
        assertEquals(Map.of(), Materials.of(BlockSpec.of("fire")));
    }
}
