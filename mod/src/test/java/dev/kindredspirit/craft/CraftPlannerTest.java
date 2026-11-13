package dev.kindredspirit.craft;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static dev.kindredspirit.craft.Recipe.Station.CRAFTING_TABLE;
import static dev.kindredspirit.craft.Recipe.Station.FURNACE;
import static dev.kindredspirit.craft.Recipe.Station.HAND;
import static org.junit.jupiter.api.Assertions.*;

/** The planner on a small copy of vanilla's recipes (as GameRecipes would give them, ids shortened). */
class CraftPlannerTest {

    static final String PLANKS = "oak_planks|birch_planks";
    static final String STONE = "cobblestone|cobbled_deepslate|blackstone";

    static final CraftPlanner P = new CraftPlanner(List.of(
            Recipe.of("oak_planks", 4, HAND, "oak_log"),
            Recipe.of("birch_planks", 4, HAND, "birch_log"),
            Recipe.of("stick", 4, HAND, PLANKS, PLANKS),
            Recipe.of("crafting_table", 1, HAND, PLANKS, PLANKS, PLANKS, PLANKS),
            Recipe.of("wooden_pickaxe", 1, CRAFTING_TABLE, PLANKS, PLANKS, PLANKS, "stick", "stick"),
            Recipe.of("stone_pickaxe", 1, CRAFTING_TABLE, STONE, STONE, STONE, "stick", "stick"),
            Recipe.of("furnace", 1, CRAFTING_TABLE, "cobblestone", "cobblestone", "cobblestone", "cobblestone",
                    "cobblestone", "cobblestone", "cobblestone", "cobblestone"),
            Recipe.of("iron_ingot", 1, FURNACE, "raw_iron"),
            Recipe.of("iron_ingot", 9, CRAFTING_TABLE, "iron_block"),
            Recipe.of("iron_ingot", 1, CRAFTING_TABLE, "iron_nugget", "iron_nugget", "iron_nugget", "iron_nugget",
                    "iron_nugget", "iron_nugget", "iron_nugget", "iron_nugget", "iron_nugget"),
            Recipe.of("iron_block", 1, CRAFTING_TABLE, "iron_ingot", "iron_ingot", "iron_ingot", "iron_ingot",
                    "iron_ingot", "iron_ingot", "iron_ingot", "iron_ingot", "iron_ingot"),
            Recipe.of("iron_nugget", 9, HAND, "iron_ingot"),
            Recipe.of("piston", 1, CRAFTING_TABLE, PLANKS, PLANKS, PLANKS, "cobblestone", "cobblestone", "cobblestone",
                    "cobblestone", "iron_ingot", "redstone"),
            Recipe.of("torch", 4, HAND, "coal|charcoal", "stick"),
            Recipe.of("charcoal", 1, FURNACE, "oak_log|birch_log"),
            Recipe.of("coal", 1, FURNACE, "coal_ore|deepslate_coal_ore"),
            Recipe.of("iron_ingot", 1, FURNACE, "iron_ore|deepslate_iron_ore")));

    @Test
    void aPistonFromLogsAndRawIron() {
        CraftPlanner.Plan p = P.plan("piston", 1, Map.of("birch_log", 1, "cobblestone", 4, "raw_iron", 1, "redstone", 1));
        assertTrue(p.canMakeNow(), "missing: " + p.missing());
        assertEquals(List.of("birch_planks", "iron_ingot", "piston"), p.steps().stream().map(s -> s.recipe().result()).toList(),
                "planks and the ingot first, then the piston");
        assertEquals(Set.of(CRAFTING_TABLE, FURNACE), p.stations());
        assertEquals(1, p.smeltedItems());
        assertEquals(Map.of("birch_log", 1, "cobblestone", 4, "raw_iron", 1, "redstone", 1), p.fromInventory());
        assertEquals(Map.of("piston", 1, "birch_planks", 1), p.after(), "one plank left over");
    }

    @Test
    void whatsMissingWhenYouHaveNothing() {
        CraftPlanner.Plan p = P.plan("stone_pickaxe", 1, Map.of());
        assertFalse(p.canMakeNow());
        assertEquals(Map.of("cobblestone", 3, "oak_log", 1), p.missing(),
                "with nothing in the pockets she names what most people use: cobblestone, an oak log");
    }

