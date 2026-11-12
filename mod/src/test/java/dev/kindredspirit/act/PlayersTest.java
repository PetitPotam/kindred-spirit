package dev.kindredspirit.act;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PlayersTest {
    @Test
    void namesSaidRoughlyStillMatch() {
        assertEquals(3, Players.score("waterwalid", Players.squash("WaterWalid")));
        assertEquals(2, Players.score("waterwalid", Players.squash("walid")));
        assertEquals(3, Players.score("waterwalid", Players.squash("Water Walid")));
        assertEquals(1, Players.score("waterwalid", Players.squash("water waleed")));
        assertEquals(0, Players.score("waterwalid", Players.squash("steve")));
    }
}
