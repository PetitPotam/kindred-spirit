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
@SuppressWarnings("unchecked")
public final class Glow {
    private Glow() {}

    private static final org.slf4j.Logger LOG = org.slf4j.LoggerFactory.getLogger("kindredspirit");
    private static BlockPos lit;
    private static boolean wasDark;
    private static ResourceKey<Level> litDim;

    /** Asked to glow brighter ("light the way"): until then, level 15 and on even where it isn't dark. */
    public static volatile long brightUntil;
    /** Asked to stop glowing: until then, off. */
    public static volatile long offUntil;
    /** In a friend's world: her light is placed by their game (set by the client when visiting). */
    public static volatile java.util.function.BiConsumer<BlockPos, Integer> remote;

    /** Called every few game ticks on the client thread. */
    public static void tick(Minecraft mc, boolean wanted, double x, double y, double z) {
        MinecraftServer server = mc.getSingleplayerServer();
        if (mc.level == null || mc.player == null) return;
        if (server == null && remote == null) return;
        BlockPos here = BlockPos.containing(x, y, z);
        long now = System.currentTimeMillis();
        boolean bright = now < brightUntil;
        // dark: the brighter of the sky (night, caves, under a roof) and lamps or torches is below 7. Her own light never
        // counts: once she's lit, only daylight or a real lamp near you (block light 13+, hers gives at most 11 there)
        // turns her off, so she doesn't flicker on her own light
        ServerLevel sl = server != null ? server.getLevel(mc.level.dimension()) : null;
        long tod = mc.level.getDayTime() % 24000;
        int skyDarken = sl != null ? sl.getSkyDarken() : (tod > 13000 && tod < 23000 ? 11 : 0); // (visiting: from the clock)
        int sky = mc.level.getBrightness(LightLayer.SKY, here) - skyDarken;
        boolean dark = wasDark
                ? sky < 7 && mc.level.getBrightness(LightLayer.BLOCK, mc.player.blockPosition()) < 13
                : Math.max(sky, mc.level.getBrightness(LightLayer.BLOCK, here)) < 7;
        int block = mc.level.getBrightness(LightLayer.BLOCK, here);
        if (dark != wasDark) {
            wasDark = dark;
            LOG.info("glow: {} (sky {} block {} at her spot)", dark ? "dark, she lights up" : "light enough", sky, block);
        }
        BlockPos want = wanted && now >= offUntil && (dark || bright) ? here : null;
        int level = bright ? 15 : 12;
        if (Objects.equals(want, lit) && level == litLevel) return;
        BlockPos old = lit;
        ResourceKey<Level> oldDim = litDim, dim = mc.level.dimension();
        lit = want;
        litDim = dim;
        litLevel = level;
        if (server == null) { // visiting: their game places it (and takes the old one away)
            remote.accept(want, level);
            return;
        }
        server.execute(() -> {
            unlight(server, oldDim, old);
            ServerLevel l = server.getLevel(dim);
            if (want != null && l != null && l.isLoaded(want) && l.getBlockState(want).isAir()) {
                l.setBlock(want, Blocks.LIGHT.defaultBlockState().setValue(LightBlock.LEVEL, level), 3);
            }
        });
    }

    private static int litLevel = 12;
    /** Light blocks placed in this world for visiting Pips (owner -> where), so each moves and is cleaned up. */
    private static final java.util.Map<java.util.UUID, Object[]> visitors = new java.util.concurrent.ConcurrentHashMap<>();

    /** On the host's server thread: a visiting Pip's light, where she floats now (or none). */
    public static void visitorLight(MinecraftServer server, net.minecraft.server.level.ServerPlayer owner, BlockPos at, int level) {
        Object[] old = visitors.remove(owner.getUUID());
        if (old != null) unlight(server, (ResourceKey<Level>) old[0], (BlockPos) old[1]);
        ServerLevel l = owner.serverLevel();
        if (at == null || !l.isLoaded(at) || !l.getBlockState(at).isAir() || at.distSqr(owner.blockPosition()) > 16 * 16) return;
        l.setBlock(at, Blocks.LIGHT.defaultBlockState().setValue(LightBlock.LEVEL, Math.max(1, Math.min(15, level))), 3);
        visitors.put(owner.getUUID(), new Object[]{l.dimension(), at});
    }

    /** On the server thread, as the world stops: take the light away so it isn't saved. */
    public static void clearNow(MinecraftServer server) {
        unlight(server, litDim, lit);
        lit = null;
        for (Object[] v : visitors.values()) unlight(server, (ResourceKey<Level>) v[0], (BlockPos) v[1]);
        visitors.clear();
    }

    private static void unlight(MinecraftServer server, ResourceKey<Level> dim, BlockPos pos) {
        if (pos == null || dim == null) return;
        ServerLevel l = server.getLevel(dim);
        if (l != null && l.isLoaded(pos) && l.getBlockState(pos).is(Blocks.LIGHT)) {
            l.setBlock(pos, Blocks.AIR.defaultBlockState(), 3);
        }
    }
}
