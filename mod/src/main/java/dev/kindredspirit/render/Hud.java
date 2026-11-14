package dev.kindredspirit.render;

/** Whether something of hers is drawn when the game's HUD may be hidden (F1). Pure Java, unit-tested. */
public final class Hud {
    private Hud() {}

    /**
     * Shown unless the game's HUD is hidden, or even then when its setting says so
     * ({@code hudWithHiddenGui} for her own HUD, {@code subtitlesWithHiddenHud} for the subtitles above her).
     */
    public static boolean visible(boolean hudHidden, boolean withHidden) {
        return !hudHidden || withHidden;
    }
}
