package dev.kindredspirit.act;

import dev.kindredspirit.util.Mc;
import dev.kindredspirit.blueprint.BlockSpec;
import dev.kindredspirit.blueprint.CatalogueIndex;
import dev.kindredspirit.blueprint.Picture;
import net.minecraft.commands.arguments.blocks.BlockStateParser;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.level.EmptyBlockGetter;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.material.MapColor;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Keeps the catalogue of her blueprint folders up to date (see {@link CatalogueIndex}): once when the game
 * starts, then whenever a folder changes (checked every 30 seconds, quietly, on its own thread), so a file
 * added from the dashboard is described and pictured within half a minute while the game runs. The
 * pictures use Minecraft's own map colours.
 */
public final class BlueprintCatalogue {
    private BlueprintCatalogue() {}

    private static final org.slf4j.Logger LOG = org.slf4j.LoggerFactory.getLogger("kindredspirit");
    private static final Map<BlockSpec, Integer> colors = new ConcurrentHashMap<>();
    private static volatile boolean started;

    public static void start() {
        if (started) return;
        started = true;
        Thread t = new Thread(() -> {
            while (true) {
                for (Path dir : BlueprintBuild.folders()) refreshIfStale(dir);
                try {
                    Thread.sleep(30_000);
                } catch (InterruptedException e) {
                    return;
                }
            }
        }, "kindred-blueprint-catalogue");
        t.setDaemon(true);
        t.setPriority(Thread.MIN_PRIORITY);
        t.start();
    }

    /** Refreshes one folder now if it changed (also used right after a build from a new file). */
    public static void refreshIfStale(Path dir) {
        if (!Files.isDirectory(dir) || !CatalogueIndex.stale(dir)) return;
        try {
            long t0 = System.currentTimeMillis();
            var out = CatalogueIndex.refresh(dir, BlueprintCatalogue::color);
            LOG.info("blueprint catalogue: {} in {} ({} unreadable) in {} ms", out.getAsJsonArray("entries").size(), dir,
                    out.getAsJsonArray("errors").size(), System.currentTimeMillis() - t0);
        } catch (Exception e) {
            LOG.warn("blueprint catalogue of {} failed: {}", dir, e.toString());
        }
    }

    /** The block's colour on a map, or a guess by name (glass and other see-through blocks have none). */
    static int color(BlockSpec spec) {
        return colors.computeIfAbsent(spec, s -> {
            try {
                BlockState st = BlockStateParser.parseForBlock(Mc.blocks(), s.toString(), false).blockState();
                MapColor c = st.getMapColor(EmptyBlockGetter.INSTANCE, BlockPos.ZERO);
                return c == null || c == MapColor.NONE ? Picture.guessColor(s) : c.col;
            } catch (Exception e) {
                return Picture.guessColor(s);
            }
        });
    }
}
