package dev.kindredspirit.job;

import com.mojang.authlib.GameProfile;
import net.fabricmc.fabric.api.entity.FakePlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.context.UseOnContext;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;

import java.util.List;

/**
 * Her hands for grounded work: a server-side stand-in player (Fabric API's {@link FakePlayer}: never
 * shown, never in the player list, not ticked) that breaks and places exactly as the player would,
 * with the player's own tool. So the game's rules apply by themselves: how long a block takes with
 * that pickaxe, whether it drops anything, Fortune and Silk Touch, the tool wearing, and every mod
 * or claim that protects blocks from players (Fabric's block-break events fire). Her body stays the
 * floating spirit drawn on your screen; nothing new appears in the world.
 *
 * <p>The stand-in uses the owner's UUID with its own name, as Fabric recommends, so protection mods
 * treat her work as the owner's.
 */
public final class Hands {
    private Hands() {}

    static FakePlayer of(ServerPlayer owner) {
        ServerLevel level = owner.serverLevel();
        FakePlayer fp = FakePlayer.get(level, new GameProfile(owner.getUUID(), "[Pip]"));
        fp.moveTo(owner.getX(), owner.getY(), owner.getZ(), owner.getYRot(), owner.getXRot());
        // never ticked, so the game would think it's falling: mining is 5x slower off the ground.
        // Her hands stand where the player stands, as the player stands.
        fp.setOnGround(owner.onGround());
        return fp;
    }

    /** Ticks it takes to break a block with this tool, as for the player (at least 1; -1: never). */
    public static int breakTicks(ServerPlayer owner, BlockPos at, ItemStack tool) {
        FakePlayer fp = of(owner);
        BlockState st = owner.serverLevel().getBlockState(at);
        fp.setItemInHand(InteractionHand.MAIN_HAND, tool);
        try {
            float perTick = st.getDestroyProgress(fp, owner.serverLevel(), at);
            if (perTick <= 0) return -1;
            return Math.max(1, (int) Math.ceil(1.0f / perTick));
        } finally {
            fp.setItemInHand(InteractionHand.MAIN_HAND, ItemStack.EMPTY);
        }
    }

    /** Shows the cracks while she works on a block (stage 0-9, or -1 to clear). */
    public static void cracks(ServerPlayer owner, BlockPos at, int stage) {
        owner.serverLevel().destroyBlockProgress(of(owner).getId(), at, stage);
    }

    /**
     * Breaks a block as the player would with {@code tool} (the real stack from their hand: it wears),
     * then puts what dropped into the owner's pockets. False if the game refused (protected, adventure
     * mode, unbreakable).
     */
    public static boolean breakBlock(ServerPlayer owner, BlockPos at, ItemStack tool, java.util.Map<String, Integer> got) {
        ServerLevel level = owner.serverLevel();
        FakePlayer fp = of(owner);
        fp.setItemInHand(InteractionHand.MAIN_HAND, tool);
        boolean ok;
        try {
            ok = fp.gameMode.destroyBlock(at);
        } finally {
            fp.setItemInHand(InteractionHand.MAIN_HAND, ItemStack.EMPTY);
            level.destroyBlockProgress(fp.getId(), at, -1);
        }
        if (ok) pocket(owner, new AABB(at).inflate(1.0), got);
        return ok;
    }

    /** Places (or uses) the stack on a block face, as a right click by the player would. */
    public static boolean useOn(ServerPlayer owner, BlockPos against, Direction face, ItemStack stack) {
        FakePlayer fp = of(owner);
        fp.setItemInHand(InteractionHand.MAIN_HAND, stack);
        try {
            Vec3 hit = Vec3.atCenterOf(against).add(face.getStepX() * 0.5, face.getStepY() * 0.5, face.getStepZ() * 0.5);
            InteractionResult r = stack.useOn(new UseOnContext(fp, InteractionHand.MAIN_HAND,
                    new BlockHitResult(hit, face, against, false)));
            return r.consumesAction();
        } finally {
            fp.setItemInHand(InteractionHand.MAIN_HAND, ItemStack.EMPTY);
        }
    }

    /** Moves fresh drops near a spot into the owner's pockets (what doesn't fit stays on the ground). */
    static void pocket(ServerPlayer owner, AABB where, java.util.Map<String, Integer> got) {
        List<ItemEntity> drops = owner.serverLevel().getEntitiesOfClass(ItemEntity.class, where,
                e -> e.isAlive() && e.getAge() < 20);
        for (ItemEntity e : drops) {
            ItemStack stack = e.getItem().copy();
            int before = stack.getCount();
            String name = net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(stack.getItem()).getPath();
            owner.getInventory().add(stack);
            int moved = before - stack.getCount();
            if (moved > 0 && got != null) got.merge(name, moved, Integer::sum);
            if (stack.isEmpty()) e.discard();
            else e.setItem(stack);
        }
    }
}
