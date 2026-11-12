package dev.kindredspirit.act;

import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.LightLayer;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.LightBlock;

import java.util.Objects;

/**
 * Her glow lights the dark (singleplayer, setting {@code glow}): where she floats, an invisible
 * light block (the game's own "light" block, level 12) that moves with her. Only ever placed in
 * air, only ever removed if it is still that light block, and cleared when she moves on, when the
 * glow is turned off, and when the world closes, so nothing is left behind in your world.
 *
 * "Dark" is judged from the sky light at her spot (night, caves, under a roof), which her own light
 * doesn't change, so it never flickers on and off.
 */
public final class Glow {
    private Glow() {}

    private static final org.slf4j.Logger LOG = org.slf4j.LoggerFactory.getLogger("kindredspirit");
    private static BlockPos lit;
    private static boolean wasDark;
    private static ResourceKey<Level> litDim;

    /** Called every few game ticks on the client thread. */
    public static void tick(Minecraft mc, boolean wanted, double x, double y, double z) {
        MinecraftServer server = mc.getSingleplayerServer();
        if (server == null || mc.level == null) return;
        BlockPos here = BlockPos.containing(x, y, z);
        // (the sky's darkening is only kept up to date on the server side, not in the client's level)
        ServerLevel sl = server.getLevel(mc.level.dimension());
        int sky = mc.level.getBrightness(LightLayer.SKY, here) - (sl != null ? sl.getSkyDarken() : 0);
        boolean dark = sky < 7;
        if (dark != wasDark) {
            wasDark = dark;
            LOG.info("glow: {} (sky light {} at her spot)", dark ? "dark, she lights up" : "light enough", sky);
        }
        BlockPos want = wanted && dark ? here : null;
        if (Objects.equals(want, lit)) return;
        BlockPos old = lit;
        ResourceKey<Level> oldDim = litDim, dim = mc.level.dimension();
        lit = want;
        litDim = dim;
        server.execute(() -> {
            unlight(server, oldDim, old);
            ServerLevel l = server.getLevel(dim);
            if (want != null && l != null && l.isLoaded(want) && l.getBlockState(want).isAir()) {
                l.setBlock(want, Blocks.LIGHT.defaultBlockState().setValue(LightBlock.LEVEL, 12), 3);
            }
        });
    }

    /** On the server thread, as the world stops: take the light away so it isn't saved. */
    public static void clearNow(MinecraftServer server) {
        unlight(server, litDim, lit);
        lit = null;
    }

    private static void unlight(MinecraftServer server, ResourceKey<Level> dim, BlockPos pos) {
        if (pos == null || dim == null) return;
        ServerLevel l = server.getLevel(dim);
        if (l != null && l.isLoaded(pos) && l.getBlockState(pos).is(Blocks.LIGHT)) {
            l.setBlock(pos, Blocks.AIR.defaultBlockState(), 3);
        }
    }
}
