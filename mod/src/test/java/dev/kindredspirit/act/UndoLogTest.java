package dev.kindredspirit.act;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/** #129: what her builds changed, so they can be undone. */
class UndoLogTest {
    @Test
    void theFirstStateSeenWinsAndTheNewestComesBackFirst() {
        UndoLog<String> log = new UndoLog<>();
        log.begin("a cottage", "overworld", true);
        log.before(1, "grass");
        log.before(2, "air");
        log.before(1, "planks"); // (changed twice: it goes back to grass, not to planks)
        UndoLog.Edit<String> e = log.pop();
        assertEquals("a cottage", e.name);
        assertEquals(Map.of(1L, "grass", 2L, "air"), e.before);
        List<Map.Entry<Long, String>> order = e.newestFirst();
        assertEquals(2L, order.get(0).getKey(), "the last changed is put back first");
        assertNull(log.pop(), "nothing left to undo");
    }

    @Test
    void severalBuildsUndoNewestFirstAndOnlyTheNewestSixteenAreKept() {
        UndoLog<String> log = new UndoLog<>();
        for (int i = 0; i < UndoLog.MAX_EDITS + 4; i++) {
            log.begin("build " + i, "overworld", false);
            log.before(i, "stone");
        }
        assertEquals(UndoLog.MAX_EDITS, log.size());
        assertEquals("build " + (UndoLog.MAX_EDITS + 3), log.pop().name);
        assertEquals("build " + (UndoLog.MAX_EDITS + 2), log.pop().name);
    }

    @Test
    void aBuildThatChangedNothingIsNotAnUndoStep() {
        UndoLog<String> log = new UndoLog<>();
        log.begin("a star", "overworld", true);
        log.begin("a wall", "overworld", true);
        log.before(7, "dirt");
        assertEquals("a wall", log.pop().name);
        assertNull(log.pop());
    }

    @Test
    void nothingIsRememberedOutsideABuild() {
        UndoLog<String> log = new UndoLog<>();
        log.before(1, "grass");
        assertNull(log.pop());
        assertEquals(0, log.size());
    }
}
