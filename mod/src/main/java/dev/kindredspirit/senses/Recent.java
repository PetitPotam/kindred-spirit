package dev.kindredspirit.senses;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Things that just happened, kept for a little while and told as a few short phrases: "broke 3 oak
 * log", "placed a torch", "hit a zombie". The same thing done again is counted, not repeated, so
 * mining a whole tunnel is one phrase. Plain Java, no game classes (tested on its own).
 */
public final class Recent {
    private record Entry(long at, String verb, String what, int n) {}

    private final Deque<Entry> entries = new ArrayDeque<>();
    private final long keepMs;
    private final int max;

    public Recent(long keepMs, int max) {
        this.keepMs = keepMs;
        this.max = max;
    }

    public void add(long now, String verb, String what) {
        add(now, verb, what, 1);
    }

    public synchronized void add(long now, String verb, String what, int n) {
        if (verb == null || what == null || what.isEmpty() || n <= 0) return;
        entries.addLast(new Entry(now, verb, what, n));
        while (entries.size() > 200) entries.removeFirst();
        forget(now);
    }

    /** What was done since {@code now - windowMs}, most recent first, counted: "broke 3 oak log". */
    public synchronized List<String> summary(long now, long windowMs) {
        forget(now);
        Map<String, int[]> counts = new LinkedHashMap<>();
        List<Entry> newestFirst = new ArrayList<>(entries);
        java.util.Collections.reverse(newestFirst);
        for (Entry e : newestFirst) {
            if (now - e.at() > windowMs) continue;
            counts.computeIfAbsent(e.verb() + "\u0000" + e.what(), k -> new int[1])[0] += e.n();
        }
        List<String> out = new ArrayList<>();
        for (Map.Entry<String, int[]> c : counts.entrySet()) {
            String[] vw = c.getKey().split("\u0000", 2);
            int n = c.getValue()[0];
            out.add(vw[0] + " " + (n == 1 ? article(vw[1]) : n + " " + vw[1]));
            if (out.size() >= max) break;
        }
        return out;
    }

    /** Recent things that were placed (or broken...) with this verb, to avoid telling them twice. */
    public synchronized boolean did(long now, String verb, String what, long withinMs) {
        for (Entry e : entries) {
            if (now - e.at() <= withinMs && e.verb().equals(verb) && e.what().equals(what)) return true;
        }
        return false;
    }

    private void forget(long now) {
        while (!entries.isEmpty() && now - entries.peekFirst().at() > keepMs) entries.removeFirst();
    }

    static String article(String what) {
        return (what.matches("^[aeiou].*") ? "an " : "a ") + what;
    }
}
