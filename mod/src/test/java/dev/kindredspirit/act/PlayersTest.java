package dev.kindredspirit.act;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PlayersTest {
    @Test
    void namesSaidRoughlyStillMatch() {
        assertEquals(3, Players.score("riverrobin", Players.squash("RiverRobin")));
        assertEquals(2, Players.score("riverrobin", Players.squash("robin")));
        assertEquals(3, Players.score("riverrobin", Players.squash("River Robin")));
        assertEquals(1, Players.score("riverrobin", Players.squash("river robeen")));
        assertEquals(0, Players.score("riverrobin", Players.squash("steve")));
    }
}
