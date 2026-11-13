package dev.kindredspirit.util;

/**
 * The mod's own version, from its fabric.mod.json (#114): the game tells her brain in its hello, so the brain (and
 * later the Setup's updates, #97) can tell a mod and a brain from different releases apart. Before, it always said 0.1.0.
 */
public final class ModVersion {
    private ModVersion() {}

    /** "0.3.0+26.3" (the version and the Minecraft it's built for) -> "0.3.0", the release both sides share. */
    public static String release(String version) {
        if (version == null || version.isBlank() || version.startsWith("$")) return "unknown"; // (an unfilled template)
        int plus = version.indexOf('+');
        return (plus > 0 ? version.substring(0, plus) : version).trim();
    }

    /** This mod's release, as Fabric Loader read it from the jar. */
    public static String get() {
        return release(net.fabricmc.loader.api.FabricLoader.getInstance().getModContainer("kindredspirit")
                .map(c -> c.getMetadata().getVersion().getFriendlyString()).orElse(null));
    }
}
