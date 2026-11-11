package dev.kindredspirit.skin;

import com.google.gson.JsonParser;
import dev.kindredspirit.render.ShapeMesh;
import org.junit.jupiter.api.Test;

import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.*;

class SkinTest {
    static Skin parse(String json) {
        return Skin.parse("test", JsonParser.parseString(json).getAsJsonObject());
    }

    @Test
    void emptyJsonIsTheClassicSlime() {
        Skin s = parse("{}");
        assertEquals(Skin.Shape.BALL, s.shape());
        assertEquals(Skin.Tint.MOOD, s.tint());
        assertTrue(s.shell() && s.face() && !s.glow());
        assertEquals(0xFF8FAB, s.cheeks());
        assertEquals(1.0f, s.size());
    }

    @Test
    void wispsGlowAndHaveNoCheeksByDefault() {
        Skin s = parse("{\"shape\": \"wisp\"}");
        assertTrue(s.glow());
        assertEquals(Skin.NO_CHEEKS, s.cheeks());
        assertTrue(s.size() < 1);
    }

    @Test
    void fairiesHaveWingsAndFloat() {
        Skin f = parse("{\"shape\": \"fairy\"}");
        assertTrue(f.wings() && f.floaty() && f.glow());
        assertTrue(f.size() < 1);
        Skin winged = parse("{\"shape\": \"ball\", \"wings\": true, \"wingColor\": \"#FFD0E0\"}");
        assertTrue(winged.wings(), "any shape can have wings");
        assertFalse(winged.floaty(), "a winged slime still hops");
        assertEquals(0xFFD0E0, winged.wingColor());
        assertFalse(parse("{}").wings());
    }

    @Test
    void colorsAndBadValuesAreForgiving() {
        Skin s = parse("{\"shape\": \"CUBE\", \"tint\": \"#3366ff\", \"size\": 99, \"eyes\": \"oops\", \"cheeks\": \"none\"}");
        assertEquals(Skin.Shape.CUBE, s.shape());
        assertEquals(Skin.Tint.FIXED, s.tint());
        assertEquals(0x3366FF, s.color());
        assertEquals(3f, s.size(), "size is capped");
        assertEquals(0x1E1A2E, s.eyes(), "bad color falls back to the default");
        assertEquals(Skin.NO_CHEEKS, s.cheeks());
        assertEquals(Skin.Shape.BALL, parse("{\"shape\": \"dragon\"}").shape());
    }

    @Test
    void fileNamesBecomeSafeIds() {
        assertEquals("my_cool_skin", SkinRegistry.sanitize("My Cool Skin"));
        assertEquals("skin", SkinRegistry.sanitize(""));
    }

    @Test
    void builtInSkinsAllParse() throws Exception {
        for (String id : new String[]{"slime", "slime_cube", "wisp", "strawberry", "starry", "fairy", "pixie"}) {
            try (var in = getClass().getResourceAsStream("/assets/kindredspirit/skins/" + id + ".json")) {
                assertNotNull(in, id + ".json is packaged");
                Skin s = Skin.parse(id, JsonParser.parseReader(new InputStreamReader(in, StandardCharsets.UTF_8)).getAsJsonObject());
                if (!s.texture().isEmpty()) {
                    String path = "/assets/kindredspirit/" + s.texture().substring(s.texture().indexOf(':') + 1);
                    assertNotNull(getClass().getResource(path), id + " texture exists: " + path);
                }
            }
        }
    }

    @Test
    void cubeFaceSitsOnTheCubeSurface() {
        ShapeMesh cube = new ShapeMesh(Skin.Shape.CUBE, 14, 10), ball = new ShapeMesh(Skin.Shape.BALL, 14, 10);
        assertEquals(1.0, ball.front(0, 0), 1e-9);
        assertEquals(0.86, cube.front(0, 0), 1e-6);
        assertTrue(cube.front(0.6, 0) > ball.front(0.6, 0), "a cube's face stays flat further out");
    }
}
