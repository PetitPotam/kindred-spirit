package dev.kindredspirit.act;

import com.google.gson.JsonObject;
import dev.kindredspirit.KindredSpiritClient;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

/**
 * Building with you: she places (or clears) blocks in a shape you asked for, floating to each spot.
 * Blocks are placed the way a player places them (a bed gets both halves, a campfire, a door, a log
 * on its end), never inside you or an animal, never over something solid. In grounded style each
 * block comes out of the inventory of whoever asked (she places what they have) and what she clears
 * goes into it; in magic style or creative they're free and it goes much faster.
 */
public final class Builder {
    private Builder() {}

    private static final int GROUNDED_EVERY = 2;   // grounded: a block every 2 ticks (10 a second)
    private static final int MAGIC_PER_TICK = 6;   // magic or creative: 6 a tick (about 120 a second)
    private static final Deque<BuildPlan.Step> queue = new ArrayDeque<>();
    private static Item item;
    private static boolean free;
    private static Abilities.Style style = Abilities.Style.GROUNDED;
    private static UUID owner; // who asked: their inventory, their reach (a visiting Pip builds for her owner)
    private static int tick, placed, cleared, skipped;

    /** Starts a build. Called on the server thread. */
    static JsonObject start(MinecraftServer server, ServerPlayer sp, JsonObject args, Abilities.Style st) {
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
        if (shape == null) {
            return Actions.error("I can't build a " + shapeName.replace('_', ' ') + " (yet). I can do " + BuildPlan.KNOWN + ".");
        }
        boolean isFree = st == Abilities.Style.MAGIC || sp.getAbilities().instabuild;
        String wanted = Actions.str(args, "block", "");
        Item what = null;
        if (shape == BuildPlan.Shape.PORTAL) {
            what = Items.OBSIDIAN;
        } else if (!shape.clears() || shape == BuildPlan.Shape.FLATTEN) {
            what = blockItem(sp, wanted, isFree);
            if (what == null && shape == BuildPlan.Shape.FLATTEN && wanted.isBlank()) what = isFree ? Items.DIRT : mostBlocks(sp);
            if (what == null) {
                return Actions.error(wanted.isBlank() ? "Which block? Hold the block you want in your hand, or name one."
                        : isFree ? "There's no block called " + wanted + "." : "You don't have any " + wanted.replace('_', ' ') + ".");
            }
        }

        // where: on the block the player is looking at (within 8 blocks), else just in front of them
        BlockPos origin;
        HitResult hit = sp.pick(8, 1f, false);
        if (hit instanceof BlockHitResult bh && hit.getType() == HitResult.Type.BLOCK) {
            BlockPos at = bh.getBlockPos();
            if (shape.clears()) origin = at; // (clearing starts with the block you look at)
            else origin = sp.serverLevel().getBlockState(at).canBeReplaced() ? at : at.relative(bh.getDirection());
        } else {
            origin = sp.blockPosition().relative(sp.getDirection(), 2);
        }
        if (shape.clears()) { // an area around where they look: they stand in the middle of its near edge
            int w = Actions.num(args, "width", 8);
            Direction f = sp.getDirection();
            origin = new BlockPos(sp.blockPosition().getX(), origin.getY(), sp.blockPosition().getZ())
                    .relative(f.getCounterClockWise(), w / 2);
        }
        Direction f = sp.getDirection();
        // clearing: everything from where they stand up (or above the level they name: "above Y 64")
        int level = args.has("level") ? Actions.num(args, "level", 0) : shape.clears() ? sp.getBlockY() - 1 : Integer.MIN_VALUE;
        List<BuildPlan.Step> steps = BuildPlan.steps(shape, origin.getX(), origin.getY(), origin.getZ(),
                f.getStepX(), f.getStepZ(),
                Actions.num(args, "width", shape == BuildPlan.Shape.PILLAR ? 1 : shape == BuildPlan.Shape.HOUSE ? 0 : 5),
                Actions.num(args, "length", shape == BuildPlan.Shape.WALL || shape == BuildPlan.Shape.PILLAR ? 1
                        : shape == BuildPlan.Shape.HOUSE ? 0 : 5),
                Actions.num(args, "height", shape == BuildPlan.Shape.FLOOR ? 1 : shape == BuildPlan.Shape.HOUSE ? 0 : 3),
                Actions.num(args, "people", 2), level);

        long needed = steps.stream().filter(s -> s.kind() == 'B' || s.kind() == 'F' || s.kind() == 'P').count();
        int have = isFree || what == null ? Integer.MAX_VALUE : count(sp, what);
        if (needed > 0 && have == 0) {
            return Actions.error("You don't have any " + name(what) + ". I can only build with what you have"
                    + (shape == BuildPlan.Shape.PORTAL ? " (a portal needs 10 obsidian)." : "."));
        }
        queue.clear();
        queue.addAll(steps);
        item = what;
        free = isFree;
        style = st;
        owner = sp.getUUID();
        placed = cleared = skipped = 0;
        tick = 0;
        JsonObject r = Actions.ok();
        r.addProperty("building", shape.name().toLowerCase(Locale.ROOT));
        if (what != null) r.addProperty("block", name(what));
        if (shape.clears()) r.addProperty("clearing", "up to " + steps.stream().filter(s -> s.kind() == 'X').count() + " blocks");
        if (needed > 0) r.addProperty("blocks", needed);
        if (!isFree && needed > 0 && have < needed) {
            r.addProperty("youHaveOnly", have);
            r.addProperty("note", "There's only enough for " + have + " of the " + needed + " blocks: I'll place those.");
        }
        if (shape == BuildPlan.Shape.PORTAL && !isFree && !hasLighter(sp)) {
            r.addProperty("note", "The frame, yes; to light it, the player needs flint and steel or a fire charge.");
        }
        if (shape == BuildPlan.Shape.HOUSE) r.addProperty("door", isFree || hasDoor(sp) ? "a door" : "a doorway (no door in your pockets)");
        double perSecond = isFree ? MAGIC_PER_TICK * 20.0 : 20.0 / GROUNDED_EVERY;
        r.addProperty("seconds", Math.max(1, Math.round(steps.size() / perSecond)));
        r.addProperty("startsAt", origin.getX() + " " + origin.getY() + " " + origin.getZ());
        return r;
    }

