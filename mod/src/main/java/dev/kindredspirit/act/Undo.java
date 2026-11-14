package dev.kindredspirit.act;

import com.google.gson.JsonObject;
import dev.kindredspirit.util.Mc;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.UUID;

/**
 * Undoing her builds and flattening (#129): {@link Builder} and {@link BlueprintBuild} call {@link #begin} when a build
 * starts and {@link #record} before each spot changes; "undo that" puts the newest build back as it was, a few
 * thousand blocks a tick. Kept in memory while the world is open, never in its save. A container she built that you
 * filled drops its contents first; in grounded style the blocks she placed come back to your pockets.
 */
public final class Undo {
    private Undo() {}

    static final UndoLog<BlockState> LOG = new UndoLog<>();
    static final int PER_TICK = 4000;
    // (no neighbour updates, no drops: the old block goes back exactly, a torch on it doesn't pop off)
    private static final int QUIET = 2 | 16 | 32;

    private static final Deque<Map.Entry<Long, BlockState>> restoring = new ArrayDeque<>();
    private static UUID owner;
    private static boolean giveBack;
    private static String restoringName = "";

    static void begin(String name, ServerLevel level, boolean magic) {
        LOG.begin(name, level.dimension().toString(), magic);
    }

    /** Before a spot changes: it, and its neighbours (a bed's other half, a door's top, a torch beside it). */
    static void record(ServerLevel level, BlockPos at) {
        recordOnly(level, at);
        for (Direction d : Direction.values()) recordOnly(level, at.relative(d));
    }

    static void recordOnly(ServerLevel level, BlockPos at) {
        LOG.before(at.asLong(), level.getBlockState(at));
    }

    public static boolean busy() {
        return !restoring.isEmpty();
    }

    /** "Undo that": the newest build goes back (stopping one in progress first). */
    static JsonObject undo(MinecraftServer server, ServerPlayer sp) {
        if (Builder.busy()) Builder.stop();
        if (BlueprintBuild.busy()) BlueprintBuild.stop();
        if (busy()) return Actions.error("I'm still putting the " + restoringName + " back.");
        UndoLog.Edit<BlockState> e = LOG.pop();
        if (e == null) return Actions.error("There's nothing of mine to undo here (I remember my builds until the world closes).");
        if (e.tooBig()) return Actions.error("The " + e.name + " was too big for me to remember, so I can't undo it.");
        if (!e.dimension.equals(Mc.level(sp).dimension().toString())) {
            return Actions.error("The " + e.name + " is in another dimension: go there and ask me again.");
        }
        restoring.addAll(e.newestFirst());
        owner = sp.getUUID();
        giveBack = !e.magic;
        restoringName = e.name;
        JsonObject r = Actions.ok();
        r.addProperty("undoing", e.name);
        r.addProperty("blocks", e.before.size());
        r.addProperty("seconds", Math.max(1, e.before.size() / PER_TICK / 20));
        return r;
    }

    /** Every server tick: put the next blocks back. */
    public static void tick(MinecraftServer server) {
        if (restoring.isEmpty()) return;
        ServerPlayer sp = owner == null ? null : server.getPlayerList().getPlayer(owner);
        if (sp == null) {
            restoring.clear();
            return;
        }
        ServerLevel level = Mc.level(sp);
        for (int n = 0; n < PER_TICK && !restoring.isEmpty(); n++) {
            Map.Entry<Long, BlockState> e = restoring.poll();
            BlockPos at = BlockPos.of(e.getKey());
            BlockState now = level.getBlockState(at);
            if (now == e.getValue()) continue;
            if (level.getBlockEntity(at) instanceof net.minecraft.world.Container c) {
                net.minecraft.world.Containers.dropContents(level, at, c); // (what you put in her chest isn't lost)
            }
            if (giveBack && !now.isAir() && e.getValue().canBeReplaced()) {
                for (ItemStack drop : Block.getDrops(now, level, at, level.getBlockEntity(at))) Mc.give(sp, drop);
            }
            level.removeBlockEntity(at);
            level.setBlock(at, e.getValue(), QUIET);
        }
    }

    /** The world closes: nothing to undo any more (her memory of builds is per world session). */
    public static void clear() {
        LOG.clear();
        restoring.clear();
    }
}
