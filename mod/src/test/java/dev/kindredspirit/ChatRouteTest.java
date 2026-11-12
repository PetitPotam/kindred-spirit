package dev.kindredspirit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ChatRouteTest {
    @Test
    void autoTalksToHerInSingleplayerAndByNameOnServers() {
        assertTrue(ChatRoute.forCompanion("auto", true, "Pip", "where are the cows?"));
        assertFalse(ChatRoute.forCompanion("auto", false, "Pip", "anyone want to trade?"), "other players on a server");
        assertTrue(ChatRoute.forCompanion("auto", false, "Pip", "Pip, where are the cows?"));
        assertFalse(ChatRoute.forCompanion("auto", true, "Pip", "/time set day"), "commands stay commands");
    }

    @Test
    void nameAndCommandModes() {
        assertTrue(ChatRoute.forCompanion("name", true, "Pip", "hey pip look at this"));
        assertTrue(ChatRoute.forCompanion("name", true, "Pip", "Pip"));
        assertFalse(ChatRoute.forCompanion("name", true, "Pip", "pipe dreams"), "not her name, just starts like it");
        assertFalse(ChatRoute.forCompanion("name", true, "Pip", "where are the cows?"));
        assertFalse(ChatRoute.forCompanion("command", true, "Pip", "Pip, hi"));
        assertTrue(ChatRoute.forCompanion("all", false, "Pip", "hello"));
    }
}
