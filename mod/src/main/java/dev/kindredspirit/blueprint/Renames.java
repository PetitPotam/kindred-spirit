package dev.kindredspirit.blueprint;

import java.util.Map;

/**
 * Block names that changed between versions, for files saved in another version than 1.21.1.
 *
 * <p>In the game, the real fix is Mojang's DataFixerUpper (the same upgrade vanilla runs when it loads
 * an old structure: {@code DataFixTypes.STRUCTURE.updateToCurrentVersion}), which the in-game loader
 * should apply using {@link Blueprint#dataVersion()}. This table only covers the renames people hit
 * most, so plain-Java previews and material lists are right without the game: "grass" became
 * "short_grass" in 1.20.3; newer versions (1.21.9+) renamed "chain" to "iron_chain", which 1.21.1
 * doesn't know, so a file from a newer game is brought back.
 *
 * <p>Files from before 1.13 (numeric ids, the MCEdit {@code .schematic}) aren't handled here at all:
 * see {@link Blueprints}.
 */
final class Renames {
    private Renames() {}

    private static final Map<String, String> NAMES = Map.of(
            "minecraft:grass", "minecraft:short_grass",
            "minecraft:iron_chain", "minecraft:chain");

    static BlockSpec apply(BlockSpec s) {
        String to = NAMES.get(s.name());
        return to == null ? s : new BlockSpec(to, s.properties());
    }
}
