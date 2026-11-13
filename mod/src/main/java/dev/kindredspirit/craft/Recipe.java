package dev.kindredspirit.craft;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/**
 * One way to make something, reduced to what planning needs: what comes out (and how many), the
 * ingredient slots (each slot accepts any one of a few items, like "any planks"), and where it's made
 * (by hand in the 2x2 grid, at a crafting table, in a furnace). Plain Java: the game's recipes are
 * turned into these by {@link GameRecipes}, tests write them by hand.
 */
public record Recipe(String result, int count, List<Set<String>> slots, Station station) {

    public enum Station {
        /** the 2x2 grid in your inventory */
        HAND,
        /** a 3x3 recipe */
        CRAFTING_TABLE,
        /** smelting: one ingredient, needs fuel */
        FURNACE
    }

    public Recipe {
        if (count <= 0) throw new IllegalArgumentException("a recipe makes at least one");
        slots = List.copyOf(slots.stream().map(Set::copyOf).toList());
    }

    /** A handy way to write recipes in tests: {@code of("stick", 4, HAND, "oak_planks|birch_planks", "oak_planks|birch_planks")}. */
    public static Recipe of(String result, int count, Station station, String... slots) {
        List<Set<String>> s = new ArrayList<>();
        for (String slot : slots) s.add(Set.of(slot.split("\\|")));
        return new Recipe(result, count, s, station);
    }
}
