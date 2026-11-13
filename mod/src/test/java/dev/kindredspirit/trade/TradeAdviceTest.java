package dev.kindredspirit.trade;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class TradeAdviceTest {

    static final TradeAdvice.Offer WHEAT = new TradeAdvice.Offer("minecraft:wheat", 20, "", 0, "minecraft:emerald", 1, 4, 16, "");
    static final TradeAdvice.Offer BREAD = new TradeAdvice.Offer("minecraft:emerald", 1, "", 0, "minecraft:bread", 6, 0, 16, "");
    static final TradeAdvice.Offer MENDING = new TradeAdvice.Offer("minecraft:emerald", 24, "minecraft:book", 1,
            "minecraft:enchanted_book", 1, 0, 12, "mending 1");
    static final TradeAdvice.Offer PUMPKIN = new TradeAdvice.Offer("minecraft:pumpkin", 6, "", 0, "minecraft:emerald", 1, 12, 12, "");

    @Test
    void sellingWhatYouHaveComesFirstThenTreasures() {
        List<TradeAdvice.Advice> a = TradeAdvice.advise("Farmer (novice)", List.of(BREAD, PUMPKIN, MENDING, WHEAT),
                Map.of("minecraft:wheat", 64, "minecraft:emerald", 2));
        assertEquals(List.of(WHEAT, MENDING, BREAD, PUMPKIN), a.stream().map(TradeAdvice.Advice::offer).toList());
        assertEquals(3, a.get(0).timesNow(), "64 wheat is three trades of 20");
        assertTrue(a.get(1).treasure(), "Mending is worth pointing out even when you can't afford it");
        assertEquals(0, a.get(1).timesNow());
        assertEquals(2, a.get(2).timesNow());
        assertEquals(0, a.get(3).timesNow(), "sold out");
    }

    @Test
    void stockLimitsHowOften() {
        TradeAdvice.Offer nearlyOut = new TradeAdvice.Offer("minecraft:wheat", 20, "", 0, "minecraft:emerald", 1, 15, 16, "");
        assertEquals(1, TradeAdvice.advise("", List.of(nearlyOut), Map.of("minecraft:wheat", 200)).get(0).timesNow());
    }

    @Test
    void linesSayItPlainly() {
        List<TradeAdvice.Advice> a = TradeAdvice.advise("Farmer (novice)", List.of(WHEAT, PUMPKIN, MENDING),
                Map.of("minecraft:wheat", 20));
        assertEquals("Farmer (novice): 20 wheat → 1 emerald. You could do it once (12 left).", a.get(0).line());
        assertTrue(a.get(1).line().contains("24 emerald + 1 book → 1 enchanted book (mending 1)"), a.get(1).line());
        assertTrue(a.get(1).line().endsWith("You don't have enough for it. A good one."), a.get(1).line());
        assertTrue(a.get(2).line().contains("Sold out"), a.get(2).line());
    }
}
