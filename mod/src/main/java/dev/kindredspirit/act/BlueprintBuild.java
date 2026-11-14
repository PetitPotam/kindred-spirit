package dev.kindredspirit.act;

import dev.kindredspirit.util.Mc;
import com.google.gson.JsonObject;
import dev.kindredspirit.KindredSpiritClient;
import dev.kindredspirit.blueprint.BlockSpec;
import dev.kindredspirit.blueprint.Blueprint;
import dev.kindredspirit.blueprint.BlueprintException;
import dev.kindredspirit.blueprint.Blueprints;
import dev.kindredspirit.blueprint.CommandPlan;
import dev.kindredspirit.blueprint.House;
import dev.kindredspirit.blueprint.Materials;
import dev.kindredspirit.blueprint.Placement;
import dev.kindredspirit.craft.CraftPlanner;
import dev.kindredspirit.craft.GameRecipes;
import net.minecraft.commands.arguments.blocks.BlockStateParser;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundSource;
import net.minecraft.tags.BlockTags;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

/**
 * Building from a blueprint: a generated cottage sized for how many people ("a cozy cottage for
 * three"), or a schematic file the player put in {@code config/kindredspirit/blueprints/} (or the
 * {@code schematics/} folder Litematica and Create use). Placed where the player looks, its door
 * toward them, its floor replacing the ground there.
 *
 * <p><b>Magic</b>: it rises through her command powers ({@link Commands}: /fill and /setblock, run as
 * the player, allowlisted and logged), a command or two a tick, with sparkles. <b>Grounded</b>: first
 * the material list against the player's pockets (and what they could craft from them); then block
 * by block from their items, what's in the way going into their pockets.
 *
 * <p>Never over the player's work: if anything built is in the way (planks, glass, a chest...: anything
 * that isn't ground, stone, plants or trees), she says so and doesn't start. Never where the player stands.
 */
public final class BlueprintBuild {
    private BlueprintBuild() {}

    private static final org.slf4j.Logger LOG = org.slf4j.LoggerFactory.getLogger("kindredspirit");
    static final int GROUNDED_EVERY = 2;   // a block every 2 ticks (10 a second)
    static final int MAGIC_EVERY = 2;      // a command every 2 ticks: it rises in a few seconds, visibly

    private static final Deque<CommandPlan.Command> queue = new ArrayDeque<>();
    private static UUID owner;
    private static boolean magic;
    private static Abilities.Power power;
    private static String name = "";
    private static int total; // blocks in the whole build, for "230 of 659"
    private static int tick, placed, commandsRun;
    private static JsonObject last;

