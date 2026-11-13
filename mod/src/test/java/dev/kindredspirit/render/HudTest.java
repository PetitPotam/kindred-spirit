package dev.kindredspirit.render;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class HudTest {
    @Test
    void shownWithTheGamesHud() {
        assertTrue(Hud.visible(false, false));
        assertTrue(Hud.visible(false, true));
    }

    @Test
    void hiddenWithF1UnlessTheSettingKeepsIt() {
        assertFalse(Hud.visible(true, false), "F1 hides her HUD by default");
        assertTrue(Hud.visible(true, true), "hudWithHiddenGui (ownhud on) keeps it for filming");
    }
}
