package dev.kindredspirit.act;

import com.google.gson.JsonObject;
import dev.kindredspirit.KindredSpiritClient;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.tags.BlockTags;
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
    private static boolean flattening; // (never clears what someone built, leaves water alone, faster with magic)
    private static Abilities.Style style = Abilities.Style.GROUNDED;
    private static UUID owner; // who asked: their inventory, their reach (a visiting Pip builds for her owner)
    private static int tick, placed, cleared, skipped;
    private static String doing = "";  // "building a farm" (the snapshot, the HUD)
    private static int total;
    private static int[] lastMiddle; // the middle of what she built last, on top ("the bell in the middle of the farm")

    /** Starts a build. Called on the server thread. */
    static JsonObject start(MinecraftServer server, ServerPlayer sp, JsonObject args, Abilities.Style st) {
        String shapeName = Actions.str(args, "shape", "pillar");
        if (shapeName.equalsIgnoreCase("stop")) {
            // "stop" stops all her work: a job (mining, chopping...) and a blueprint build too
            if (dev.kindredspirit.job.Jobs.busy()) dev.kindredspirit.job.Jobs.stop();
            if (BlueprintBuild.busy()) BlueprintBuild.stop();
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
        if (shape == BuildPlan.Shape.END_PORTAL && !isFree) {
            return Actions.error("End portal frames can't be crafted or picked up: only with magic (or find the one in a stronghold, and I'll help you look).");
        }
        if (shape == BuildPlan.Shape.FARM) {
            what = crop(wanted.isBlank() ? "wheat" : wanted);
            if (what == null) return Actions.error("Which crop? Wheat, carrots, potatoes or beetroots.");
            if (!isFree && count(sp, what) == 0) {
                return Actions.error("You don't have any " + name(what) + " to plant. I can till the ground once you do.");
            }
        } else if (shape == BuildPlan.Shape.END_PORTAL) {
            what = null;
        } else if (shape == BuildPlan.Shape.PORTAL) {
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
        // "x y z face": where they looked when they asked (a task kept while her hands were busy, #76)
        String[] spot = Actions.str(args, "at", "").trim().split("\\s+");
        if (spot.length >= 3 && spot[0].matches("-?\\d+") && spot[1].matches("-?\\d+") && spot[2].matches("-?\\d+")) {
            BlockPos at = new BlockPos(Integer.parseInt(spot[0]), Integer.parseInt(spot[1]), Integer.parseInt(spot[2]));
            Direction face = spot.length > 3 ? Direction.byName(spot[3]) : null;
            if (shape.clears()) origin = at;
            else origin = sp.serverLevel().getBlockState(at).canBeReplaced() || face == null ? at : at.relative(face);
        }
        boolean middle = "middle".equalsIgnoreCase(Actions.str(args, "at", ""));
        if (middle && lastMiddle == null) {
            return Actions.error("I haven't built anything yet to put it in the middle of: I'll put it where you look if you like.");
        }
        if (middle) origin = new BlockPos(lastMiddle[0], lastMiddle[1], lastMiddle[2]);
        Direction f = sp.getDirection();
        // clearing: everything from where they stand up (or above the level they name: "above Y 64")
        int level = args.has("level") ? Actions.num(args, "level", 0) : shape.clears() ? sp.getBlockY() - 1 : Integer.MIN_VALUE;
        List<BuildPlan.Step> steps = BuildPlan.steps(shape, origin.getX(), origin.getY(), origin.getZ(),
                f.getStepX(), f.getStepZ(),
                Actions.num(args, "width", shape == BuildPlan.Shape.PILLAR ? 1
                        : shape == BuildPlan.Shape.HOUSE || shape == BuildPlan.Shape.FARM ? 0 : 5), // (0: the shape's own size)
                Actions.num(args, "length", shape == BuildPlan.Shape.WALL || shape == BuildPlan.Shape.PILLAR ? 1
                        : shape == BuildPlan.Shape.HOUSE || shape == BuildPlan.Shape.FARM ? 0 : 5),
                Actions.num(args, "height", shape == BuildPlan.Shape.FLOOR ? 1 : shape == BuildPlan.Shape.HOUSE ? 0 : 3),
                Actions.num(args, "people", 2), level);

        String form = shape == BuildPlan.Shape.FORM ? Shapes.of(shapeName) : null;
        if (form != null) { // any shape, any size (#58): from the spot they look at, forward and up
            int[] d = Shapes.defaults(form);
            int radius = Actions.num(args, "radius", 0);
            int w = radius > 0 ? 2 * radius + 1 : Actions.num(args, "width", d[0]);
            int l = radius > 0 ? 2 * radius + 1 : Actions.num(args, "length", args.has("width") && !Shapes.is3d(form)
                    && !form.equals("rectangle") ? w : d[1]);
            int h = Actions.num(args, "height", Shapes.is3d(form) && (args.has("width") || radius > 0)
                    && (form.equals("sphere") || form.equals("cube") || form.equals("cone")) ? w : d[2]);
            boolean hollow = Actions.str(args, "hollow", "").equalsIgnoreCase("true");
            boolean vertical = Actions.str(args, "vertical", "").equalsIgnoreCase("true");
            int cap = isFree ? Shapes.MAX_CELLS : 1024;
            List<int[]> cells = Shapes.cells(form, w, l, h, hollow, vertical, Actions.num(args, "sides", 6),
                    Actions.num(args, "thickness", 1));
            if (cells.size() > cap) {
                return Actions.error("That's " + cells.size() + " blocks: too many " + (isFree ? "" : "to place by hand ")
                        + "(at most " + cap + "). A smaller size, or hollow?");
            }
            int rx = -f.getStepZ(), rz = f.getStepX();
            List<BuildPlan.Step> formSteps = new java.util.ArrayList<>(cells.size());
            for (int[] c : cells) {
                formSteps.add(new BuildPlan.Step(origin.getX() + c[0] * rx + c[2] * f.getStepX(), origin.getY() + c[1],
                        origin.getZ() + c[0] * rz + c[2] * f.getStepZ(), 'B'));
            }
            steps = formSteps;
        }
        String fillTop = null;
        if (shape == BuildPlan.Shape.FLATTEN) { // by size or radius, filled with the ground's own blocks (#74)
            int radius = Actions.num(args, "radius", 0);
            boolean centered = radius > 0;
            int w = radius > 0 ? 2 * radius + 1 : Actions.num(args, "width", 12);
            int l = radius > 0 ? 2 * radius + 1 : Actions.num(args, "length", 12);
            boolean round = radius > 0 && !Actions.str(args, "round", "true").equalsIgnoreCase("false");
            int lvl = args.has("level") ? Actions.num(args, "level", 0) : sp.getBlockY() - 1;
            int ox = sp.getBlockX() + (centered ? 0 : f.getStepX()), oz = sp.getBlockZ() + (centered ? 0 : f.getStepZ());
            String[] fill;
            if (!wanted.isBlank() || !isFree) {
                String id = BuiltInRegistries.ITEM.getKey(what).toString();
                fill = new String[]{id, id}; // a floor of what they named (or what's in their pockets)
            } else {
                fill = ground(sp.serverLevel(), ox, oz, lvl, Math.max(w, l) / 2);
            }
            fillTop = fill[0];
            steps = BuildPlan.flattenArea(ox, oz, lvl, w, l, centered, round, f.getStepX(), f.getStepZ(),
                    Actions.num(args, "height", 20), Actions.num(args, "depth", 4), fill[0], fill[1]);
        }
        long needed = steps.stream().filter(s -> s.kind() == 'B' || s.kind() == 'F' || s.kind() == 'P' || s.kind() == 'C').count();
        int have = isFree || what == null ? Integer.MAX_VALUE : count(sp, what);
        if (needed > 0 && have == 0) {
            return Actions.error("You don't have any " + name(what) + ". I can only build with what you have"
                    + (shape == BuildPlan.Shape.PORTAL ? " (a portal needs 10 obsidian)." : "."));
        }
        queue.clear();
        queue.addAll(steps);
        total = steps.size();
        flattening = shape == BuildPlan.Shape.FLATTEN;
        doing = shape == BuildPlan.Shape.FLATTEN ? "flattening the ground" : shape.clears() ? "clearing"
                : "building a " + (form != null ? form : shape.name().toLowerCase(Locale.ROOT)).replace('_', ' ');
        if (!shape.clears() && shape != BuildPlan.Shape.PLACE) lastMiddle = BuildPlan.middleTop(steps);
        item = what;
        free = isFree;
        style = st;
        owner = sp.getUUID();
        placed = cleared = skipped = 0;
        tick = 0;
        JsonObject r = Actions.ok();
        r.addProperty("building", form != null ? form.replace('_', ' ') : shape.name().toLowerCase(Locale.ROOT));
        if (what != null) r.addProperty("block", name(what));
        if (shape.clears()) r.addProperty("clearing", "up to " + steps.stream().filter(s -> s.kind() == 'X').count() + " blocks");
        if (fillTop != null) {
            r.addProperty("fill", fillTop.replace("minecraft:", "").replace('_', ' '));
            r.addProperty("block", fillTop.replace("minecraft:", "").replace('_', ' '));
            r.addProperty("note", "Anything someone built is left as it is, and so is water.");
        }
        if (needed > 0) r.addProperty("blocks", needed);
        if (!isFree && needed > 0 && have < needed) {
            r.addProperty("youHaveOnly", have);
            r.addProperty("note", "There's only enough for " + have + " of the " + needed + " blocks: I'll place those.");
        }
        if (shape == BuildPlan.Shape.PORTAL && !isFree && !hasLighter(sp)) {
            r.addProperty("note", "The frame, yes; to light it, the player needs flint and steel or a fire charge.");
        }
        if (shape == BuildPlan.Shape.FARM && !isFree && count(sp, Items.WATER_BUCKET) == 0) {
            r.addProperty("note", "No water bucket in your pockets: I'll till and plant, and leave the water hole for you to fill.");
        }
        if (shape == BuildPlan.Shape.END_PORTAL) r.addProperty("portal", "twelve frames with their eyes, and the way to the End open");
        if (shape == BuildPlan.Shape.HOUSE) r.addProperty("door", isFree || hasDoor(sp) ? "a door" : "a doorway (no door in your pockets)");
        double perSecond = isFree ? MAGIC_PER_TICK * 20.0 * (shape == BuildPlan.Shape.FLATTEN ? 8 : 1) : 20.0 / GROUNDED_EVERY;
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
        int budget = free ? (flattening ? MAGIC_PER_TICK * 8 : MAGIC_PER_TICK) : 1;
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
                case 'E' -> endFrame(level, at, s.block());
                case 'O' -> set(level, at, Blocks.END_PORTAL.defaultBlockState());
                case 'T' -> till(level, at);
                case 'W' -> water(level, sp, at);
                case 'C' -> plant(level, sp, at);
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
        if (s.kind() == 'F' && flattening && !here.getFluidState().isEmpty()) {
            skipped++;
            return false; // (water stays: a flattened field doesn't fill the lake beside it)
        }
        if (s.kind() == 'F' && flattening && (here.is(BlockTags.LEAVES) || here.is(BlockTags.LOGS))) {
            level.destroyBlock(at, !free, sp); // (a tree's stump or fallen leaves at ground level: ground instead)
            here = level.getBlockState(at);
        }
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
        if (flattening && !BlueprintBuild.natural(st)) {
            skipped++;
            return false; // never what someone built
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

    /** An end portal frame with its eye, facing the middle (block: "dx,dz"). */
    private static boolean endFrame(ServerLevel level, BlockPos at, String facing) {
        String[] d = (facing == null ? "0,1" : facing).split(",");
        Direction dir = Direction.getNearest(Integer.parseInt(d[0]), 0, Integer.parseInt(d[1]));
        return set(level, at, Blocks.END_PORTAL_FRAME.defaultBlockState()
                .setValue(net.minecraft.world.level.block.EndPortalFrameBlock.FACING, dir)
                .setValue(net.minecraft.world.level.block.EndPortalFrameBlock.HAS_EYE, true));
    }

    /** Set a block where there's air, a plant or grass (never over something built or a fluid). */
    private static boolean set(ServerLevel level, BlockPos at, BlockState st) {
        BlockState here = level.getBlockState(at);
        if (!(here.isAir() || here.canBeReplaced()) || !here.getFluidState().isEmpty()) {
            skipped++;
            return false;
        }
        level.setBlockAndUpdate(at, st);
        placed++;
        return true;
    }

    /** Ground becomes farmland (watered): grass, dirt, coarse dirt, a path; what grows on it goes first. */
    private static boolean till(ServerLevel level, BlockPos at) {
        BlockState st = level.getBlockState(at);
        boolean soil = st.is(Blocks.GRASS_BLOCK) || st.is(Blocks.DIRT) || st.is(Blocks.COARSE_DIRT) || st.is(Blocks.DIRT_PATH)
                || st.is(Blocks.ROOTED_DIRT) || st.is(Blocks.FARMLAND) || st.is(Blocks.PODZOL) || st.is(Blocks.MYCELIUM);
        if (st.isAir()) soil = true; // (a hole: filled with farmland)
        if (!soil) {
            skipped++;
            return false;
        }
        BlockPos up = at.above();
        if (level.getBlockState(up).canBeReplaced() && !level.getBlockState(up).isAir()) level.destroyBlock(up, false);
        level.setBlockAndUpdate(at, Blocks.FARMLAND.defaultBlockState().setValue(net.minecraft.world.level.block.FarmBlock.MOISTURE, 7));
        placed++;
        return true;
    }

    /** The water in the middle (grounded: from their water bucket, which stays a bucket). */
    private static boolean water(ServerLevel level, ServerPlayer sp, BlockPos at) {
        if (!free) {
            boolean has = false;
            for (ItemStack s : sp.getInventory().items) if (s.is(Items.WATER_BUCKET)) has = true;
            if (!has) {
                level.setBlockAndUpdate(at, Blocks.AIR.defaultBlockState()); // (the hole, for their water)
                return true;
            }
        }
        BlockPos up = at.above();
        if (level.getBlockState(up).canBeReplaced() && !level.getBlockState(up).isAir()) level.destroyBlock(up, false);
        level.setBlockAndUpdate(at, Blocks.WATER.defaultBlockState());
        placed++;
        return true;
    }

    /** A crop on the farmland below (grounded: one of their seeds). */
    private static boolean plant(ServerLevel level, ServerPlayer sp, BlockPos at) {
        if (!level.getBlockState(at.below()).is(Blocks.FARMLAND) || !level.getBlockState(at).canBeReplaced()) {
            skipped++;
            return false;
        }
        if (!(item instanceof BlockItem bi)) return false;
        if (!free && count(sp, item) == 0) return false;
        level.setBlockAndUpdate(at, bi.getBlock().defaultBlockState());
        if (!free) take(sp, item);
        placed++;
        return true;
    }

    /** What to plant, from what they said: the seed item (wheat seeds, a carrot, a potato, beetroot seeds). */
    private static Item crop(String wanted) {
        String w = wanted.toLowerCase(Locale.ROOT);
        if (w.contains("carrot")) return Items.CARROT;
        if (w.contains("potato")) return Items.POTATO;
        if (w.contains("beet")) return Items.BEETROOT_SEEDS;
        if (w.contains("wheat") || w.contains("seed") || w.contains("crop") || w.contains("farm") || w.contains("bread")) return Items.WHEAT_SEEDS;
        return null;
    }

    public static boolean busy() {
        return !queue.isEmpty();
    }

    /** What she's building and how far along, or null when she isn't. */
    public static JsonObject progress() {
        int left = queue.size();
        if (left == 0 || total < 20) return null; // (a block or two isn't a task worth waiting for)
        JsonObject o = new JsonObject();
        o.addProperty("what", doing);
        o.addProperty("done", total - left);
        o.addProperty("total", total);
        return o;
    }

    private static Item blockItem(ServerPlayer sp, String wanted, boolean free) {
        ItemStack hand = sp.getMainHandItem();
        if (wanted.isBlank() || wanted.equalsIgnoreCase("hand") || wanted.equalsIgnoreCase("held")) {
            return buildable(hand.getItem()) ? hand.getItem() : mostBlocks(sp);
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

    /** The ground around (x, z) at the level: the most common natural top block there, and what goes under it
     *  (grass on dirt, sand on sandstone, snow on dirt...), so a flattened field looks like the land around it. */
    private static String[] ground(ServerLevel level, int x, int z, int lvl, int reach) {
        java.util.Map<net.minecraft.world.level.block.Block, Integer> seen = new java.util.HashMap<>();
        int step = Math.max(1, reach / 6);
        for (int dx = -reach; dx <= reach; dx += step) for (int dz = -reach; dz <= reach; dz += step) {
            for (int y = lvl + 6; y >= lvl - 6; y--) { // the surface near the level here
                BlockState st = level.getBlockState(new BlockPos(x + dx, y, z + dz));
                if (st.isAir() || st.canBeReplaced() || st.is(BlockTags.LEAVES) || st.is(BlockTags.LOGS)) continue;
                if (st.is(BlockTags.DIRT) || st.is(BlockTags.SAND) || st.is(Blocks.GRAVEL) || st.is(Blocks.SNOW_BLOCK)
                        || st.is(BlockTags.BASE_STONE_OVERWORLD) || st.is(BlockTags.TERRACOTTA) || st.is(Blocks.CLAY)) {
                    seen.merge(st.getBlock(), 1, Integer::sum);
                }
                break;
            }
        }
        net.minecraft.world.level.block.Block top = seen.entrySet().stream().max(java.util.Map.Entry.comparingByValue())
                .map(java.util.Map.Entry::getKey).orElse(Blocks.GRASS_BLOCK);
        net.minecraft.world.level.block.Block under = top == Blocks.SAND ? Blocks.SANDSTONE
                : top == Blocks.RED_SAND ? Blocks.RED_SANDSTONE
                : top.defaultBlockState().is(BlockTags.DIRT) || top == Blocks.SNOW_BLOCK ? Blocks.DIRT : top;
        if (top == Blocks.SNOW_BLOCK) top = Blocks.GRASS_BLOCK; // (snowy plains: grass, the snow falls again by itself)
        return new String[]{BuiltInRegistries.BLOCK.getKey(top).toString(), BuiltInRegistries.BLOCK.getKey(under).toString()};
    }

    /** A block to build with: not seeds, saplings, flowers or crops (wheat seeds in your hand made an outline of wheat). */
    private static boolean buildable(Item it) {
        return it instanceof BlockItem b && !(b.getBlock() instanceof net.minecraft.world.level.block.BushBlock);
    }

    private static Item itemOf(String id) {
        ResourceLocation key = ResourceLocation.tryParse(id.contains(":") ? id : "minecraft:" + id);
        return key == null ? null : BuiltInRegistries.ITEM.getOptional(key).orElse(null);
    }

    private static Item mostBlocks(ServerPlayer sp) {
        java.util.Map<Item, Integer> n = new java.util.HashMap<>();
        for (ItemStack s : sp.getInventory().items) if (buildable(s.getItem())) n.merge(s.getItem(), s.getCount(), Integer::sum);
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
