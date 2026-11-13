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
 * <p><b>Grounded</b> (her default): within {@link #GROUNDED_RADIUS} blocks of you; mining goes through
 * her {@link Hands} with the tool in your hand, as slowly as it would for you (the cracks show), the
 * tool wears, a block that needs a better tool stops the job and says so, drops go to your pockets; crafting uses your items and needs a crafting table or furnace nearby (or in your pockets)
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

    enum Result { DONE, SKIPPED, WORKING }

    private interface Work {
        /** One tick of work: done, skipped (couldn't), or still working on it (mining a hard block). */
        Result run(ServerPlayer sp);
    }

    /** Work that's done in one go: true done, false skipped. */
    private interface Quick {
        boolean run(ServerPlayer sp);
    }

    private static Work quick(Quick q) {
        return sp -> q.run(sp) ? Result.DONE : Result.SKIPPED;
    }

    private static final class Job {
        final String kind, what;
        final UUID owner;
        final boolean magic;
        final Deque<Work> work = new ArrayDeque<>();
        final Map<String, Integer> got = new TreeMap<>();
        int done, skipped, total, pause;
        String stoppedBecause;

        Job(String kind, String what, UUID owner, boolean magic) {
            this.kind = kind;
            this.what = what;
            this.owner = owner;
            this.magic = magic;
        }
    }

    private static Job job;
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
        for (int[] p : cells) {
            BlockPos at = new BlockPos(p[0], p[1], p[2]);
            j.work.add(magic ? quick(s -> breakBlock(s, at, j)) : new Mining(at, j));
        }
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
        for (ItemEntity e : items) j.work.add(quick(s -> pickUp(s, e, j)));
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
        j.work.add(quick(s -> {
            if (!magic && !takeFuel(s, (plan.smeltedItems() + 7) / 8, true)) return false;
            CraftPlanner.Plan done = GameRecipes.carryOut(s, planner(s.getServer()), id, n);
            if (!done.canMakeNow()) return false; // something left their pockets meanwhile: nothing changed
            if (!magic) takeFuel(s, (done.smeltedItems() + 7) / 8, false);
            j.got.merge(id.substring(id.indexOf(':') + 1), n, Integer::sum);
            return true;
        }));
        JsonObject r = start(j, 1);
        r.add("steps", toJson(stepsOf(plan)));
        return r;
    }

    /**
     * Her {@code job} action: {"kind": "mine" | "chop" | "collect" | "craft" | "return_items" | "stop" | "status",
     * "what", "count", "x", "y", "z" (return_items: where they died, else the last death this game saw)}.
     */
    public static JsonObject action(ServerPlayer sp, JsonObject args, boolean magic) {
        String kind = str(args, "kind", "status").toLowerCase(java.util.Locale.ROOT).replace(' ', '_');
        String what = str(args, "what", "");
        int count = args.has("count") ? Math.max(1, args.get("count").getAsInt()) : 0;
        if (busy() && !kind.equals("stop") && !kind.equals("status")) {
            return error("I'm still busy with the last job (" + job.kind + " " + job.what + "). Say stop first.");
        }
        return switch (kind) {
            case "mine", "dig", "collect_blocks" -> what.isBlank() ? error("Mine what? (iron, coal, stone, diamonds...)")
                    : mine(sp, what, count == 0 ? 8 : count, magic);
            case "chop", "tree", "wood", "logs" -> chop(sp, count == 0 ? 64 : count, magic);
            case "collect", "pick_up", "gather" -> collect(sp, magic);
            case "craft", "make" -> what.isBlank() ? error("Craft what?") : craft(sp, what, count == 0 ? 1 : count, magic);
            case "return_items", "get_my_things", "death" -> {
                BlockPos at = args.has("x") && args.has("z")
                        ? BlockPos.containing(args.get("x").getAsDouble(), args.has("y") ? args.get("y").getAsDouble() : sp.getY(),
                        args.get("z").getAsDouble())
                        : deathOf(sp);
                yield at == null ? error("I don't know where you died.") : returnItems(sp, at, magic);
            }
            case "stop" -> stop();
            default -> status();
        };
    }

    /** "Chop that tree": the nearest tree within reach, its whole trunk (grounded: with your axe, at its speed). */
    public static JsonObject chop(ServerPlayer sp, int max, boolean magic) {
        ServerLevel level = sp.serverLevel();
        BlockPos c = sp.blockPosition();
        int radius = magic ? 16 : 8;
        Predicate<String> logs = Dig.kind("log");
        Dig.World world = (x, y, z) -> {
            BlockPos p = new BlockPos(x, y, z);
            return level.isLoaded(p) ? BuiltInRegistries.BLOCK.getKey(level.getBlockState(p).getBlock()).toString() : "";
        };
        // the tree they look at, else the nearest log
        net.minecraft.world.phys.HitResult hit = sp.pick(8, 1f, false);
        List<int[]> start = null;
        if (hit instanceof net.minecraft.world.phys.BlockHitResult bh && hit.getType() == net.minecraft.world.phys.HitResult.Type.BLOCK
                && level.getBlockState(bh.getBlockPos()).is(net.minecraft.tags.BlockTags.LOGS)) {
            BlockPos b = bh.getBlockPos();
            start = List.of(new int[]{b.getX(), b.getY(), b.getZ()});
        } else {
            start = Dig.find(world, c.getX(), c.getY(), c.getZ(), radius, logs, 1);
        }
        if (start.isEmpty()) return error("There's no tree within " + radius + " blocks.");
        int[] s0 = start.get(0);
        List<int[]> trunk = Dig.vein(world, s0[0], s0[1], s0[2], logs, Math.min(max, MAX_BLOCKS), true);
        trunk.sort(java.util.Comparator.comparingInt(p -> p[1])); // from the bottom, like a player
        Job j = new Job("chop", "a tree", sp.getUUID(), magic);
        for (int[] p : trunk) {
            BlockPos at = new BlockPos(p[0], p[1], p[2]);
            j.work.add(magic ? quick(s -> breakBlock(s, at, j)) : new Mining(at, j));
        }
        return start(j, trunk.size());
    }

    /** Where each player last died (this game saw it), for "get my things back". */
    private static final Map<UUID, BlockPos> deaths = new java.util.concurrent.ConcurrentHashMap<>();

    public static BlockPos deathOf(ServerPlayer sp) {
        return deaths.get(sp.getUUID());
    }

    /** Hooks for the world's game: the job tick and where players die. Called once from the client entrypoint. */
    public static void register() {
        net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents.END_SERVER_TICK.register(Jobs::tick);
        net.fabricmc.fabric.api.entity.event.v1.ServerLivingEntityEvents.AFTER_DEATH.register((entity, source) -> {
            if (entity instanceof ServerPlayer p && !(p instanceof net.fabricmc.fabric.api.entity.FakePlayer)) {
                deaths.put(p.getUUID(), p.blockPosition());
            }
        });
    }

    /** "What am I missing for a piston?": the plan from their pockets, in words for her. */
    public static JsonObject craftHelp(ServerPlayer sp, String item, int count) {
        CraftPlanner p = planner(sp.getServer());
        String id = item.contains(":") ? item : "minecraft:" + item.trim().toLowerCase(java.util.Locale.ROOT).replace(' ', '_');
        if (!p.knows(id)) {
            JsonObject r = error("There's no recipe for " + item + " (it's found or mined, not crafted, or it has another name).");
            r.addProperty("item", item);
            return r;
        }
        CraftPlanner.Plan plan = p.plan(id, Math.max(1, count), GameRecipes.pockets(sp));
        JsonObject r = ok();
        r.addProperty("item", id.replace("minecraft:", ""));
        r.addProperty("count", Math.max(1, count));
        r.addProperty("canMakeNow", plan.canMakeNow());
        StringBuilder steps = new StringBuilder();
        for (CraftPlanner.Step st : plan.steps()) {
            if (steps.length() > 0) steps.append(", then ");
            steps.append(st.recipe().station() == dev.kindredspirit.craft.Recipe.Station.FURNACE ? "smelt " : "craft ")
                    .append(st.makes()).append(' ').append(st.recipe().result().replace("minecraft:", "").replace('_', ' '));
        }
        r.addProperty("steps", steps.toString());
        if (!plan.missing().isEmpty()) r.add("missing", toJson(plan.missing()));
        r.add("uses", toJson(plan.fromInventory()));
        if (!plan.stations().isEmpty()) {
            r.addProperty("needs", plan.stations().stream().map(st -> st == dev.kindredspirit.craft.Recipe.Station.FURNACE
                    ? "a furnace and fuel" : "a crafting table").reduce((a, b) -> a + " and " + b).orElse(""));
        }
        return r;
    }

    /** Trading help: the nearest villager's real offers, against the player's pockets. */
    public static JsonObject trades(ServerPlayer sp) {
        net.minecraft.world.entity.npc.AbstractVillager v = dev.kindredspirit.trade.VillagerTrades.nearest(sp, 10);
        if (v == null) return error("There's no villager within 10 blocks.");
        JsonObject r = ok();
        r.addProperty("villager", dev.kindredspirit.trade.VillagerTrades.who(v));
        com.google.gson.JsonArray lines = new com.google.gson.JsonArray();
        var advice = dev.kindredspirit.trade.TradeAdvice.advise("", dev.kindredspirit.trade.VillagerTrades.offers(v),
                dev.kindredspirit.trade.VillagerTrades.pockets(sp));
        for (int i = 0; i < Math.min(8, advice.size()); i++) lines.add(advice.get(i).line());
        r.add("offers", lines);
        r.addProperty("distance", (int) Math.round(v.distanceTo(sp)));
        if (advice.isEmpty()) r.addProperty("note", "It has nothing to trade (no job yet, or a baby).");
        return r;
    }

    private static String str(JsonObject o, String k, String d) {
        return o.has(k) && !o.get(k).isJsonNull() ? o.get(k).getAsString() : d;
    }

    public static JsonObject stop() {
        if (job == null) return error("I'm not doing a job.");
        job.stoppedBecause = "asked";
        JsonObject r = status(job);
        last = r;
        job = null;
        return r;
    }

    public static JsonObject status() {
        if (job == null) {
            JsonObject r = ok();
            r.addProperty("job", "none");
            if (last != null) r.add("last", last);
            return r;
        }
        return status(job);
    }

    private static JsonObject status(Job job) {
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
        ServerPlayer sp = server.getPlayerList().getPlayer(j.owner);
        if (sp == null) {
            job = null; // they left
            return;
        }
        if (j.magic) {
            for (int budget = MAGIC_PER_TICK; budget > 0 && !j.work.isEmpty() && j.stoppedBecause == null; budget--) {
                count(j, j.work.poll().run(sp));
            }
        } else if (j.pause > 0) {
            j.pause--; // a breath between blocks, so you see each one go
        } else if (!j.work.isEmpty() && j.stoppedBecause == null) {
            Result r = j.work.peek().run(sp);
            if (r != Result.WORKING) {
                j.work.poll();
                count(j, r);
                j.pause = GROUNDED_EVERY - 1;
            }
        }
        if (j.work.isEmpty() || j.stoppedBecause != null) {
            last = status(j);
            job = null; // finished: the brain asks status() or hears it
        }
    }

    private static JsonObject last;

    /** How the last job ended (what it got, what stopped it), once it's over. */
    public static JsonObject lastResult() {
        return last;
    }

    private static void count(Job j, Result r) {
        if (r == Result.DONE) j.done++;
        else if (r == Result.SKIPPED) j.skipped++;
    }

    /**
     * Grounded mining of one block: with the tool in the player's hand, taking as long as it would take
     * them (the cracks show), through her hands so the game's rules and protections apply.
     */
    private static final class Mining implements Work {
        final BlockPos at;
        final Job j;
        int ticks, needed = -2;

        Mining(BlockPos at, Job j) {
            this.at = at;
            this.j = j;
        }

        @Override
        public Result run(ServerPlayer sp) {
            ServerLevel level = sp.serverLevel();
            BlockState st = level.getBlockState(at);
            if (st.isAir() || level.getBlockEntity(at) instanceof Container || at.equals(sp.blockPosition().below())
                    || at.distSqr(sp.blockPosition()) > (GROUNDED_RADIUS + 4) * (GROUNDED_RADIUS + 4)) {
                Hands.cracks(sp, at, -1);
                return Result.SKIPPED; // gone already, holds things, under their feet, or they walked away
            }
            ItemStack tool = sp.getMainHandItem();
            if (needed == -2) {
                if (st.requiresCorrectToolForDrops() && !tool.isCorrectToolForDrops(st)) {
                    j.stoppedBecause = "needs a better tool for " + BuiltInRegistries.BLOCK.getKey(st.getBlock()).getPath().replace('_', ' ');
                    return Result.SKIPPED;
                }
                needed = Hands.breakTicks(sp, at, tool);
                if (needed < 0) return Result.SKIPPED;
                visit(at);
            }
            ticks++;
            if (ticks < needed) {
                Hands.cracks(sp, at, Math.min(9, ticks * 10 / needed));
                return Result.WORKING;
            }
            return Hands.breakBlock(sp, at, tool, j.got) ? Result.DONE : Result.SKIPPED;
        }
    }

    /** She floats to the block she's working on (only in the game she lives in: singleplayer or hosting). */
    private static void visit(BlockPos at) {
        try {
            net.minecraft.client.Minecraft mc = net.minecraft.client.Minecraft.getInstance();
            double x = at.getX() + 0.5, y = at.getY() + 1.3, z = at.getZ() + 0.5;
            mc.execute(() -> dev.kindredspirit.KindredSpiritClient.get().companion().life.visit(x, y, z, 1.2,
                    System.nanoTime() / 1e9));
        } catch (RuntimeException ignored) {
            // no companion to move (a dedicated server, or she isn't here): the work still happens
        }
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
