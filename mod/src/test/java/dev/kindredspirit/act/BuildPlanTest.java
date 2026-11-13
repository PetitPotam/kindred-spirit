package dev.kindredspirit.act;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class BuildPlanTest {
    // facing south (+z): forward (0, 1), right is west (-1, 0)
    static final int FX = 0, FZ = 1;

    @Test
    void aPillarRisesFromTheSpot() {
        List<int[]> p = BuildPlan.positions(BuildPlan.Shape.PILLAR, 10, 64, 10, FX, FZ, 1, 1, 5);
        assertEquals(5, p.size());
        assertArrayEquals(new int[]{10, 64, 10}, p.get(0));
        assertArrayEquals(new int[]{10, 68, 10}, p.get(4));
    }

    @Test
    void tenOnEachCornerLayerByLayer() {
        List<int[]> p = BuildPlan.positions(BuildPlan.Shape.CORNERS, 0, 64, 0, FX, FZ, 5, 7, 10);
        assertEquals(40, p.size());
        // first layer: the four corners at the bottom, then up
        assertArrayEquals(new int[]{0, 64, 0}, p.get(0));
        assertArrayEquals(new int[]{-4, 64, 0}, p.get(1), "width goes to the right (west when facing south)");
        assertArrayEquals(new int[]{0, 64, 6}, p.get(2), "length goes forward");
        assertArrayEquals(new int[]{-4, 64, 6}, p.get(3));
        assertEquals(65, p.get(4)[1], "then the next layer");
    }

    @Test
    void outlineWalksTheEdgeOnce() {
        List<int[]> p = BuildPlan.positions(BuildPlan.Shape.OUTLINE, 0, 0, 0, 1, 0, 4, 3, 1);
        assertEquals(10, p.size(), "4x3 border: 2*4 + 2*1");
        assertEquals(p.size(), p.stream().map(a -> a[0] + "," + a[2]).distinct().count(), "no cell twice");
    }

    @Test
    void floorsAreFlatAndEverythingIsCapped() {
        assertTrue(BuildPlan.positions(BuildPlan.Shape.FLOOR, 0, 0, 0, FX, FZ, 3, 3, 9).stream().allMatch(a -> a[1] == 0));
        assertEquals(BuildPlan.MAX_BLOCKS, BuildPlan.positions(BuildPlan.Shape.FLOOR, 0, 0, 0, FX, FZ, 99, 99, 1).size());
        assertEquals(BuildPlan.MAX_HEIGHT, BuildPlan.positions(BuildPlan.Shape.PILLAR, 0, 0, 0, FX, FZ, 1, 1, 500).size());
    }

    @Test
    void shapesByManyNames() {
        assertEquals(BuildPlan.Shape.PILLAR, BuildPlan.Shape.of("tower"));
        assertEquals(BuildPlan.Shape.CORNERS, BuildPlan.Shape.of("corners"));
        assertEquals(BuildPlan.Shape.OUTLINE, BuildPlan.Shape.of("pen"));
        assertNull(BuildPlan.Shape.of("castle"));
    }

    @org.junit.jupiter.api.Test
    void aHouseHasAFloorWallsADoorwayAndARoof() {
        var steps = BuildPlan.steps(BuildPlan.Shape.HOUSE, 0, 64, 0, FX, FZ, 0, 0, 0, 2, Integer.MIN_VALUE);
        // for two: 7 x 7, walls 3 high, flat roof
        long floor = steps.stream().filter(s -> s.y() == 64).count(), roof = steps.stream().filter(s -> s.y() == 68).count();
        org.junit.jupiter.api.Assertions.assertEquals(49, floor);
        org.junit.jupiter.api.Assertions.assertEquals(49, roof);
        org.junit.jupiter.api.Assertions.assertEquals(1, steps.stream().filter(s -> s.kind() == 'D').count(), "one door");
        org.junit.jupiter.api.Assertions.assertEquals(1, steps.stream().filter(s -> s.kind() == 'X').count(), "above the door: open");
        org.junit.jupiter.api.Assertions.assertTrue(BuildPlan.steps(BuildPlan.Shape.HOUSE, 0, 64, 0, FX, FZ, 0, 0, 0, 4,
                Integer.MIN_VALUE).stream().filter(s -> s.y() == 64).count() > 49, "a bigger house for four");
    }

    @org.junit.jupiter.api.Test
    void aPortalIsTenObsidianThenFire() {
        var steps = BuildPlan.steps(BuildPlan.Shape.PORTAL, 0, 64, 0, FX, FZ, 0, 0, 0, 1, Integer.MIN_VALUE);
        org.junit.jupiter.api.Assertions.assertEquals(10, steps.stream().filter(s -> "obsidian".equals(s.block())).count());
        org.junit.jupiter.api.Assertions.assertEquals('L', steps.get(steps.size() - 1).kind(), "lit last");
    }

    @org.junit.jupiter.api.Test
    void clearingGoesFromTheTopDownAndFlatteningFillsTheGround() {
        var clear = BuildPlan.steps(BuildPlan.Shape.CLEAR, 0, 70, 0, FX, FZ, 4, 4, 5, 1, 64);
        org.junit.jupiter.api.Assertions.assertEquals(80, clear.size());
        org.junit.jupiter.api.Assertions.assertEquals(69, clear.get(0).y(), "the top layer first");
        org.junit.jupiter.api.Assertions.assertTrue(clear.stream().allMatch(s -> s.kind() == 'X' && s.y() >= 65), "above Y 64 only");
        var flat = BuildPlan.steps(BuildPlan.Shape.FLATTEN, 0, 70, 0, FX, FZ, 4, 4, 5, 1, 64);
        org.junit.jupiter.api.Assertions.assertEquals(16, flat.stream().filter(s -> s.kind() == 'F' && s.y() == 64).count());
    }

    @org.junit.jupiter.api.Test
    void unknownShapesAreNamedHonestly() {
        org.junit.jupiter.api.Assertions.assertNull(BuildPlan.Shape.of("castle"));
        org.junit.jupiter.api.Assertions.assertEquals(BuildPlan.Shape.FLATTEN, BuildPlan.Shape.of("flatten"));
        org.junit.jupiter.api.Assertions.assertEquals(BuildPlan.Shape.PLACE, BuildPlan.Shape.of("place"));
    }

    @Test
    void anEndPortalIsTwelveFramesFacingInAroundNineOpenings() {
        var steps = BuildPlan.steps(BuildPlan.Shape.END_PORTAL, 0, 64, 0, FX, FZ, 0, 0, 0, 1, Integer.MIN_VALUE);
        assertEquals(12, steps.stream().filter(s -> s.kind() == 'E').count());
        assertEquals(9, steps.stream().filter(s -> s.kind() == 'O').count());
        assertEquals(BuildPlan.Shape.END_PORTAL, BuildPlan.Shape.of("end portal".replace(' ', '_')));
        // the near frame faces forward (south), towards the middle
        var near = steps.stream().filter(s -> s.kind() == 'E' && s.z() == 0).findFirst().orElseThrow();
        assertEquals("0,1", near.block());
        assertTrue(steps.stream().filter(s -> s.kind() == 'O').allMatch(s -> s.z() >= 1 && s.z() <= 3 && s.y() == 64));
    }

    @Test
    void aFarmIsTilledAroundWaterWithCropsOnTop() {
        var steps = BuildPlan.steps(BuildPlan.Shape.FARM, 0, 64, 0, FX, FZ, 0, 0, 0, 1, Integer.MIN_VALUE);
        assertEquals(1, steps.stream().filter(s -> s.kind() == 'W').count(), "one water in a 9 x 9");
        assertEquals(80, steps.stream().filter(s -> s.kind() == 'T').count());
        assertEquals(80, steps.stream().filter(s -> s.kind() == 'C' && s.y() == 64).count());
        assertTrue(steps.stream().filter(s -> s.kind() != 'C').allMatch(s -> s.y() == 63), "the ground is the layer below");
        var big = BuildPlan.steps(BuildPlan.Shape.FARM, 0, 64, 0, FX, FZ, 12, 12, 0, 1, Integer.MIN_VALUE);
        assertEquals(4, big.stream().filter(s -> s.kind() == 'W').count(), "a shorter last stretch gets its own water");
        for (var s : big) if (s.kind() == 'T') { // every tilled block is within 4 of water
            assertTrue(big.stream().filter(w -> w.kind() == 'W')
                    .anyMatch(w -> Math.abs(w.x() - s.x()) <= 4 && Math.abs(w.z() - s.z()) <= 4), s.toString());
        }
        assertEquals(BuildPlan.Shape.FARM, BuildPlan.Shape.of("wheat_farm"));
    }

    @Test
    void theMiddleOfAFarmIsOverItsWater() {
        var farm = BuildPlan.steps(BuildPlan.Shape.FARM, 0, 64, 0, FX, FZ, 0, 0, 0, 1, Integer.MIN_VALUE);
        var water = farm.stream().filter(s -> s.kind() == 'W').findFirst().orElseThrow();
        assertArrayEquals(new int[]{water.x(), 64, water.z()}, BuildPlan.middleTop(farm), "on the water, at crop level");
        var pillar = BuildPlan.steps(BuildPlan.Shape.PILLAR, 5, 64, 5, FX, FZ, 1, 1, 4, 1, Integer.MIN_VALUE);
        assertArrayEquals(new int[]{5, 68, 5}, BuildPlan.middleTop(pillar), "on top of the pillar");
        assertNull(BuildPlan.middleTop(List.of()));
    }
}