    static JsonObject start(MinecraftServer server, ServerPlayer sp, JsonObject args, Abilities.Style style, Abilities.Power pw) {
        String what = Actions.str(args, "what", "cottage");
        if (what.equalsIgnoreCase("stop")) return stop();
        if (busy()) return Actions.error("I'm still building the " + name + ". Say stop first if you want something else.");
        Blueprint bp;
        try {
            bp = choose(what, Actions.num(args, "people", 2), Actions.str(args, "wood", Actions.str(args, "block", "")));
        } catch (BlueprintException e) {
            return Actions.error(e.getMessage());
        }
        if (bp == null) {
            return Actions.error("I don't have a blueprint for " + what + ". I can build a cottage for as many people as you like "
                    + "(and any schematic you put in the blueprints folder).");
        }
        // where: the ground the player looks at (the porch goes there, the door just behind it)
        ServerLevel level = Mc.level(sp);
        BlockPos base;
        HitResult hit = sp.pick(24, 1f, false);
        if (hit instanceof BlockHitResult bh && hit.getType() == HitResult.Type.BLOCK) {
            BlockPos at = bh.getBlockPos();
            base = level.getBlockState(at).canBeReplaced() ? at.below()
                    : bh.getDirection() == Direction.UP ? at : at.relative(bh.getDirection()).below();
        } else {
            base = sp.blockPosition().relative(sp.getDirection(), 4).below();
        }
        Direction f = sp.getDirection();
        Placement p = Placement.inFront(bp, base.getX(), base.getY(), base.getZ(), f.getStepX(), f.getStepZ(), Placement.Anchor.FRONT_CENTER);
        int[] box = p.box();
        BlockPos me = sp.blockPosition();
        if (me.getX() >= box[0] && me.getX() <= box[3] && me.getZ() >= box[2] && me.getZ() <= box[5]
                && me.getY() >= box[1] - 1 && me.getY() <= box[4]) {
            return Actions.error("You're standing where it goes: look at a spot a few steps away.");
        }
        // never over what someone built
        int built = 0;
        for (Placement.Step s : p.steps(true)) {
            BlockPos at = new BlockPos(s.x(), s.y(), s.z());
            if (!level.isLoaded(at)) return Actions.error("That spot is too far for me to reach.");
            if (!natural(level.getBlockState(at))) built++;
        }
        if (built > 0) {
            JsonObject r = Actions.error("There's something built where it would go (" + built + " blocks): pick an open spot, "
                    + "or clear it first. I never build over what you made.");
            r.addProperty("inTheWay", built);
            return r;
        }
        List<CommandPlan.Command> plan = CommandPlan.of(p, true);
        Map<String, Integer> needs = bp.materials();
        boolean free = style == Abilities.Style.MAGIC || sp.getAbilities().instabuild;
        JsonObject r = Actions.ok();
        r.addProperty("building", bp.name());
        r.addProperty("size", bp.width() + "x" + bp.length() + ", " + bp.height() + " high");
        r.addProperty("blocks", bp.solidBlocks());
        r.add("materials", json(needs, 10));
        if (!free) {
            Map<String, Integer> have = GameRecipes.pockets(sp), missing = new LinkedHashMap<>();
            needs.forEach((item, n) -> { if (have.getOrDefault(item, 0) < n) missing.put(item, n - have.getOrDefault(item, 0)); });
            if (!missing.isEmpty()) {
                JsonObject e = Actions.error("Not enough for the " + bp.name() + " yet: grounded, I build only with what you have.");
                e.addProperty("building", bp.name());
                e.add("needs", json(needs, 20));
                e.add("missing", json(missing, 20));
                Map<String, Integer> craftable = craftable(server, missing, have);
                if (!craftable.isEmpty()) e.add("youCouldCraft", json(craftable, 10));
                return e;
            }
        }
        queue.clear();
        queue.addAll(plan);
        owner = sp.getUUID();
        magic = free;
        power = pw;
        name = bp.name();
        Undo.begin(name.replace('_', ' '), level, free); // (#129: "undo that" puts it all back)
        total = bp.solidBlocks();
        tick = placed = commandsRun = 0;
        last = null;
        r.addProperty("how", free ? "magic: with the old words the world obeys (/fill, /setblock)" : "from your pockets, block by block");
        int seconds = free ? plan.size() * MAGIC_EVERY / 20 : p.steps(true).size() * GROUNDED_EVERY / 20;
        r.addProperty("seconds", Math.max(1, seconds));
        r.addProperty("doorAt", "where you're looking, facing you");
        r.addProperty("at", base.getX() + " " + base.getY() + " " + base.getZ()); // (to lead there later, #179)
        LOG.info("blueprint {} for {} at {} {} {} ({} commands, {})", bp.name(), sp.getGameProfile().name(), base.getX(),
                base.getY(), base.getZ(), plan.size(), free ? "magic" : "grounded");
        return r;
    }

