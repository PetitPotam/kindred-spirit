package dev.kindredspirit.util;

import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.*;

/** #92 (the "Pip needs her brain" hint) and #114 (the mod's real version in its hello). */
class SetupHintTest {
    private static final int LATER = NoBrainHint.DELAY_TICKS;

    @Test
    void theHintShowsOnceInYourOwnWorldWhenThereIsNoBrain() {
        assertTrue(NoBrainHint.due(false, true, true, false, LATER));
        assertFalse(NoBrainHint.due(false, true, true, false, LATER - 1), "not before the world has settled");
        assertFalse(NoBrainHint.due(true, true, true, false, LATER), "her brain is here: nothing to say");
        assertFalse(NoBrainHint.due(false, false, true, false, LATER), "switched off (Don't show again)");
        assertFalse(NoBrainHint.due(false, true, false, false, LATER), "a friend's world: their Pip is the point");
        assertFalse(NoBrainHint.due(false, true, true, true, LATER), "once per game");
    }

    @Test
    void theHintLinksToTheGuides() {
        assertEquals("https://kindred-spirit-pip.web.app/download", NoBrainHint.SETUP_GUIDE, "the website's Download page");
        assertTrue(NoBrainHint.FRIENDS_GUIDE.startsWith("https://"));
    }

    @Test
    void modMenusHomepageIsTheDownloadPageToo() throws Exception {
        try (InputStream in = SetupHintTest.class.getResourceAsStream("/fabric.mod.json")) {
            assertNotNull(in, "fabric.mod.json on the classpath");
            String json = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            assertTrue(json.contains("\"homepage\": \"" + NoBrainHint.SETUP_GUIDE + "\""), "homepage = " + NoBrainHint.SETUP_GUIDE);
        }
    }

    @Test
    void theModSaysItsReleaseNotZeroPointOne() {
        assertEquals("0.3.0", ModVersion.release("0.3.0+26.3"));
        assertEquals("0.3.0-beta.1", ModVersion.release("0.3.0-beta.1+1.21.1"));
        assertEquals("0.2.0-preview", ModVersion.release("0.2.0-preview"));
        assertEquals("unknown", ModVersion.release(null));
        assertEquals("unknown", ModVersion.release("${version}"));
    }
}
