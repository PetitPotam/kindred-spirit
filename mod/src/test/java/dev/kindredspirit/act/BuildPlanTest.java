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
}
