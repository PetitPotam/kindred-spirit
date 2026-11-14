package dev.kindredspirit.act;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * What her builds changed, so they can be undone (#129): for each build, the blocks as they were before she touched
 * them (the first state seen wins, so a spot changed twice goes back to how it was before the build). The newest
 * {@link #MAX_EDITS} builds are kept, in memory only (never in the world's save). Plain Java: the Minecraft side is
 * {@link Undo}; {@code S} is a block state there and a string in the tests.
 */
public final class UndoLog<S> {
    public static final int MAX_EDITS = 16;
    /** A build bigger than this (blocks remembered) can't be undone: memory stays small. */
    public static final int MAX_BLOCKS = 400_000;

    public static final class Edit<S> {
        public final String name, dimension;
        public final boolean magic;
        public final LinkedHashMap<Long, S> before = new LinkedHashMap<>();
        boolean tooBig;

        Edit(String name, String dimension, boolean magic) {
            this.name = name;
            this.dimension = dimension;
            this.magic = magic;
        }

        public boolean tooBig() {
            return tooBig;
        }

        /** The positions in the order to restore them: the last changed first. */
        public List<Map.Entry<Long, S>> newestFirst() {
            List<Map.Entry<Long, S>> out = new ArrayList<>(before.entrySet());
            java.util.Collections.reverse(out);
            return out;
        }
    }

    private final Deque<Edit<S>> edits = new ArrayDeque<>();
    private Edit<S> open;

    /** A new build starts: the one before it is kept as finished. */
    public synchronized void begin(String name, String dimension, boolean magic) {
        close();
        while (edits.size() > MAX_EDITS - 1) edits.removeLast(); // (with this one: MAX_EDITS in all)
        open = new Edit<>(name, dimension, magic);
    }

    /** A spot is about to change in the build in progress: remember it (if not already). */
    public synchronized void before(long pos, S state) {
        if (open == null || open.tooBig) return;
        if (open.before.size() >= MAX_BLOCKS && !open.before.containsKey(pos)) {
            open.tooBig = true;
            open.before.clear(); // (too big to undo: don't hold the memory)
            return;
        }
        open.before.putIfAbsent(pos, state);
    }

    private void close() {
        if (open != null && (open.tooBig || !open.before.isEmpty())) {
            edits.push(open);
            while (edits.size() > MAX_EDITS) edits.removeLast();
        }
        open = null;
    }

    /** The newest build, taken off the log (the one in progress included), or null when there's none. */
    public synchronized Edit<S> pop() {
        close();
        return edits.poll();
    }

    public synchronized int size() {
        return edits.size() + (open != null && !open.before.isEmpty() ? 1 : 0);
    }

    public synchronized void clear() {
        edits.clear();
        open = null;
    }
}
