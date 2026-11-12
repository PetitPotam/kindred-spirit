package dev.kindredspirit.job;

import com.google.gson.JsonObject;
import dev.kindredspirit.craft.CraftPlanner;
import dev.kindredspirit.craft.GameRecipes;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.Container;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.UUID;
import java.util.function.Predicate;

/**
 * Jobs that take a while (Phase 5): mine some of something, collect what's lying around, craft a
 * batch, get your things back where you died. One job at a time, run a little every server tick, so
 * you see it happen and can say "stop". Every job remembers who asked (their pockets, their reach).
 *
 * <p><b>Grounded</b> (her default): within {@link #GROUNDED_RADIUS} blocks of you; mining uses the tool
 * in your hand (it wears, and a block that needs a better tool is skipped and said so), drops go to your
 * pockets; crafting uses your items and needs a crafting table or furnace nearby (or in your pockets)
 * and fuel for smelting. <b>Magic</b>: a wider reach, no tool needed, faster.
 *
 * <p>Never breaks unbreakable blocks, anything that holds items (chests, barrels, furnaces), or blocks
 * under the player. Not wired yet: {@link #tick} goes next to the Builder's tick, and the actions
 * ({@code job} with {@code kind = mine | collect | craft | return_items | stop | status}) into
 * act/Actions once the playtest-fixes branch has landed (it owns those files).
 */
public final class Jobs {
    private Jobs() {}

    public static final int GROUNDED_RADIUS = 12, MAGIC_RADIUS = 32;
    static final int GROUNDED_EVERY = 4; // a block every 4 ticks (5 a second): you see each one go
    static final int MAGIC_PER_TICK = 4;
    static final int MAX_BLOCKS = 256;

    private interface Work {
        /** One unit of work; false when it couldn't be done (counted as skipped). */
        boolean run(ServerPlayer sp);
    }

    private static final class Job {
        final String kind, what;
        final UUID owner;
        final boolean magic;
        final Deque<Work> work = new ArrayDeque<>();
        final Map<String, Integer> got = new TreeMap<>();
        int done, skipped, total;
        String stoppedBecause;

        Job(String kind, String what, UUID owner, boolean magic) {
            this.kind = kind;
            this.what = what;
            this.owner = owner;
            this.magic = magic;
        }
    }

    private static Job job;
    private static int tick;
    private static CraftPlanner planner;
    private static MinecraftServer plannerFor;

    // --- starting --------------------------------------------------------------------------------

    /** "Mine 10 iron": the nearest veins within reach, whole, nearest first. */
    public static JsonObject mine(ServerPlayer sp, String what, int count, boolean magic) {
        ServerLevel level = sp.serverLevel();
        BlockPos c = sp.blockPosition();
        int radius = magic ? MAGIC_RADIUS : GROUNDED_RADIUS;
        Predicate<String> kind = Dig.kind(what);
        Dig.World world = (x, y, z) -> {
            BlockPos p = new BlockPos(x, y, z);
            return level.isLoaded(p) ? BuiltInRegistries.BLOCK.getKey(level.getBlockState(p).getBlock()).toString() : "";
        };
        List<int[]> cells = Dig.find(world, c.getX(), c.getY(), c.getZ(), radius, kind, Math.max(1, Math.min(count, MAX_BLOCKS)));
        if (cells.isEmpty()) return error("There's no " + what + " within " + radius + " blocks.");
        Job j = new Job("mine", what, sp.getUUID(), magic);
        for (int[] p : cells) j.work.add(s -> breakBlock(s, new BlockPos(p[0], p[1], p[2]), j));
        return start(j, cells.size());
    }

    /** Items lying around (a broken chest, a mob farm's drops) into your pockets. */
    public static JsonObject collect(ServerPlayer sp, boolean magic) {
        return gather(sp, sp.blockPosition(), magic ? MAGIC_RADIUS : GROUNDED_RADIUS, "collect", "what's lying around", magic);
    }

    /** Your things where you died. Grounded: you need to be near the spot; magic: from anywhere loaded. */
    public static JsonObject returnItems(ServerPlayer sp, BlockPos deathSpot, boolean magic) {
        if (!magic && deathSpot.distSqr(sp.blockPosition()) > 32 * 32) {
            return error("Your things are where you died, " + (int) Math.sqrt(deathSpot.distSqr(sp.blockPosition()))
                    + " blocks away. Go there with me and I'll gather them (they vanish after five minutes).");
        }
        if (!sp.serverLevel().isLoaded(deathSpot)) return error("That spot is too far away for me to reach right now.");
        return gather(sp, deathSpot, 8, "return_items", "your things", magic);
    }