    /** Every server tick: the next blocks. */
    public static void tick(MinecraftServer server) {
        if (queue.isEmpty()) return;
        if (!free && ++tick % GROUNDED_EVERY != 0) return;
        ServerPlayer sp = owner == null ? null : server.getPlayerList().getPlayer(owner);
        if (sp == null) {
            queue.clear();
            return;
        }
        ServerLevel level = sp.serverLevel();
        int budget = free ? MAGIC_PER_TICK : 1;
        BlockPos last = null;
        while (!queue.isEmpty() && budget > 0) {
            BuildPlan.Step s = queue.poll();
            BlockPos at = new BlockPos(s.x(), s.y(), s.z());
            if (at.distSqr(sp.blockPosition()) > 40 * 40) {
                skipped++;
                continue;
            }
            boolean did = switch (s.kind()) {
                case 'X' -> clear(level, sp, at);
                case 'D' -> door(level, sp, at);
                case 'L' -> light(level, sp, at);
                default -> place(level, sp, at, s);
            };
            if (did) {
                budget--;
                last = at;
            } else if (!free && item != null && s.kind() != 'X' && count(sp, item) == 0) {
                queue.removeIf(x -> x.kind() == 'B' || x.kind() == 'F' || x.kind() == 'P'); // out of blocks
            }
        }
        if (last != null && Minecraft.getInstance().player != null && owner.equals(Minecraft.getInstance().player.getUUID())) {
            double x = last.getX() + 0.5, y = last.getY() + 1.3, z = last.getZ() + 0.5;
            Minecraft.getInstance().execute(() -> KindredSpiritClient.get().companion().life.visit(x, y, z, 1.2,
                    System.nanoTime() / 1e9)); // she floats to each block as it appears
        }
    }

    /** One block, placed as a player places it (both halves of a bed, a door, a campfire facing you). */
    private static boolean place(ServerLevel level, ServerPlayer sp, BlockPos at, BuildPlan.Step s) {
        Item it = s.block() != null ? itemOf(s.block()) : item;
        if (!(it instanceof BlockItem bi)) return false;
        BlockState here = level.getBlockState(at);
        if (!here.canBeReplaced() || !level.getEntitiesOfClass(LivingEntity.class, new AABB(at)).isEmpty()) {
            skipped++;
            return false; // solid already, or you / an animal is there: next one
        }
        if (!free && count(sp, it) == 0) return false;
        ItemStack one = new ItemStack(it, 1);
        BlockHitResult aim = new BlockHitResult(Vec3.atCenterOf(at), Direction.UP, at, false);
        var result = bi.place(new BlockPlaceContext(level, sp, InteractionHand.MAIN_HAND, one, aim));
        if (!result.consumesAction()) { // (a bed with no room for its head, a door with nothing under it...)
            skipped++;
            return false;
        }
        if (!free) take(sp, it);
        placed++;
        return true;
    }