    /** The cottage generator for houses, else a schematic file whose name has the words asked. */
    static Blueprint choose(String what, int people, String wood) {
        // a blueprint file by its exact name first ("village_plains_small_house_1" is a file, not "a house")
        String exact = what == null ? "" : what.trim().toLowerCase(Locale.ROOT).replace(' ', '_');
        for (Path dir : folders()) {
            for (String ext : new String[]{".nbt", ".schem", ".litematic"}) {
                Path file = dir.resolve(exact + ext);
                if (!exact.isEmpty() && Files.isRegularFile(file)) {
                    try {
                        return Blueprints.read(file);
                    } catch (Exception e) {
                        LOG.warn("couldn't read blueprint {}: {}", file, e.toString());
                    }
                }
            }
        }
        if (House.names(what)) return House.cottage(people, wood);
        String want = what.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9 ]", " ").trim();
        for (Path dir : folders()) {
            if (!Files.isDirectory(dir)) continue;
            try (var files = Files.list(dir)) {
                for (Path file : (Iterable<Path>) files::iterator) {
                    String n = file.getFileName().toString().toLowerCase(Locale.ROOT);
                    if (!(n.endsWith(".nbt") || n.endsWith(".schem") || n.endsWith(".litematic"))) continue;
                    String base = n.replaceAll("\\.(nbt|schem|litematic)$", "").replace('_', ' ').replace('-', ' ');
                    boolean all = true;
                    for (String w : want.split("\\s+")) if (w.length() > 2 && !base.contains(w)) all = false;
                    if (all) return Blueprints.read(file);
                }
            } catch (java.io.IOException e) {
                LOG.warn("couldn't read blueprints in {}: {}", dir, e.toString());
            }
        }
        return null;
    }

    public static List<Path> folders() {
        Path config = net.fabricmc.loader.api.FabricLoader.getInstance().getConfigDir();
        Path game = net.fabricmc.loader.api.FabricLoader.getInstance().getGameDir();
        // (yours first: a file of yours with the same name as one of the game's wins; #181: the game's own structures)
        return List.of(config.resolve("kindredspirit").resolve("blueprints"), game.resolve("schematics"),
                config.resolve("kindredspirit").resolve(dev.kindredspirit.blueprint.GameStructures.FOLDER));
    }

    /** Ground, stone, sand, plants, trees, snow, water: what she may build over (and clear). */
    static boolean natural(BlockState st) {
        return st.isAir() || st.canBeReplaced() || Mc.soil(st) || st.is(BlockTags.SAND) || st.is(BlockTags.LEAVES)
                || st.is(BlockTags.LOGS) || st.is(BlockTags.BASE_STONE_OVERWORLD) || st.is(BlockTags.FLOWERS)
                || st.is(BlockTags.SAPLINGS) || st.is(Blocks.GRAVEL) || st.is(Blocks.SNOW_BLOCK) || st.is(Blocks.CLAY)
                || st.is(BlockTags.ICE) || st.is(Mc.blockTag("coal_ores"))
                || st.is(BlockTags.IRON_ORES) || st.is(BlockTags.COPPER_ORES) || st.is(Blocks.MOSS_BLOCK)
                || st.is(Blocks.SUGAR_CANE) || st.is(Blocks.BAMBOO) || st.is(Blocks.PUMPKIN) || st.is(Blocks.MELON);
    }

    private static Map<String, Integer> craftable(MinecraftServer server, Map<String, Integer> missing, Map<String, Integer> have) {
        Map<String, Integer> out = new LinkedHashMap<>();
        try {
            CraftPlanner planner = new CraftPlanner(GameRecipes.from(server.getRecipeManager(), server.registryAccess()));
            missing.forEach((item, n) -> {
                if (planner.knows(item) && planner.plan(item, n, have).canMakeNow()) out.put(item, n);
            });
        } catch (RuntimeException e) {
            LOG.warn("crafting check failed: {}", e.toString());
        }
        return out;
    }

    public static JsonObject stop() {
        if (queue.isEmpty()) return Actions.error("I'm not building anything.");
        int left = queue.size();
        queue.clear();
        JsonObject r = Actions.ok();
        r.addProperty("stopped", true);
        r.addProperty("placed", placed);
        r.addProperty("notDone", left);
        last = r;
        return r;
    }

    public static boolean busy() {
        return !queue.isEmpty();
    }

    /** What she's building and how far along, or null when she isn't (the snapshot, the HUD). */
    public static JsonObject progress() {
        if (queue.isEmpty()) return null;
        JsonObject o = new JsonObject();
        o.addProperty("what", "building " + name.replace('_', ' '));
        o.addProperty("done", Math.min(placed, total));
        o.addProperty("total", total);
        return o;
    }

    /** How the last build ended (for the brain or the sandbox), or null. */
    public static JsonObject lastResult() {
        return last;
    }

    /** Every server tick (next to Builder.tick). */
    public static void tick(MinecraftServer server) {
        if (queue.isEmpty()) return;
        if (++tick % (magic ? MAGIC_EVERY : GROUNDED_EVERY) != 0) return;
        ServerPlayer sp = server.getPlayerList().getPlayer(owner);
        if (sp == null) {
            queue.clear();
            return;
        }
        ServerLevel level = Mc.level(sp);
        if (magic) {
            // nothing to clear there: no command, and no wait for it
            while (!queue.isEmpty() && queue.peek().first().kind() == Placement.Kind.CLEAR && queue.peek().steps().stream()
                    .allMatch(st -> level.getBlockState(new BlockPos(st.x(), st.y(), st.z())).isAir())) {
                placed += queue.poll().blocks();
            }
            if (queue.isEmpty()) {
                finish();
                return;
            }
            CommandPlan.Command c = queue.poll();
            for (Placement.Step st : c.steps()) Undo.recordOnly(level, new BlockPos(st.x(), st.y(), st.z())); // (#129)
            JsonObject r = Commands.run(server, sp, c.text(), power == null ? Abilities.Power.HELPER : power, false);
            if (!r.has("ok") || !r.get("ok").getAsBoolean()) LOG.info("blueprint command failed: {} -> {}", c.text(), r);
            commandsRun++;
            placed += c.blocks();
            sparkle(level, c.first());
            if (commandsRun % 3 == 1) visit(c.first());
        } else {
            // grounded: one block of the current command, from the pockets
            CommandPlan.Command c = queue.peek();
            Placement.Step s = c.steps().get(c.steps().size() - remaining(c));
            Undo.record(level, new BlockPos(s.x(), s.y(), s.z())); // (#129)
            if (!placeGrounded(level, sp, s)) {
                queue.clear();
                last = Actions.error("I ran out of " + Materials.of(s.state()).keySet().stream().findFirst().orElse("blocks")
                        .replace("minecraft:", "").replace('_', ' ') + " after " + placed + " blocks.");
                return;
            }
            placed++;
            if (decrement(c) == 0) queue.poll();
            if (placed % 6 == 1) visit(s);
        }
        if (queue.isEmpty()) finish();
    }

    private static void finish() {
        JsonObject r = Actions.ok();
        r.addProperty("built", name);
        r.addProperty("blocks", placed);
        last = r;
        LOG.info("blueprint {} done: {} blocks", name, placed);
    }

    private static final Map<CommandPlan.Command, Integer> left = new java.util.IdentityHashMap<>();

    private static int remaining(CommandPlan.Command c) {
        return left.computeIfAbsent(c, k -> k.blocks());
    }

    private static int decrement(CommandPlan.Command c) {
        int n = remaining(c) - 1;
        if (n <= 0) left.remove(c);
        else left.put(c, n);
        return n;
    }

    private static boolean placeGrounded(ServerLevel level, ServerPlayer sp, Placement.Step s) {
        BlockPos at = new BlockPos(s.x(), s.y(), s.z());
        BlockState now = level.getBlockState(at);
        if (s.kind() == Placement.Kind.CLEAR) {
            if (now.isAir()) return true;
            for (ItemStack drop : Block.getDrops(now, level, at, level.getBlockEntity(at), sp, sp.getMainHandItem())) {
                Mc.give(sp, drop);
            }
            level.destroyBlock(at, false, sp);
            return true;
        }
        BlockState st = state(s.state());
        if (st == null) return true; // a block this game doesn't know: skipped
        for (Map.Entry<String, Integer> e : Materials.of(s.state()).entrySet()) {
            Item it = Mc.item(net.minecraft.resources.Identifier.parse(e.getKey()));
            for (int i = 0; i < e.getValue(); i++) if (!take(sp, it)) return false;
        }
        if (!now.isAir() && !now.canBeReplaced()) level.destroyBlock(at, true, sp);
        level.setBlock(at, st, 3);
        level.playSound(null, at, st.getSoundType().getPlaceSound(), SoundSource.BLOCKS, 0.8f, 1.0f);
        return true;
    }

    static BlockState state(BlockSpec spec) {
        try {
            return BlockStateParser.parseForBlock(Mc.blocks(), spec.toString(), false).blockState();
        } catch (Exception e) {
            LOG.info("unknown block in a blueprint: {}", spec);
            return null;
        }
    }

    private static boolean take(ServerPlayer sp, Item it) {
        for (ItemStack s : Mc.items(sp)) {
            if (s.is(it)) {
                s.shrink(1);
                return true;
            }
        }
        return false;
    }

    private static void sparkle(ServerLevel level, Placement.Step s) {
        level.sendParticles(ParticleTypes.END_ROD, s.x() + 0.5, s.y() + 0.6, s.z() + 0.5, 6, 0.4, 0.3, 0.4, 0.02);
        if (s.kind() != Placement.Kind.CLEAR) {
            BlockState st = state(s.state());
            if (st != null) level.playSound(null, new BlockPos(s.x(), s.y(), s.z()), st.getSoundType().getPlaceSound(),
                    SoundSource.BLOCKS, 0.6f, 1.2f);
        }
    }

    private static void visit(Placement.Step s) {
        try {
            double x = s.x() + 0.5, y = s.y() + 1.6, z = s.z() + 0.5;
            net.minecraft.client.Minecraft.getInstance().execute(() -> KindredSpiritClient.get().companion().life.visit(x, y, z, 1.2,
                    System.nanoTime() / 1e9));
        } catch (RuntimeException ignored) {
            // (no companion here: the building still happens)
        }
    }

    private static JsonObject json(Map<String, Integer> m, int max) {
        JsonObject o = new JsonObject();
        int i = 0;
        for (Map.Entry<String, Integer> e : m.entrySet()) {
            if (i++ >= max) break;
            o.addProperty(e.getKey().replace("minecraft:", ""), e.getValue());
        }
        return o;
    }
}
