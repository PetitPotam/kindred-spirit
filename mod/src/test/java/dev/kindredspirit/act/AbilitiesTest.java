package dev.kindredspirit.act;

import dev.kindredspirit.act.Abilities.Ability;
import dev.kindredspirit.act.Abilities.Power;
import dev.kindredspirit.act.Abilities.Style;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class AbilitiesTest {
    @Test
    void advisorOnlyReadsTheWorld() {
        for (Ability a : Ability.values()) {
            assertEquals(!a.changesWorld, Abilities.allowed(a, Power.ADVISOR, Style.MAGIC), a.name());
        }
    }

    @Test
    void groundedHelperProtectsAndLightsButMakesNothingAppear() {
        assertTrue(Abilities.allowed(Ability.PROTECT, Power.HELPER, Style.GROUNDED));
        assertTrue(Abilities.allowed(Ability.PLACE_TORCH, Power.HELPER, Style.GROUNDED));
        assertTrue(Abilities.allowed(Ability.HARVEST, Power.HELPER, Style.GROUNDED));
        assertTrue(Abilities.allowed(Ability.FIND_BLOCK, Power.ADVISOR, Style.GROUNDED), "finding is only looking");
        assertFalse(Abilities.allowed(Ability.HARVEST, Power.ADVISOR, Style.MAGIC));
        assertFalse(Abilities.allowed(Ability.GIVE_ITEM, Power.HELPER, Style.GROUNDED));
        assertTrue(Abilities.allowed(Ability.GIVE_ITEM, Power.HELPER, Style.MAGIC));
        assertTrue(Abilities.refusal(Ability.GIVE_ITEM, Power.HELPER, Style.GROUNDED).contains("grounded"));
    }

    @Test
    void onlyAllPowerfulChangesTimeAndWeather() {
        assertFalse(Abilities.allowed(Ability.SET_TIME, Power.HELPER, Style.MAGIC));
        assertTrue(Abilities.allowed(Ability.SET_WEATHER, Power.ALLPOWERFUL, Style.GROUNDED));
        assertTrue(Abilities.allowedIds(Power.ALLPOWERFUL, Style.MAGIC).containsAll(java.util.List.of("give_item", "set_time")));
    }

    @Test
    void unknownSettingsFallBackToTheGentleDefaults() {
        assertEquals(Power.HELPER, Abilities.power("godmode"));
        assertEquals(Style.GROUNDED, Abilities.style(""));
        assertNull(Abilities.ability("explode"));
    }

    @Test
    void oreWords() {
        assertEquals("sheep", Places.creatureKind("sheeps"));
        assertEquals("wolf", Places.creatureKind("Wolves"));
        assertEquals("bunny", Places.creatureKind("bunnies"));
        assertEquals("cow", Places.creatureKind("a cow"));
        assertTrue(Places.isCreature("donkey", "horse") && Places.isCreature("pig", "animal"));
        assertFalse(Places.isCreature("zombie", "animal"));
        assertEquals("diamond", Places.oreKind("Diamonds"));
        assertEquals("iron", Places.oreKind("minecraft:deepslate_iron_ore"));
        assertEquals("ancient_debris", Places.oreKind("ancient debris"));
        assertTrue(Places.isOre("deepslate_diamond_ore", "diamond"));
        assertTrue(Places.isOre("nether_gold_ore", "gold"));
        assertFalse(Places.isOre("diamond_block", "diamond"));
        assertTrue(Places.isOre("ancient_debris", "netherite"));
    }

    @Test
    void compassMatchesMinecraft() {
        assertEquals("north", Places.compass(0, -10));
        assertEquals("east", Places.compass(10, 0));
        assertEquals("south-west", Places.compass(-10, 10));
    }
}