    private static JsonObject gather(ServerPlayer sp, BlockPos at, int radius, String kind, String what, boolean magic) {
        List<ItemEntity> items = sp.serverLevel().getEntitiesOfClass(ItemEntity.class, new AABB(at).inflate(radius),
                e -> e.isAlive() && !e.getItem().isEmpty());
        if (items.isEmpty()) return error("There's nothing lying around" + (kind.equals("return_items") ? " where you died anymore." : " here."));
        Job j = new Job(kind, what, sp.getUUID(), magic);
        for (ItemEntity e : items) j.work.add(s -> pickUp(s, e, j));
        return start(j, items.size());
    }

    /** "Make me 16 torches" from your own things (the planner works out the sticks and charcoal). */
    public static JsonObject craft(ServerPlayer sp, String item, int count, boolean magic) {
        CraftPlanner p = planner(sp.getServer());
        String id = item.contains(":") ? item : "minecraft:" + item.trim().toLowerCase(java.util.Locale.ROOT).replace(' ', '_');
        if (!p.knows(id)) return error("I don't know a recipe for " + item + ".");
        int n = Math.max(1, Math.min(count, 576));
        CraftPlanner.Plan plan = p.plan(id, n, GameRecipes.pockets(sp));
        if (!plan.canMakeNow()) {
            JsonObject r = error("Not enough to make it yet.");
            r.add("missing", toJson(plan.missing()));
            return r;
        }
        if (!magic) {
            for (var station : plan.stations()) {
                if (!near(sp, station)) {
                    return error("I need a " + (station == dev.kindredspirit.craft.Recipe.Station.FURNACE ? "furnace"
                            : "crafting table") + " close by (or in your pockets) for that.");
                }
            }
            int fuel = (plan.smeltedItems() + 7) / 8;
            if (fuel > 0 && !takeFuel(sp, fuel, true)) return error("Smelting needs fuel: " + fuel + " coal or charcoal.");
        }
        Job j = new Job("craft", id, sp.getUUID(), magic);
        j.work.add(s -> {
            if (!magic && !takeFuel(s, (plan.smeltedItems() + 7) / 8, true)) return false;
            CraftPlanner.Plan done = GameRecipes.carryOut(s, planner(s.getServer()), id, n);
            if (!done.canMakeNow()) return false; // something left their pockets meanwhile: nothing changed
            if (!magic) takeFuel(s, (done.smeltedItems() + 7) / 8, false);
            j.got.merge(id.substring(id.indexOf(':') + 1), n, Integer::sum);
            return true;
        });
        JsonObject r = start(j, 1);
        r.add("steps", toJson(stepsOf(plan)));
        return r;
    }

    public static JsonObject stop() {
        if (job == null) return error("I'm not doing a job.");
        job.stoppedBecause = "asked";
        JsonObject r = status();
        job = null;
        return r;
    }

    public static JsonObject status() {
        if (job == null) {
            JsonObject r = ok();
            r.addProperty("job", "none");
            return r;
        }
        JsonObject r = ok();
        r.addProperty("job", job.kind);
        r.addProperty("what", job.what);
        r.addProperty("done", job.done);
        r.addProperty("skipped", job.skipped);
        r.addProperty("left", job.work.size());
        r.add("got", toJson(job.got));
        if (job.stoppedBecause != null) r.addProperty("stopped", job.stoppedBecause);
        return r;
    }

    public static boolean busy() {
        return job != null;
    }

    private static JsonObject start(Job j, int total) {
        j.total = total;
        job = j;
        tick = 0;
        JsonObject r = ok();
        r.addProperty("job", j.kind);
        r.addProperty("what", j.what);
        r.addProperty("total", total);
        r.addProperty("seconds", j.magic ? Math.round(total / (MAGIC_PER_TICK * 20.0)) : Math.round(total * GROUNDED_EVERY / 20.0));
        return r;
    }

    // --- running ---------------------------------------------------------------------------------

    /** Every server tick (next to Builder.tick). */
    public static void tick(MinecraftServer server) {
        Job j = job;
        if (j == null) return;
        if (!j.magic && ++tick % GROUNDED_EVERY != 0) return;
        ServerPlayer sp = server.getPlayerList().getPlayer(j.owner);
        if (sp == null) {
            job = null; // they left
            return;
        }
        int budget = j.magic ? MAGIC_PER_TICK : 1;
        while (budget-- > 0 && !j.work.isEmpty() && j.stoppedBecause == null) {
            if (j.work.poll().run(sp)) j.done++;
            else j.skipped++;
        }
        if (j.work.isEmpty() || j.stoppedBecause != null) job = null; // finished: the brain asks status() or hears it
    }

