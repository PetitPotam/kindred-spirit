package dev.kindredspirit.job;

import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class DigTest {

    /** Stone everywhere, with what we put. */
    static final class FakeWorld implements Dig.World {
        final Map<String, String> blocks = new HashMap<>();

        void put(int x, int y, int z, String id) {
            blocks.put(x + "," + y + "," + z, id);
        }

        @Override
        public String block(int x, int y, int z) {
            return blocks.getOrDefault(x + "," + y + "," + z, "minecraft:stone");
        }
    }

    @Test
    void wholeVeinsNearestFirst() {
        FakeWorld w = new FakeWorld();
        // a near vein of 3 iron (one diagonal), a far vein of 2
        w.put(2, 0, 0, "minecraft:iron_ore");
        w.put(3, 0, 0, "minecraft:deepslate_iron_ore");
        w.put(4, 1, 0, "minecraft:iron_ore");
        w.put(0, 0, 7, "minecraft:iron_ore");
        w.put(0, 1, 7, "minecraft:iron_ore");
        List<int[]> got = Dig.find(w, 0, 0, 0, 8, Dig.kind("iron"), 10);
        assertEquals(5, got.size());
        assertArrayEquals(new int[]{2, 0, 0}, got.get(0));
        assertTrue(List.of(got.get(0)[0], got.get(1)[0], got.get(2)[0]).containsAll(List.of(2, 3, 4)),
                "the near vein is taken whole before the far one");
        assertEquals(7, got.get(3)[2]);
    }

    @Test
    void neverPastTheRadiusAndNeverMoreThanAsked() {
        FakeWorld w = new FakeWorld();
        for (int x = 1; x <= 12; x++) w.put(x, 0, 0, "minecraft:coal_ore");
        List<int[]> got = Dig.find(w, 0, 0, 0, 5, Dig.kind("coal"), 100);
        assertEquals(5, got.size(), "the vein goes on, but she only reaches 5 blocks");
        assertEquals(3, Dig.find(w, 0, 0, 0, 5, Dig.kind("coal"), 3).size());
    }

    @Test
    void namesForWhatToMine() {
        assertTrue(Dig.kind("diamonds").test("minecraft:deepslate_diamond_ore"));
        assertTrue(Dig.kind("iron ore").test("minecraft:iron_ore"));
        assertTrue(Dig.kind("gold").test("minecraft:nether_gold_ore"));
        assertFalse(Dig.kind("iron").test("minecraft:iron_block"));
        assertTrue(Dig.kind("logs").test("minecraft:birch_log"));
        assertTrue(Dig.kind("ancient debris").test("minecraft:ancient_debris"));
        assertTrue(Dig.kind("ores").test("minecraft:copper_ore"));
        assertTrue(Dig.kind("sand").test("minecraft:sand"));
        assertFalse(Dig.kind("sand").test("minecraft:sandstone"));
    }

    @Test
    void aVeinStopsAtItsEdges() {
        FakeWorld w = new FakeWorld();
        w.put(0, 0, 0, "minecraft:oak_log");
        w.put(0, 1, 0, "minecraft:oak_log");
        w.put(0, 2, 0, "minecraft:oak_log");
        w.put(1, 3, 0, "minecraft:oak_log"); // a branch, diagonal
        assertEquals(3, Dig.vein(w, 0, 0, 0, Dig.kind("log"), 100, false).size());
        assertEquals(4, Dig.vein(w, 0, 0, 0, Dig.kind("log"), 100, true).size());
        assertTrue(Dig.vein(w, 5, 5, 5, Dig.kind("log"), 100, true).isEmpty());
    }
}
