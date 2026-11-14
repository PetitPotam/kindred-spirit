package dev.kindredspirit.util;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

/** #187: putting her to sleep and waking her up from the game. */
class SleepTest {
    @Test
    void theGameAsksTheDashboardOnThisComputerOnly() {
        assertEquals("http://127.0.0.1:11440/api/her/sleep", Sleep.endpoint("127.0.0.1", 11440, "sleep"));
        assertEquals("http://127.0.0.1:11440/api/her/wake", Sleep.endpoint("", 11440, "wake"));
        assertNull(Sleep.endpoint("192.168.1.20", 11440, "wake"), "her brain on another computer: its dashboard answers there only");
        assertNull(Sleep.endpoint("127.0.0.1", 11440, "stop-all"), "the game never stops the dashboard itself");
    }

    @Test
    void asleepIsNotTheSameAsStopped() {
        assertTrue(Sleep.offline("Pip", true).contains("/kindred wake"));
        assertTrue(Sleep.offline("Pip", false).contains("scripts/start.sh"));
    }
}
