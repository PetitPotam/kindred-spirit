package dev.kindredspirit;

import java.util.Locale;

/**
 * Which chat messages go to the companion instead of the game's chat (setting {@code chatMode}):
 * <ul>
 *   <li><b>auto</b> (default): everything in singleplayer; on a server only messages that start
 *       with her name ("Pip, where are the cows?"), so you can still talk to other players</li>
 *   <li><b>all</b>: everything you type in chat goes to her</li>
 *   <li><b>name</b>: only messages that start with her name</li>
 *   <li><b>command</b>: only {@code /kindred ...} (and the talk key), nothing from plain chat</li>
 * </ul>
 * Pure Java, unit-tested.
 */
public final class ChatRoute {
    private ChatRoute() {}

    /** True if this chat message is meant for the companion. */
    public static boolean forCompanion(String mode, boolean singleplayer, String name, String text) {
        if (text == null || text.isBlank() || text.startsWith("/")) return false;
        String m = mode == null ? "auto" : mode.toLowerCase(Locale.ROOT);
        return switch (m) {
            case "all" -> true;
            case "command" -> false;
            case "name" -> addressed(name, text);
            default -> singleplayer || addressed(name, text);
        };
    }

    /** "Pip, ...", "pip: ...", "Hey Pip ...", "Pip" alone: the message starts by calling her. */
    static boolean addressed(String name, String text) {
        if (name == null || name.isBlank()) return false;
        String t = text.trim().toLowerCase(Locale.ROOT), n = name.toLowerCase(Locale.ROOT);
        for (String start : new String[]{"", "hey ", "hi ", "hello ", "oh ", "ok ", "okay "}) {
            String p = start + n;
            if (t.equals(p) || (t.startsWith(p) && !Character.isLetterOrDigit(t.charAt(p.length())))) return true;
        }
        return false;
    }
}
