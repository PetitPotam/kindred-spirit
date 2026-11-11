package dev.kindredspirit.util;

import java.util.Locale;

/** The companion's moods. Each one has a color and a bounce style. The brain decides the mood. */
public enum Mood {
    HAPPY(0x7ADC6E, 1.0f, 1.0f),
    EXCITED(0xFFD250, 1.8f, 1.3f),
    CALM(0x6EC8DC, 0.6f, 0.6f),
    CURIOUS(0xAA8CFF, 1.1f, 0.9f),
    WORRIED(0xFF9646, 1.3f, 0.7f),
    SCARED(0xF05A78, 2.2f, 0.5f),
    SAD(0x6E8CE6, 0.5f, 0.4f),
    SLEEPY(0xA096BE, 0.35f, 0.3f),
    OFFLINE(0x9A9AA2, 0.3f, 0.25f);

    public final int rgb;
    /** How fast it bounces, and how high, relative to HAPPY. */
    public final float speed, height;

    Mood(int rgb, float speed, float height) {
        this.rgb = rgb;
        this.speed = speed;
        this.height = height;
    }

    public static Mood parse(String name, Mood fallback) {
        if (name == null) return fallback;
        try {
            return valueOf(name.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException e) {
            return fallback;
        }
    }

    /** Blends two 0xRRGGBB colors; t=0 gives a, t=1 gives b. */
    public static int blend(int a, int b, float t) {
        t = Math.max(0f, Math.min(1f, t));
        int r = Math.round(((a >> 16) & 0xff) + (((b >> 16) & 0xff) - ((a >> 16) & 0xff)) * t);
        int g = Math.round(((a >> 8) & 0xff) + (((b >> 8) & 0xff) - ((a >> 8) & 0xff)) * t);
        int bl = Math.round((a & 0xff) + ((b & 0xff) - (a & 0xff)) * t);
        return (r << 16) | (g << 8) | bl;
    }

    /** Multiplies each channel by f (f < 1 darkens). */
    public static int shade(int rgb, float f) {
        int r = Math.min(255, Math.round(((rgb >> 16) & 0xff) * f));
        int g = Math.min(255, Math.round(((rgb >> 8) & 0xff) * f));
        int b = Math.min(255, Math.round((rgb & 0xff) * f));
        return (r << 16) | (g << 8) | b;
    }
}