    private static boolean breakBlock(ServerPlayer sp, BlockPos at, Job j) {
        ServerLevel level = sp.serverLevel();
        BlockState st = level.getBlockState(at);
        if (st.isAir() || st.getDestroySpeed(level, at) < 0 || level.getBlockEntity(at) instanceof Container) return false;
        if (at.equals(sp.blockPosition().below())) return false; // never the block under their feet
        int reach = j.magic ? MAGIC_RADIUS : GROUNDED_RADIUS;
        if (at.distSqr(sp.blockPosition()) > (reach + 4) * (reach + 4)) return false; // they walked away
        ItemStack tool = j.magic ? new ItemStack(Items.NETHERITE_PICKAXE) : sp.getMainHandItem();
        if (!j.magic && st.requiresCorrectToolForDrops() && !tool.isCorrectToolForDrops(st)) {
            j.stoppedBecause = "needs a better tool for " + BuiltInRegistries.BLOCK.getKey(st.getBlock()).getPath().replace('_', ' ');
            return false;
        }
        for (ItemStack drop : Block.getDrops(st, level, at, level.getBlockEntity(at), sp, tool)) {
            j.got.merge(BuiltInRegistries.ITEM.getKey(drop.getItem()).getPath(), drop.getCount(), Integer::sum);
            if (!sp.getInventory().add(drop)) sp.drop(drop, false);
        }
        level.destroyBlock(at, false, sp);
        if (!j.magic && !tool.isEmpty() && tool.isDamageableItem()) tool.hurtAndBreak(1, sp, EquipmentSlot.MAINHAND);
        return true;
    }

    private static boolean pickUp(ServerPlayer sp, ItemEntity e, Job j) {
        if (!e.isAlive()) return false;
        ItemStack stack = e.getItem().copy();
        int before = stack.getCount();
        String name = BuiltInRegistries.ITEM.getKey(stack.getItem()).getPath();
        sp.getInventory().add(stack);
        int moved = before - stack.getCount();
        if (moved <= 0) {
            j.stoppedBecause = "your pockets are full";
            return false;
        }
        j.got.merge(name, moved, Integer::sum);
        if (stack.isEmpty()) e.discard();
        else e.setItem(stack);
        return true;
    }

    private static boolean near(ServerPlayer sp, dev.kindredspirit.craft.Recipe.Station station) {
        boolean furnace = station == dev.kindredspirit.craft.Recipe.Station.FURNACE;
        if (sp.getInventory().contains(new ItemStack(furnace ? Items.FURNACE : Items.CRAFTING_TABLE))) return true;
        BlockPos c = sp.blockPosition();
        for (BlockPos p : BlockPos.betweenClosed(c.offset(-6, -3, -6), c.offset(6, 3, 6))) {
            BlockState s = sp.serverLevel().getBlockState(p);
            if (furnace ? s.is(Blocks.FURNACE) || s.is(Blocks.BLAST_FURNACE) : s.is(Blocks.CRAFTING_TABLE)) return true;
        }
        return false;
    }

    /** Coal or charcoal (one smelts 8): checks, or takes them. */
    private static boolean takeFuel(ServerPlayer sp, int n, boolean checkOnly) {
        int have = 0;
        for (ItemStack s : sp.getInventory().items) if (s.is(Items.COAL) || s.is(Items.CHARCOAL)) have += s.getCount();
        if (have < n) return false;
        if (checkOnly) return true;
        for (ItemStack s : sp.getInventory().items) {
            if (n <= 0) break;
            if (s.is(Items.COAL) || s.is(Items.CHARCOAL)) {
                int t = Math.min(n, s.getCount());
                s.shrink(t);
                n -= t;
            }
        }
        return true;
    }

    private static CraftPlanner planner(MinecraftServer server) {
        if (planner == null || plannerFor != server) {
            planner = new CraftPlanner(GameRecipes.from(server.getRecipeManager(), server.registryAccess()));
            plannerFor = server;
        }
        return planner;
    }

    /** After a data pack reload. */
    public static void forgetRecipes() {
        planner = null;
    }

    private static Map<String, Integer> stepsOf(CraftPlanner.Plan plan) {
        Map<String, Integer> m = new java.util.LinkedHashMap<>();
        for (CraftPlanner.Step s : plan.steps()) m.merge(s.recipe().result().replace("minecraft:", ""), s.makes(), Integer::sum);
        return m;
    }

    private static JsonObject toJson(Map<String, Integer> m) {
        JsonObject o = new JsonObject();
        m.forEach((k, v) -> o.addProperty(k.replace("minecraft:", ""), v));
        return o;
    }

    private static JsonObject ok() {
        JsonObject r = new JsonObject();
        r.addProperty("ok", true);
        return r;
    }

    private static JsonObject error(String why) {
        JsonObject r = new JsonObject();
        r.addProperty("ok", false);
        r.addProperty("error", why);
        return r;
    }
}
