package dev.kindredspirit.act;

import com.google.gson.JsonObject;
import dev.kindredspirit.KindredSpiritClient;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Locale;

/**
 * Building with you: she places blocks in a shape you asked for, one at a time, floating to each
 * spot, a few per second. In grounded style each block comes out of your inventory (she places
 * what you have and says how far it went); in magic style or creative they're free. Never inside
 * you or an animal, never over something solid; only within reach of where you stand.
 */
public final class Builder {
    private Builder() {}

    private static final int EVERY_TICKS = 3; // ~6-7 blocks a second
    private static final Deque<BlockPos> queue = new ArrayDeque<>();
    private static Item item;
    private static boolean free;
    private static int tick, placed, skipped;

    /** Starts a build. Called on the server thread. */
    static JsonObject start(MinecraftServer server, LocalPlayer p, JsonObject args, Abilities.Style style) {
        ServerPlayer sp = Actions.serverPlayer(server, p);
        String shapeName = Actions.str(args, "shape", "pillar");
        if (shapeName.equalsIgnoreCase("stop")) {
            int left = queue.size();
            queue.clear();
            JsonObject r = Actions.ok();
            r.addProperty("stopped", true);
            r.addProperty("placed", placed);
            r.addProperty("notPlaced", left);
            return r;
        }
        BuildPlan.Shape shape = BuildPlan.Shape.of(shapeName);
        if (shape == null) return Actions.error("I can build a pillar, corners (a pillar on each corner), a wall, a floor or an outline.");
        Item what = blockItem(sp, Actions.str(args, "block", ""));
        if (what == null) return Actions.error("Which block? Hold the block you want in your hand, or name one you have.");

        // where: on the block the player is looking at (within 8 blocks), else just in front of them
        BlockPos origin;
        HitResult hit = sp.pick(8, 1f, false);
        if (hit instanceof BlockHitResult bh && hit.getType() == HitResult.Type.BLOCK) {
            BlockPos at = bh.getBlockPos();
            // grass or snow there: build in its place; a solid block: on the face you're looking at
            origin = sp.serverLevel().getBlockState(at).canBeReplaced() ? at : at.relative(bh.getDirection());
        } else {
            origin = sp.blockPosition().relative(sp.getDirection(), 2);
        }
        Direction f = sp.getDirection();
        List<int[]> cells = BuildPlan.positions(shape, origin.getX(), origin.getY(), origin.getZ(),
                f.getStepX(), f.getStepZ(), Actions.num(args, "width", shape == BuildPlan.Shape.PILLAR ? 1 : 5),
                Actions.num(args, "length", shape == BuildPlan.Shape.WALL || shape == BuildPlan.Shape.PILLAR ? 1 : 5),
                Actions.num(args, "height", shape == BuildPlan.Shape.FLOOR ? 1 : 3));

        boolean isFree = style == Abilities.Style.MAGIC || sp.getAbilities().instabuild;
        int have = isFree ? Integer.MAX_VALUE : count(sp, what);
        if (have == 0) return Actions.error("You don't have any " + name(what) + ". I can only build with what you have.");
        queue.clear();
        for (int[] c : cells) queue.add(new BlockPos(c[0], c[1], c[2]));
        item = what;
        free = isFree;
        placed = skipped = 0;
        tick = 0;
        JsonObject r = Actions.ok();
        r.addProperty("building", shape.name().toLowerCase(Locale.ROOT));
        r.addProperty("block", name(what));
        r.addProperty("blocks", cells.size());
        if (!isFree && have < cells.size()) {
            r.addProperty("youHaveOnly", have);
            r.addProperty("note", "There's only enough for " + have + " of the " + cells.size() + " blocks: I'll place those.");
        }
        r.addProperty("seconds", Math.round(Math.min(cells.size(), have) * EVERY_TICKS / 20.0));
        r.addProperty("startsAt", origin.getX() + " " + origin.getY() + " " + origin.getZ());
        return r;
    }

    /** Every server tick: the next block, now and then. */
    public static void tick(MinecraftServer server) {
        if (queue.isEmpty() || ++tick % EVERY_TICKS != 0) return;
        Minecraft mc = Minecraft.getInstance();
        if (mc.player == null) {
            queue.clear();
            return;
        }
        ServerPlayer sp = server.getPlayerList().getPlayer(mc.player.getUUID());
        if (sp == null) {
            queue.clear();
            return;
        }
        ServerLevel level = sp.serverLevel();
        while (!queue.isEmpty()) {
            BlockPos at = queue.poll();
            BlockState here = level.getBlockState(at);
            boolean someoneThere = !level.getEntitiesOfClass(LivingEntity.class, new AABB(at)).isEmpty();
            if (!here.canBeReplaced() || someoneThere || at.distSqr(sp.blockPosition()) > 32 * 32) {
                skipped++;
                continue; // solid already, or you / an animal is there, or too far: next one
            }
            if (!free && !take(sp, item)) {
                queue.clear(); // out of blocks
                return;
            }
            BlockState state = ((BlockItem) item).getBlock().defaultBlockState();
            level.setBlockAndUpdate(at, state);
            level.playSound(null, at, state.getSoundType().getPlaceSound(), SoundSource.BLOCKS, 0.8f, 1.1f);
            placed++;
            double x = at.getX() + 0.5, y = at.getY() + 1.3, z = at.getZ() + 0.5;
            mc.execute(() -> KindredSpiritClient.get().companion().life.visit(x, y, z, 1.2,
                    System.nanoTime() / 1e9)); // she floats to each block as it appears
            return;
        }
    }

    public static boolean busy() {
        return !queue.isEmpty();
    }

    private static Item blockItem(ServerPlayer sp, String wanted) {
        ItemStack hand = sp.getMainHandItem();
        if (wanted.isBlank() || wanted.equalsIgnoreCase("hand") || wanted.equalsIgnoreCase("held")) {
            return hand.getItem() instanceof BlockItem ? hand.getItem() : mostBlocks(sp);
        }
        String id = wanted.trim().toLowerCase(Locale.ROOT).replace(' ', '_');
        ResourceLocation key = ResourceLocation.tryParse(id.contains(":") ? id : "minecraft:" + id);
        Item it = key == null ? null : BuiltInRegistries.ITEM.getOptional(key).orElse(null);
        if (it instanceof BlockItem) return it;
        // "stone" when they hold cobblestone, "wood" when they have planks...: a block item they have whose name contains it
        for (ItemStack s : sp.getInventory().items) {
            if (s.getItem() instanceof BlockItem && BuiltInRegistries.ITEM.getKey(s.getItem()).getPath().contains(id)) {
                return s.getItem();
            }
        }
        return null;
    }

    private static Item mostBlocks(ServerPlayer sp) {
        java.util.Map<Item, Integer> n = new java.util.HashMap<>();
        for (ItemStack s : sp.getInventory().items) if (s.getItem() instanceof BlockItem) n.merge(s.getItem(), s.getCount(), Integer::sum);
        return n.entrySet().stream().max(java.util.Map.Entry.comparingByValue()).map(java.util.Map.Entry::getKey).orElse(null);
    }

    private static int count(ServerPlayer sp, Item it) {
        int n = 0;
        for (ItemStack s : sp.getInventory().items) if (s.is(it)) n += s.getCount();
        return n;
    }

    private static boolean take(ServerPlayer sp, Item it) {
        for (ItemStack s : sp.getInventory().items) {
            if (s.is(it)) {
                s.shrink(1);
                return true;
            }
        }
        return false;
    }

    private static String name(Item it) {
        return BuiltInRegistries.ITEM.getKey(it).getPath().replace('_', ' ');
    }
}