    /** What's there goes: into the asker's pockets (grounded), or just gone (magic). Never unbreakable
     *  blocks, never things that hold items, never water or lava. */
    private static boolean clear(ServerLevel level, ServerPlayer sp, BlockPos at) {
        BlockState st = level.getBlockState(at);
        if (st.isAir() || !st.getFluidState().isEmpty() || st.getDestroySpeed(level, at) < 0 || level.getBlockEntity(at) != null) {
            return false;
        }
        if (!free) {
            for (ItemStack drop : Block.getDrops(st, level, at, null, sp, sp.getMainHandItem())) {
                if (!sp.getInventory().add(drop)) sp.drop(drop, false);
            }
        }
        level.destroyBlock(at, false, sp);
        cleared++;
        return true;
    }

    private static boolean door(ServerLevel level, ServerPlayer sp, BlockPos at) {
        clear(level, sp, at);
        Item d = free ? Items.OAK_DOOR : doorItem(sp);
        if (d == null) return true; // a doorway, then
        ItemStack one = new ItemStack(d, 1);
        var result = ((BlockItem) d).place(new BlockPlaceContext(level, sp, InteractionHand.MAIN_HAND, one,
                new BlockHitResult(Vec3.atCenterOf(at), Direction.UP, at, false)));
        if (result.consumesAction() && !free) take(sp, d);
        return true;
    }

    /** A portal frame: fire inside it, and the portal fills it (grounded: with their flint and steel). */
    private static boolean light(ServerLevel level, ServerPlayer sp, BlockPos at) {
        if (!level.getBlockState(at).isAir()) return false;
        if (!free) {
            ItemStack lighter = null;
            for (ItemStack s : sp.getInventory().items) if (s.is(Items.FLINT_AND_STEEL) || s.is(Items.FIRE_CHARGE)) lighter = s;
            if (lighter == null) return false;
            if (lighter.is(Items.FIRE_CHARGE)) lighter.shrink(1);
            else lighter.hurtAndBreak(1, sp, net.minecraft.world.entity.EquipmentSlot.MAINHAND);
        }
        level.setBlockAndUpdate(at, Blocks.FIRE.defaultBlockState()); // (fire in a frame makes the portal)
        level.playSound(null, at, net.minecraft.sounds.SoundEvents.FLINTANDSTEEL_USE, SoundSource.BLOCKS, 1f, 1f);
        return true;
    }

    public static boolean busy() {
        return !queue.isEmpty();
    }

    private static Item blockItem(ServerPlayer sp, String wanted, boolean free) {
        ItemStack hand = sp.getMainHandItem();
        if (wanted.isBlank() || wanted.equalsIgnoreCase("hand") || wanted.equalsIgnoreCase("held")) {
            return hand.getItem() instanceof BlockItem ? hand.getItem() : mostBlocks(sp);
        }
        String id = wanted.trim().toLowerCase(Locale.ROOT).replace(' ', '_');
        Item it = itemOf(id);
        if (it instanceof BlockItem && (free || count(sp, it) > 0)) return it;
        // "stone" when they hold cobblestone, "wood" when they have planks...: a block item they have whose name contains it
        for (ItemStack s : sp.getInventory().items) {
            if (s.getItem() instanceof BlockItem && BuiltInRegistries.ITEM.getKey(s.getItem()).getPath().contains(id)) {
                return s.getItem();
            }
        }
        return it instanceof BlockItem ? it : null;
    }

    private static Item itemOf(String id) {
        ResourceLocation key = ResourceLocation.tryParse(id.contains(":") ? id : "minecraft:" + id);
        return key == null ? null : BuiltInRegistries.ITEM.getOptional(key).orElse(null);
    }

    private static Item mostBlocks(ServerPlayer sp) {
        java.util.Map<Item, Integer> n = new java.util.HashMap<>();
        for (ItemStack s : sp.getInventory().items) if (s.getItem() instanceof BlockItem) n.merge(s.getItem(), s.getCount(), Integer::sum);
        return n.entrySet().stream().max(java.util.Map.Entry.comparingByValue()).map(java.util.Map.Entry::getKey).orElse(null);
    }

    private static Item doorItem(ServerPlayer sp) {
        for (ItemStack s : sp.getInventory().items) {
            if (s.getItem() instanceof net.minecraft.world.item.DoubleHighBlockItem && s.is(net.minecraft.tags.ItemTags.DOORS)) {
                return s.getItem();
            }
        }
        return null;
    }

    private static boolean hasDoor(ServerPlayer sp) {
        return doorItem(sp) != null;
    }

    private static boolean hasLighter(ServerPlayer sp) {
        for (ItemStack s : sp.getInventory().items) if (s.is(Items.FLINT_AND_STEEL) || s.is(Items.FIRE_CHARGE)) return true;
        return false;
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
