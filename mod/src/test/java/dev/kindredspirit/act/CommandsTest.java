package dev.kindredspirit.act;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

/** Her commands' safety checks (the allowlist, selectors, distance, effects, mobs). */
class CommandsTest {
    static String check(String c, Abilities.Power p, boolean harmful) {
        return Commands.check(c, p, 100, 64, 100, harmful);
    }

    @Test
    void buildingAndGiftsWithMagicHelperWorldChangesAllPowerfulOnly() {
        assertNull(check("/fill ~-5 ~ ~-5 ~5 ~3 ~5 dirt", Abilities.Power.HELPER, false));
        assertNull(check("setblock 101 64 99 red_bed[part=foot,facing=north]", Abilities.Power.HELPER, false));
        assertNull(check("enchant AlexCraftX efficiency 3", Abilities.Power.HELPER, false));
        assertNotNull(check("time set day", Abilities.Power.HELPER, false));
        assertNull(check("time set day", Abilities.Power.ALLPOWERFUL, false));
        assertNotNull(check("kill @e", Abilities.Power.ALLPOWERFUL, false));
        assertNotNull(check("op AlexCraftX", Abilities.Power.ALLPOWERFUL, false));
    }

    @Test
    void neverEveryoneNeverFarNeverNested() {
        assertNotNull(check("effect give @a speed 30", Abilities.Power.ALLPOWERFUL, false));
        assertNotNull(check("fill 5000 64 5000 5010 70 5010 stone", Abilities.Power.ALLPOWERFUL, false));
        assertNotNull(check("fill ~ ~ ~ ~200 ~ ~ stone", Abilities.Power.ALLPOWERFUL, false));
        assertNotNull(check("execute as @s run kill @s", Abilities.Power.ALLPOWERFUL, false));
    }

    @Test
    void harmfulEffectsOnlyWhenAskedShortAndNeverLethal() {
        assertNotNull(check("effect give Robin poison 5", Abilities.Power.HELPER, false));
        assertNull(check("effect give Robin poison 5", Abilities.Power.HELPER, true));
        assertNotNull(check("effect give Robin poison 60", Abilities.Power.HELPER, true));
        assertNotNull(check("effect give Robin instant_damage 1", Abilities.Power.HELPER, true));
        assertNull(check("effect give Robin speed 120 1", Abilities.Power.HELPER, false));
    }

    @Test
    void noDangerousMobs() {
        assertNotNull(check("summon wither ~ ~ ~5", Abilities.Power.ALLPOWERFUL, false));
        assertNull(check("summon zombie ~3 ~ ~3", Abilities.Power.ALLPOWERFUL, false));
    }
}
