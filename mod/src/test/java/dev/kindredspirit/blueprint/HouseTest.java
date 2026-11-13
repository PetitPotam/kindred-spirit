package dev.kindredspirit.blueprint;

import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class HouseTest {

    static long count(Blueprint b, String path) {
        long n = 0;
        for (int y = 0; y < b.height(); y++)
            for (int z = 0; z < b.length(); z++)
                for (int x = 0; x < b.width(); x++) {
                    BlockSpec s = b.at(x, y, z);
                    if (s != null && s.path().equals(path)) n++;
                }
        return n;
    }

    @Test
    void aCottageForThree() {
        Blueprint b = House.cottage(3, "oak");
        assertEquals("cozy cottage for 3", b.name());
        assertEquals(0, b.frontTurns(), "the door is on the front (south) side");
        assertEquals(3, b.materials().entrySet().stream().filter(e -> e.getKey().endsWith("_bed")).mapToInt(Map.Entry::getValue).sum(),
                "a bed each");
        assertEquals(1, b.materials().get("minecraft:oak_door"));
        assertEquals(5, b.materials().get("minecraft:glass_pane"), "both sides, the back, either side of the door");
        assertTrue(b.materials().get("minecraft:dark_oak_stairs") > 40, "a stair roof (dark oak over oak)");
        assertEquals(1, b.materials().get("minecraft:chest"));
        assertEquals(1, b.materials().get("minecraft:crafting_table"));
        assertEquals(1, b.materials().get("minecraft:furnace"));
        assertEquals(3, b.materials().get("minecraft:torch"));
        assertEquals(1, count(b, "dark_oak_slab") / b.length(), "a slab ridge the whole length");
        assertTrue(b.width() % 2 == 1, "odd, so the door is in the middle");
        BlockSpec doorTop = b.at(b.width() / 2, 2, b.length() - 2);
        assertEquals("upper", doorTop.get("half"));
    }

    @Test
    void biggerForMorePeopleAndOtherWoods() {
        Blueprint one = House.cottage(1, "spruce"), six = House.cottage(6, "birch planks");
        assertTrue(six.width() > one.width());
        assertEquals(6, six.materials().entrySet().stream().filter(e -> e.getKey().endsWith("_bed")).mapToInt(Map.Entry::getValue).sum());
        assertTrue(one.materials().containsKey("minecraft:spruce_stairs"), "spruce roof over spruce");
        assertTrue(six.materials().containsKey("minecraft:birch_planks"));
        assertTrue(House.cottage(2, "unobtainium").materials().containsKey("minecraft:oak_planks"), "unknown wood: oak");
        assertTrue(House.names("a cozy cottage for three"));
        assertTrue(House.names("our house"));
        assertFalse(House.names("a castle"));
    }

    @Test
    void placedTheDoorFacesThePlayerAndThePorchIsWhereTheyLook() {
        Blueprint b = House.cottage(3, "oak");
        int[][] facings = {{0, -1}, {1, 0}, {0, 1}, {-1, 0}};
        for (int[] f : facings) {
            Placement p = Placement.inFront(b, 100, 64, 100, f[0], f[1], Placement.Anchor.FRONT_CENTER);
            Placement.Step door = p.steps(false).stream()
                    .filter(s -> s.state().path().equals("oak_door") && "lower".equals(s.state().get("half"))).findFirst().orElseThrow();
            // the door is one step behind the spot they look at (the porch), in the direction they face
            assertEquals(100 + f[0], door.x());
            assertEquals(100 + f[1], door.z());
            assertEquals(65, door.y());
        }
    }

    @Test
    void asCommandsDoorsAndBedsComeWholeAndRunsBecomeFills() {
        Placement p = Placement.inFront(House.cottage(3, "oak"), 0, 64, 0, 0, -1, Placement.Anchor.FRONT_CENTER);
        List<CommandPlan.Command> cmds = CommandPlan.of(p, true);
        int blocks = cmds.stream().mapToInt(CommandPlan.Command::blocks).sum();
        assertEquals(p.steps(true).size(), blocks, "every step is in some command");
        assertTrue(cmds.size() < blocks / 2, cmds.size() + " commands for " + blocks + " blocks");
        assertTrue(cmds.stream().allMatch(c -> c.text().startsWith("fill ") || c.text().startsWith("setblock ")));
        for (int i = 0; i < cmds.size(); i++) {
            String t = cmds.get(i).text();
            if (t.contains("half=lower")) assertTrue(cmds.get(i + 1).text().contains("half=upper"), "door top right after: " + t);
            if (t.contains("part=foot")) assertTrue(cmds.get(i + 1).text().contains("part=head"), "bed head right after: " + t);
        }
        // clearing first (top down), then the frame from the floor up
        int firstFrame = -1;
        for (int i = 0; i < cmds.size(); i++) if (!cmds.get(i).text().endsWith("minecraft:air")) { firstFrame = i; break; }
        assertTrue(firstFrame > 0);
        assertTrue(cmds.get(firstFrame).text().contains("cobblestone"), "the floor comes first: " + cmds.get(firstFrame).text());
        // what the commands build is the blueprint
        Map<String, String> world = new HashMap<>();
        for (CommandPlan.Command c : cmds) {
            String[] w = c.text().split(" ");
            if (w[0].equals("setblock")) world.put(w[1] + "," + w[2] + "," + w[3], w[4]);
            else for (int x = Integer.parseInt(w[1]); x <= Integer.parseInt(w[4]); x++)
                for (int z = Integer.parseInt(w[3]); z <= Integer.parseInt(w[6]); z++) world.put(x + "," + w[2] + "," + z, w[7]);
        }
        Verify.Result r = Verify.check(p, (x, y, z) -> world.getOrDefault(x + "," + y + "," + z, "minecraft:air"), true, true);
        assertEquals(1.0, r.score(), 1e-9, "todo: " + r.todo());
    }
}
