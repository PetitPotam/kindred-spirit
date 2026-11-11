package dev.kindredspirit.util;

import java.util.Locale;

/**
 * Picks how detailed the companion is drawn and how often the game is described to the brain,
 * so a slow computer stays smooth. "auto" watches the frame rate and steps down when the game
 * struggles, and back up when there is headroom (with a delay, so it does not flicker).
 */
public final class Quality {
    public enum Level {
        //    sphere slices, stacks, glassy shell, snapshot every ms, mob scan radius
        LOW(8, 6, false, 2000, 16),
        MEDIUM(14, 10, true, 1000, 24),
        HIGH(22, 16, true, 1000, 24);

        public final int slices, stacks;
        public final boolean shell;
        public final int snapshotMs, scanRadius;

        Level(int slices, int stacks, boolean shell, int snapshotMs, int scanRadius) {
            this.slices = slices;
            this.stacks = stacks;
            this.shell = shell;
            this.snapshotMs = snapshotMs;
            this.scanRadius = scanRadius;
        }
    }

    static final int LOW_FPS = 30, HIGH_FPS = 75;
    static final int SECONDS_BEFORE_DOWN = 3, SECONDS_BEFORE_UP = 15;

    private final String setting;
    private Level level;
    private int slowSeconds, fastSeconds;

    /** @param setting "auto", "low", "medium" or "high" */
    public Quality(String setting) {
        this.setting = setting == null ? "auto" : setting.toLowerCase(Locale.ROOT);
        this.level = switch (this.setting) {
            case "low" -> Level.LOW;
            case "high" -> Level.HIGH;
            default -> Level.MEDIUM;
        };
    }

    public Level level() {
        return level;
    }

    public boolean isAuto() {
        return !setting.equals("low") && !setting.equals("medium") && !setting.equals("high");
    }

    /**
     * Call once per second.
     * @param fps          frames in the last second
     * @param fastGraphics the player chose "Fast" graphics: never go above MEDIUM
     */
    public Level update(int fps, boolean fastGraphics) {
        if (!isAuto()) return level;
        Level ceiling = fastGraphics ? Level.MEDIUM : Level.HIGH;
        if (level.ordinal() > ceiling.ordinal()) level = ceiling;
        if (fps < LOW_FPS) {
            fastSeconds = 0;
            if (++slowSeconds >= SECONDS_BEFORE_DOWN && level != Level.LOW) {
                level = Level.values()[level.ordinal() - 1];
                slowSeconds = 0;
            }
        } else if (fps > HIGH_FPS) {
            slowSeconds = 0;
            if (++fastSeconds >= SECONDS_BEFORE_UP && level.ordinal() < ceiling.ordinal()) {
                level = Level.values()[level.ordinal() + 1];
                fastSeconds = 0;
            }
        } else {
            slowSeconds = 0;
            fastSeconds = 0;
        }
        return level;
    }
}
