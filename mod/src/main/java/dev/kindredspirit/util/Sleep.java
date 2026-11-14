package dev.kindredspirit.util;

import java.nio.file.Path;

/**
 * Putting her to sleep and waking her up (#187). Her dashboard does it ("Put her to sleep" stops her brain, voice and
 * hearing and leaves a marker file, ~/.kindred-spirit/asleep; waking her starts them again); in game
 * {@code /kindred sleep} and {@code /kindred wake} ask the dashboard, and while the marker is there the game says she's
 * asleep instead of "her brain isn't running".
 */
public final class Sleep {
    private Sleep() {}

    public static Path marker() {
        return Path.of(System.getProperty("user.home"), ".kindred-spirit", "asleep");
    }

    /** The dashboard's address for sleep, wake or stop-all, or null when her brain isn't on this computer. */
    public static String endpoint(String brainHost, int dashboardPort, String what) {
        String url = Dashboard.url(brainHost, dashboardPort);
        if (url == null || !(what.equals("sleep") || what.equals("wake"))) return null;
        return url + "api/her/" + what;
    }

    /** What the game says while her brain isn't there. */
    public static String offline(String name, boolean asleep) {
        return asleep ? name + " is asleep: /kindred wake (or her dashboard, K) wakes her up."
                : name + "'s brain isn't running: start it with scripts/start.sh (she'll come back by herself).";
    }
}
