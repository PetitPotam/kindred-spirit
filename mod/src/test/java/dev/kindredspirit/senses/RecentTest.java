package dev.kindredspirit.senses;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class RecentTest {
    @Test
    void theSameThingAgainIsCountedNotRepeated() {
        Recent r = new Recent(60000, 6);
        r.add(1000, "broke", "oak log");
        r.add(2000, "broke", "oak log");
        r.add(3000, "placed", "torch");
        r.add(4000, "broke", "oak log");
        r.add(5000, "hit", "zombie");
        assertEquals(List.of("hit a zombie", "broke 3 oak log", "placed a torch"), r.summary(6000, 30000));
    }

    @Test
    void oldThingsFade() {
        Recent r = new Recent(60000, 6);
        r.add(0, "ate", "apple");
        r.add(50000, "got", "oak planks", 4);
        r.add(51000, "ate", "apple");
        assertEquals(List.of("ate an apple", "got 4 oak planks"), r.summary(55000, 20000));
        assertEquals(List.of(), r.summary(200000, 20000), "forgotten after a while");
        assertTrue(new Recent(60000, 6).summary(0, 1000).isEmpty());
    }

    @Test
    void knowsWhatWasJustDone() {
        Recent r = new Recent(60000, 6);
        r.add(1000, "placed", "torch");
        assertTrue(r.did(2000, "placed", "torch", 5000));
        assertFalse(r.did(9000, "placed", "torch", 5000));
    }
}
