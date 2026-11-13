package dev.kindredspirit.act;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ShapesTest {
    private static List<int[]> flat(String form, int w, int l) {
        return Shapes.cells(form, w, l, 1, false, false, 6, 1);
    }

    @Test
    void namesAndSynonyms() {
        assertEquals("sphere", Shapes.of("ball"));
        assertEquals("cylinder", Shapes.of("Tower"));
        assertEquals("stepped_pyramid", Shapes.of("stepped pyramid"));
        assertNull(Shapes.of("castle"));
    }

    @Test
    void flatShapesHaveTheRightSizeAndSymmetry() {
        assertEquals(81, flat("square", 9, 9).size());
        assertEquals(77, flat("rectangle", 11, 7).size());
        int circle = flat("circle", 21, 21).size();
        assertTrue(Math.abs(circle - Math.PI * 10.5 * 10.5) < 40, "a circle of radius ~10.5: " + circle);
        for (String form : new String[]{"circle", "star", "heart", "hexagon", "cross", "diamond", "triangle"}) {
            List<int[]> c = flat(form, 15, 15);
            assertFalse(c.isEmpty(), form);
            for (int[] p : c) { // left-right mirror: every shape here is symmetric across your view
                assertTrue(c.stream().anyMatch(q -> q[0] == -p[0] && q[2] == p[2]), form + " not symmetric at " + p[0] + "," + p[2]);
            }
        }
        List<int[]> tri = flat("triangle", 9, 9);
        long near = tri.stream().filter(p -> p[2] == 0).count(), far = tri.stream().filter(p -> p[2] == 8).count();
        assertTrue(near > far, "the base is near you, the tip ahead");
    }

    @Test
    void hollowKeepsOnlyTheOutline() {
        List<int[]> ring = Shapes.cells("circle", 15, 15, 1, true, false, 0, 1);
        assertTrue(ring.size() < flat("circle", 15, 15).size() / 2);
        assertTrue(ring.stream().noneMatch(p -> p[0] == 0 && p[2] == 7), "the middle is open");
        assertEquals(32, Shapes.cells("square", 9, 9, 1, true, false, 0, 1).size());
    }

    @Test
    void standingUpGoesUpInsteadOfForward() {
        List<int[]> sign = Shapes.cells("heart", 9, 9, 1, false, true, 0, 1);
        assertTrue(sign.stream().allMatch(p -> p[2] == 0) && sign.stream().anyMatch(p -> p[1] == 8));
        long upper = sign.stream().filter(p -> p[1] >= 5).count(), lower = sign.stream().filter(p -> p[1] <= 3).count();
        assertTrue(upper > lower, "the lobes on top, the tip at the bottom: " + upper + " / " + lower);
        int top = sign.stream().mapToInt(p -> p[1]).max().orElseThrow();
        assertTrue(sign.stream().noneMatch(p -> p[1] == top && p[0] == 0), "the notch between the lobes, at the top");
    }

    @Test
    void solidShapesRiseFromTheGround() {
        List<int[]> sphere = Shapes.cells("sphere", 9, 9, 9, false, false, 0, 1);
        double volume = 4.0 / 3 * Math.PI * 4.5 * 4.5 * 4.5;
        assertTrue(Math.abs(sphere.size() - volume) < volume * 0.15, "a ball of radius 4.5: " + sphere.size());
        assertEquals(0, sphere.get(0)[1], "built from the bottom up");
        assertTrue(Shapes.cells("sphere", 9, 9, 9, true, false, 0, 1).size() < sphere.size() / 2, "hollow: a shell");
        List<int[]> pyramid = Shapes.cells("pyramid", 11, 11, 6, false, false, 0, 1);
        long bottom = pyramid.stream().filter(p -> p[1] == 0).count(), top = pyramid.stream().filter(p -> p[1] == 5).count();
        assertTrue(bottom > 80 && top <= 9, "wide at the bottom, a point at the top: " + bottom + " / " + top);
        List<int[]> stepped = Shapes.cells("stepped_pyramid", 11, 11, 6, false, false, 0, 1);
        assertEquals(121, stepped.stream().filter(p -> p[1] == 0).count());
        assertEquals(81, stepped.stream().filter(p -> p[1] == 1).count());
        assertTrue(Shapes.cells("torus", 13, 13, 3, false, false, 0, 1).stream().noneMatch(p -> p[0] == 0 && p[2] == 6),
                "a hole in the middle of the donut");
    }

    @Test
    void everyNameMakesSomething() {
        for (String name : Shapes.FORMS.keySet()) {
            String form = Shapes.of(name);
            int[] d = Shapes.defaults(form);
            assertFalse(Shapes.cells(form, d[0], d[1], d[2], false, false, 6, 1).isEmpty(), name);
        }
    }
}
