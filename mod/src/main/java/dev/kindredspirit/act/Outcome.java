package dev.kindredspirit.act;

import com.google.gson.JsonObject;

/**
 * How her last build, blueprint or job really ended (#139): what it was, how much was done of how much, how much
 * couldn't be (something in the way, too far), and why it stopped early, if it did. The snapshot carries it (with a
 * number that changes each time), so her brain speaks from the result, not from having started it: "Here's your
 * cottage!" only when it's really built, "I built most of it, but 12 blocks wouldn't fit" when it half-failed.
 * Written on the server thread, read by the snapshot on the client's: kept as one immutable object.
 */
public final class Outcome {
    private Outcome() {}

    private static volatile JsonObject last;
    private static int seq;

    /**
     * @param kind    build, blueprint or job
     * @param stopped null when it ran to the end; "asked" when you stopped it; else why ("your pockets are full")
     */
    public static synchronized void ended(String kind, String what, int done, int skipped, int total, String stopped) {
        if (total <= 0 && done <= 0) return; // (nothing was ever started)
        JsonObject o = new JsonObject();
        o.addProperty("seq", ++seq);
        o.addProperty("kind", kind);
        o.addProperty("what", what == null ? "" : what);
        o.addProperty("done", done);
        o.addProperty("skipped", skipped);
        o.addProperty("total", Math.max(total, done));
        if (stopped != null) o.addProperty("stopped", stopped);
        last = o;
        org.slf4j.LoggerFactory.getLogger("kindredspirit").info("outcome: {}", o);
    }

    /** The last outcome, or null when nothing has ended since the world opened. */
    public static JsonObject last() {
        return last;
    }

    public static synchronized void clear() {
        last = null;
    }
}