    @Test
    void oreBlocksAreTheLastResort() {
        CraftPlanner.Plan torches = P.plan("torch", 8, Map.of());
        assertFalse(torches.missing().keySet().stream().anyMatch(k -> k.endsWith("_ore")),
                "not 'smelt coal ore' (only Silk Touch brings ore home): " + torches.missing());
        CraftPlanner.Plan ingot = P.plan("iron_ingot", 1, Map.of());
        assertEquals(Map.of("raw_iron", 1), ingot.missing());
        CraftPlanner.Plan withOre = P.plan("iron_ingot", 1, Map.of("iron_ore", 1));
        assertTrue(withOre.canMakeNow(), "but an ore block in the pockets is fine to smelt");
    }

    @Test
    void itUsesTheWoodYouHave() {
        CraftPlanner.Plan p = P.plan("wooden_pickaxe", 1, Map.of("oak_log", 2));
        assertTrue(p.canMakeNow(), "missing: " + p.missing());
        assertTrue(p.steps().stream().anyMatch(s -> s.recipe().result().equals("oak_planks")));
        assertFalse(p.steps().stream().anyMatch(s -> s.recipe().result().equals("birch_planks")));
        assertEquals(1, p.after().get("wooden_pickaxe"));
    }

    @Test
    void mixingAcceptedItemsInOneRecipe() {
        CraftPlanner.Plan p = P.plan("wooden_pickaxe", 1, Map.of("oak_planks", 1, "birch_planks", 2, "stick", 2));
        assertTrue(p.canMakeNow(), "missing: " + p.missing());
        assertEquals(1, p.steps().size(), "nothing to craft first");
        assertEquals(Map.of("oak_planks", 1, "birch_planks", 2, "stick", 2), p.steps().get(0).uses());
        assertEquals(Map.of("wooden_pickaxe", 1), p.after());
    }

    @Test
    void sparesAreUsedAndKept() {
        CraftPlanner.Plan p = P.plan("torch", 8, Map.of("coal", 2, "oak_planks", 2));
        assertTrue(p.canMakeNow(), "missing: " + p.missing());
        assertEquals(1, p.steps().get(0).times(), "one stick craft makes the 4 sticks: 2 used, 2 spare");
        assertEquals(2, p.steps().get(1).times());
        assertEquals(Map.of("torch", 8, "stick", 2), p.after());
    }

    @Test
    void recipeLoopsEnd() {
        CraftPlanner.Plan p = P.plan("iron_block", 1, Map.of());
        assertEquals(Map.of("raw_iron", 9), p.missing(), "nine raw iron to smelt, not an endless loop");
        CraftPlanner.Plan noFurnace = P.plan("iron_block", 1, Map.of(), false);
        assertFalse(noFurnace.canMakeNow());
        assertFalse(noFurnace.missing().containsKey("raw_iron"), "without smelting raw iron is no use");
    }

    @Test
    void theTargetIsMadeEvenIfYouHaveOne() {
        CraftPlanner.Plan p = P.plan("crafting_table", 1, Map.of("crafting_table", 1, "oak_planks", 4));
        assertTrue(p.canMakeNow());
        assertEquals(Map.of("crafting_table", 2), p.after());
        assertEquals(Set.of(), p.stations(), "a crafting table is made by hand");
    }

    @Test
    void unknownThingsAreSimplyMissing() {
        CraftPlanner.Plan p = P.plan("diamond", 2, Map.of("oak_log", 5));
        assertEquals(Map.of("diamond", 2), p.missing());
        assertTrue(p.steps().isEmpty());
        assertEquals(Map.of("oak_log", 5), p.after(), "nothing used");
    }

    @Test
    void severalOfTheSameStepAreOne() {
        CraftPlanner.Plan p = P.plan("stick", 12, Map.of("oak_log", 2));
        assertTrue(p.canMakeNow(), "missing: " + p.missing());
        assertEquals(List.of("oak_planks", "stick"), p.steps().stream().map(s -> s.recipe().result()).toList());
        assertEquals(3, p.steps().get(1).times());
        assertEquals(12, p.after().get("stick"));
    }
}
