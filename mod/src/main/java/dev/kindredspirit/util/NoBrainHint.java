package dev.kindredspirit.util;

/**
 * #92: someone who installs only the mod (from Modrinth, say) and has no brain on their computer saw nothing at all,
 * and thought it was broken. In their own world, a few seconds after it opens, one chat message says what Pip needs
 * and where to get it, once per game, until they switch it off ("/kindred hint off", or its "Don't show again").
 * Friends who join a host's LAN world never see it: there, the host's Pip is the point.
 */
public final class NoBrainHint {
    private NoBrainHint() {}

    /** Kindred Spirit Setup, how to download and open it (until the website has its Download page). */
    public static final String SETUP_GUIDE = "https://github.com/PetitPotam/kindred-spirit/blob/main/docs/SETUP.md";
    /** Playing with a friend who hosts her. */
    public static final String FRIENDS_GUIDE = "https://github.com/PetitPotam/kindred-spirit/blob/main/docs/PLAY-WITH-FRIENDS.md";
    /** Five seconds after the world opens, after the game's own messages. */
    public static final int DELAY_TICKS = 100;

    /**
     * Whether to show it now: no brain set up on this computer, the hint not switched off, in the player's own
     * world (singleplayer, or hosting it on LAN), not shown yet in this game, and the world open for a few seconds.
     */
    public static boolean due(boolean brainHere, boolean enabled, boolean ownWorld, boolean shownThisGame, int ticksInWorld) {
        return !brainHere && enabled && ownWorld && !shownThisGame && ticksInWorld >= DELAY_TICKS;
    }
}
