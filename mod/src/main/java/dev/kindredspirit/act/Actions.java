package dev.kindredspirit.act;

import com.google.gson.JsonObject;
import com.mojang.datafixers.util.Pair;
import dev.kindredspirit.util.Direction8;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.HolderSet;
import net.minecraft.core.Registry;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.tags.StructureTags;
import net.minecraft.tags.TagKey;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.levelgen.structure.BuiltinStructures;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.phys.AABB;

import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.function.Function;

/**
 * Does what the brain asks ("find diamonds", "where's a village", "protect me"), within what
 * {@link Abilities} allows. Reading the world happens on your client (it only sees what your game
 * already loaded). Changing it goes through the singleplayer server, the same way a command
 * would, so it works in singleplayer and when you host LAN, and is refused on other servers.
 * Every answer is a small JSON the AI turns into words.
 */
public final class Actions {
    private Actions() {}

    /** Where the last find/locate pointed, so "take me there" works right after. */
    public static volatile double[] lastTarget;
    /** When the last thing found was an animal: its id, so a guided trip follows it as it walks. */
    public static volatile int lastTargetEntity = -1;
    /** The player she found last (by name), so leading to them keeps up as they move, even far away. */
    public static volatile String lastTargetPlayer;
    /** Who last hurt whom (players, on this world's server): protect pushes a friend who just hit you, playfully. */
    private static final Map<java.util.UUID, Object[]> hurtBy = new java.util.concurrent.ConcurrentHashMap<>();

    /** What each player did lately, as the world's game saw it (placed, broke, hit, killed, got hurt): so she never
     *  has to guess what a friend is doing. Kept two minutes, a few dozen entries each. */
    private static final Map<java.util.UUID, java.util.Deque<Object[]>> did = new java.util.concurrent.ConcurrentHashMap<>();

    public static void playerDid(net.minecraft.world.entity.player.Player p, String what) {
        if (!(p instanceof ServerPlayer) || p instanceof net.fabricmc.fabric.api.entity.FakePlayer) return; // (her hands aren't the player)
        var q = did.computeIfAbsent(p.getUUID(), k -> new java.util.concurrent.ConcurrentLinkedDeque<>());
        q.addLast(new Object[]{System.currentTimeMillis(), what});
        while (q.size() > 40) q.pollFirst();
    }

    /** "placed 12 oak log, broke 3 stone, hit a sheep (the last 10 s ago)", or "" if nothing in two minutes. */
    public static String activityOf(java.util.UUID id) {
        var q = did.get(id);
        if (q == null) return "";
        long now = System.currentTimeMillis();
        java.util.Map<String, Integer> n = new java.util.LinkedHashMap<>();
        long last = 0;
        for (Object[] e : q) {
            if (now - (long) e[0] > 120000) continue;
            n.merge((String) e[1], 1, Integer::sum);
            last = Math.max(last, (long) e[0]);
        }
        if (n.isEmpty()) return "";
        StringBuilder b = new StringBuilder();
        n.forEach((k, v) -> {
            String[] w = k.split(" ", 2);
            b.append(b.length() > 0 ? ", " : "").append(w[0]).append(" ").append(v > 1 ? v + " " : "a ").append(w.length > 1 ? w[1] : "");
        });
        return b + " (the last " + Math.max(1, (now - last) / 1000) + " s ago)";
    }

    /** The world's game saw a player hurt another (registered on the server: see KindredSpiritClient). */
    public static void playerHurt(ServerPlayer victim, ServerPlayer attacker) {
        if (victim != attacker) hurtBy.put(victim.getUUID(), new Object[]{attacker.getUUID(), System.currentTimeMillis()});
    }

    private static final Map<String, Object> STRUCTURES = Map.ofEntries(
            Map.entry("village", StructureTags.VILLAGE), Map.entry("mineshaft", StructureTags.MINESHAFT),
            Map.entry("shipwreck", StructureTags.SHIPWRECK), Map.entry("ruined_portal", StructureTags.RUINED_PORTAL),
            Map.entry("ocean_ruin", StructureTags.OCEAN_RUIN), Map.entry("monument", BuiltinStructures.OCEAN_MONUMENT),
            Map.entry("mansion", BuiltinStructures.WOODLAND_MANSION), Map.entry("stronghold", BuiltinStructures.STRONGHOLD),
            Map.entry("fortress", BuiltinStructures.FORTRESS), Map.entry("bastion", BuiltinStructures.BASTION_REMNANT),
            Map.entry("desert_temple", BuiltinStructures.DESERT_PYRAMID), Map.entry("jungle_temple", BuiltinStructures.JUNGLE_TEMPLE),
            Map.entry("witch_hut", BuiltinStructures.SWAMP_HUT), Map.entry("igloo", BuiltinStructures.IGLOO),
            Map.entry("outpost", BuiltinStructures.PILLAGER_OUTPOST), Map.entry("ancient_city", BuiltinStructures.ANCIENT_CITY),
            Map.entry("trail_ruins", BuiltinStructures.TRAIL_RUINS), Map.entry("trial_chambers", BuiltinStructures.TRIAL_CHAMBERS),
            Map.entry("end_city", BuiltinStructures.END_CITY), Map.entry("buried_treasure", BuiltinStructures.BURIED_TREASURE));

    public static java.util.Set<String> structureNames() {
        return STRUCTURES.keySet();
    }

    /**
     * Runs one action; the future completes with {"ok": true, ...} or {"ok": false, "error": ...}.
     * Called on the game thread.
     */
    public static CompletableFuture<JsonObject> run(String action, JsonObject args, Abilities.Power power, Abilities.Style style) {
        Abilities.Ability a = Abilities.ability(action);
        if (a == null) return done(error("I don't know how to " + action + "."));
        if (!Abilities.allowed(a, power, style)) return done(error(Abilities.refusal(a, power, style)));
        Minecraft mc = Minecraft.getInstance();
        if (mc.player == null || mc.level == null) return done(error("We're not in a world."));
        try {
            return switch (a) {
                case FIND_ORE -> done(findOre(mc, str(args, "ore", "diamond")));
                case FIND_ANIMAL -> done(findAnimal(mc, str(args, "animal", "sheep")));
                case FIND_BLOCK -> done(findBlock(mc, str(args, "block", "flower")));
                case FIND_PLAYER -> { // the world's game knows everyone, even far away (your game only knows who's near)
                    if (mc.getSingleplayerServer() == null && remote == null) yield done(findPlayer(mc, str(args, "name", ""), str(args, "from", "")));
                    yield onServer(mc, a, args, power, style).thenApply(r -> {
                        String err = r.has("error") ? r.get("error").getAsString() : "";
                        if (err.contains("isn't done on the server")) { // (an older Kindred hosts: ask your own game)
                            JsonObject[] out = new JsonObject[1];
                            Minecraft.getInstance().executeBlocking(() -> out[0] = findPlayer(Minecraft.getInstance(),
                                    str(args, "name", ""), str(args, "from", "")));
                            return out[0];
                        }
                        if (r.has("x") && r.has("z")) {
                            lastTarget = new double[]{r.get("x").getAsDouble() + 0.5, r.has("y") ? r.get("y").getAsDouble() + 0.5 : 64,
                                    r.get("z").getAsDouble() + 0.5};
                            lastTargetEntity = r.has("entity") ? r.get("entity").getAsInt() : -1;
                            lastTargetPlayer = r.has("player") ? r.get("player").getAsString() : null;
                        }
                        return r;
                    });
                }
                case LOCATE, PROTECT, PLACE_TORCH, HARVEST, BUILD, GIVE_ITEM, GIVE_EFFECT, SET_TIME, SET_WEATHER, COMMAND,
                     JOB, BLUEPRINT, CRAFT_HELP, TRADES -> onServer(mc, a, args, power, style);
                case GUIDE, STOP_GUIDE, FOLLOW_PLAYER -> done(ok()); // handled by the companion itself
            };
        } catch (RuntimeException e) {
            return done(error("That didn't work: " + e.getMessage()));
        }
    }

    // ------------------------------------------------------------------ reading the world (client)

    /** Nearest ore of a kind within 24 blocks, among the blocks your game has loaded. */
    static JsonObject findOre(Minecraft mc, String ore) {
        String kind = Places.oreKind(ore);
        LocalPlayer p = mc.player;
        BlockPos center = p.blockPosition();
        int r = 24;
        BlockPos best = null;
        double bestD = Double.MAX_VALUE;
        int count = 0;
        BlockPos.MutableBlockPos m = new BlockPos.MutableBlockPos();
        for (int dy = -r; dy <= r; dy++) {
            for (int dx = -r; dx <= r; dx++) {
                for (int dz = -r; dz <= r; dz++) {
                    m.set(center.getX() + dx, center.getY() + dy, center.getZ() + dz);
                    Block b = mc.level.getBlockState(m).getBlock();
                    if (b == Blocks.AIR || b == Blocks.STONE || b == Blocks.DEEPSLATE || b == Blocks.DIRT) continue;
                    if (!Places.isOre(BuiltInRegistries.BLOCK.getKey(b).getPath(), kind)) continue;
                    count++;
                    double d = dx * dx + dy * dy + dz * dz;
                    if (d < bestD) {
                        bestD = d;
                        best = m.immutable();
                    }
                }
            }
        }
        if (best == null) {
            JsonObject r0 = ok();
            r0.addProperty("found", false);
            r0.addProperty("searched", "24 blocks around the player (only what the game has loaded)");
            return r0;
        }
        JsonObject res = place(p, best.getX() + 0.5, best.getY() + 0.5, best.getZ() + 0.5);
        res.addProperty("found", true);
        res.addProperty("ore", kind);
        res.addProperty("blocksOfIt", count);
        return res;
    }

    /**
     * Nearest block of a kind within 24 blocks ("flower", "pumpkin", "sugar cane", "chest", "water", "tree"):
     * a group by tag (any flower, any log, any leaves, any bed), else any block whose id has those words.
     */
    static JsonObject findBlock(Minecraft mc, String what) {
        String w = what.toLowerCase(Locale.ROOT).replace("minecraft:", "").trim().replaceAll("\\s+", "_");
        if (w.endsWith("s") && !w.endsWith("ss") && !w.equals("grass")) w = w.substring(0, w.length() - 1);
        final String want = w;
        java.util.function.Predicate<net.minecraft.world.level.block.state.BlockState> match = switch (want) {
            case "flower" -> st -> st.is(net.minecraft.tags.BlockTags.FLOWERS);
            case "tree", "log", "wood" -> st -> st.is(net.minecraft.tags.BlockTags.LOGS);
            case "leave", "leaf" -> st -> st.is(net.minecraft.tags.BlockTags.LEAVES);
            case "bed" -> st -> st.is(net.minecraft.tags.BlockTags.BEDS);
            case "water" -> st -> st.getFluidState().is(net.minecraft.tags.FluidTags.WATER) && st.getFluidState().isSource();
            case "lava" -> st -> st.getFluidState().is(net.minecraft.tags.FluidTags.LAVA);
            default -> st -> BuiltInRegistries.BLOCK.getKey(st.getBlock()).getPath().contains(want);
        };
        LocalPlayer p = mc.player;
        BlockPos center = p.blockPosition();
        int r = 24;
        BlockPos best = null;
        double bestD = Double.MAX_VALUE;
        int count = 0;
        BlockPos.MutableBlockPos m = new BlockPos.MutableBlockPos();
        for (int dy = -12; dy <= 12; dy++) {
            for (int dx = -r; dx <= r; dx++) {
                for (int dz = -r; dz <= r; dz++) {
                    m.set(center.getX() + dx, center.getY() + dy, center.getZ() + dz);
                    net.minecraft.world.level.block.state.BlockState st = mc.level.getBlockState(m);
                    if (st.isAir() || !match.test(st)) continue;
                    count++;
                    double d = dx * dx + dy * dy * 2 + dz * dz; // the same level counts as closer
                    if (d < bestD) {
                        bestD = d;
                        best = m.immutable();
                    }
                }
            }
        }
        if (best == null) {
            JsonObject r0 = ok();
            r0.addProperty("found", false);
            r0.addProperty("searched", "24 blocks around the player");
            return r0;
        }
        JsonObject res = place(p, best.getX() + 0.5, best.getY() + 0.5, best.getZ() + 0.5);
        res.addProperty("found", true);
        res.addProperty("block", BuiltInRegistries.BLOCK.getKey(mc.level.getBlockState(best).getBlock()).getPath().replace('_', ' '));
        res.addProperty("howMany", count);
        return res;
    }

    /** Nearest animal (or villager, or any creature) of a kind, among those your game has loaded. */
    static JsonObject findAnimal(Minecraft mc, String what) {
        String want = Places.creatureKind(what);
        LocalPlayer p = mc.player;
        java.util.List<net.minecraft.world.entity.LivingEntity> all = mc.level.getEntitiesOfClass(
                net.minecraft.world.entity.LivingEntity.class, p.getBoundingBox().inflate(ANIMAL_RANGE),
                e -> e.isAlive() && e != p && !(e instanceof net.minecraft.world.entity.player.Player)
                        && Places.isCreature(BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).getPath(), want));
        if (all.isEmpty()) {
            JsonObject r0 = ok();
            r0.addProperty("found", false);
            r0.addProperty("searched", "about " + (int) ANIMAL_RANGE + " blocks around the player (what the game has loaded)");
            return r0;
        }
        all.sort(java.util.Comparator.comparingDouble(e -> e.distanceToSqr(p)));
        net.minecraft.world.entity.LivingEntity best = all.get(0);
        int group = 0;
        for (var e : all) if (e.distanceToSqr(best) < 16 * 16) group++;
        JsonObject res = place(p, best.getX(), best.getY(), best.getZ());
        lastTargetEntity = best.getId();
        res.addProperty("found", true);
        res.addProperty("animal", BuiltInRegistries.ENTITY_TYPE.getKey(best.getType()).getPath());
        res.addProperty("howManyThere", group);
        res.addProperty("totalAround", all.size());
        return res;
    }

    static final double ANIMAL_RANGE = 96;

    // ------------------------------------------------------------------ the server side (singleplayer / LAN host)

    /**
     * In a friend's LAN world whose game has Kindred: asks their game to do it for you (visiting Pip, see
     * GuestBridge.visit). Set by the client; null when there's no such world.
     */
    public static java.util.function.BiFunction<String, JsonObject, CompletableFuture<JsonObject>> remote;

    private static CompletableFuture<JsonObject> onServer(Minecraft mc, Abilities.Ability a, JsonObject args,
                                                          Abilities.Power power, Abilities.Style style) {
        MinecraftServer server = mc.getSingleplayerServer();
        if (server == null) {
            if (remote != null) {
                JsonObject req = new JsonObject();
                req.add("args", args);
                req.addProperty("power", power.name());
                req.addProperty("style", style.name());
                return remote.apply(a.id(), req);
            }
            return done(error("I can only do that in singleplayer, when you host LAN, or in a friend's world whose game has Kindred."));
        }
        CompletableFuture<JsonObject> f = new CompletableFuture<>();
        java.util.UUID you = mc.player.getUUID();
        args.addProperty("_power", power.name()); // (commands: what this power may run)
        server.execute(() -> {
            ServerPlayer sp = server.getPlayerList().getPlayer(you);
            f.complete(sp == null ? error("player not found on the server") : serverSide(server, sp, a, args, style));
        });
        return f;
    }

    /** The world-changing powers, on the server (yours, or a friend's for your visiting Pip), for player sp. */
    public static JsonObject serverSide(MinecraftServer s, ServerPlayer sp, Abilities.Ability a, JsonObject args,
                                        Abilities.Style style) {
        try {
            return switch (a) {
                case LOCATE -> locate(s, sp, str(args, "what", "village"));
                case PROTECT -> args.has("poke") && args.get("poke").getAsBoolean()
                        ? poke(sp, target(s, sp, str(args, "to", "")))
                        : protect(target(s, sp, str(args, "to", "")));
                // (for a friend: from where THEY stand, with THEIR inventory: "for" names them)
                case PLACE_TORCH -> placeTorch(target(s, sp, str(args, "for", "")), style);
                case HARVEST -> harvest(target(s, sp, str(args, "for", "")));
                case BUILD -> Builder.start(s, target(s, sp, str(args, "for", "")), args, style);
                // jobs and blueprints (grounded through her hands, magic through the command powers), expertise
                case JOB -> dev.kindredspirit.job.Jobs.action(target(s, sp, str(args, "for", "")), args, style == Abilities.Style.MAGIC);
                case BLUEPRINT -> BlueprintBuild.start(s, target(s, sp, str(args, "for", "")), args, style,
                        Abilities.power(str(args, "_power", "HELPER")));
                case CRAFT_HELP -> dev.kindredspirit.job.Jobs.craftHelp(target(s, sp, str(args, "for", "")), str(args, "item", ""),
                        num(args, "count", 1));
                case TRADES -> dev.kindredspirit.job.Jobs.trades(target(s, sp, str(args, "for", "")));
                case GIVE_ITEM -> give(target(s, sp, str(args, "to", "")), str(args, "item", ""), num(args, "count", 1));
                case GIVE_EFFECT -> effect(target(s, sp, str(args, "to", "")), str(args, "effect", ""));
                case SET_TIME -> setTime(s, str(args, "time", "day"));
                case SET_WEATHER -> setWeather(s, str(args, "weather", "clear"));
                case FIND_PLAYER -> findPlayerServer(s, sp, str(args, "name", ""), str(args, "from", ""));
                case COMMAND -> Commands.run(s, target(s, sp, str(args, "for", "")), str(args, "command", ""), Abilities.power(str(args, "_power", "HELPER")),
                        args.has("harmfulAsked") && args.get("harmfulAsked").getAsBoolean());
                default -> error("That isn't done on the server.");
            };
        } catch (RuntimeException e) {
            return error("That didn't work: " + e.getMessage());
        }
    }

    static ServerPlayer serverPlayer(MinecraftServer server, LocalPlayer p) {
        ServerPlayer sp = server.getPlayerList().getPlayer(p.getUUID());
        if (sp == null) throw new IllegalStateException("player not found on the server");
        return sp;
    }

    @SuppressWarnings("unchecked")
    static JsonObject locate(MinecraftServer server, ServerPlayer sp, String what) {
        Player p = sp;
        ServerLevel level = sp.serverLevel();
        BlockPos from = sp.blockPosition();
        String key = what.toLowerCase(Locale.ROOT).replace("minecraft:", "").trim().replace(' ', '_');
        if (key.endsWith("s") && STRUCTURES.containsKey(key.substring(0, key.length() - 1))) key = key.substring(0, key.length() - 1);
        Object s = STRUCTURES.get(key);
        if (s != null) {
            Registry<Structure> reg = level.registryAccess().registryOrThrow(Registries.STRUCTURE);
            Optional<? extends HolderSet<Structure>> set = s instanceof TagKey<?> tag
                    ? reg.getTag((TagKey<Structure>) tag)
                    : reg.getHolder((ResourceKey<Structure>) s).map(HolderSet::direct);
            if (set.isEmpty()) return error("There are no " + what + "s in this world.");
            Pair<BlockPos, Holder<Structure>> found = level.getChunkSource().getGenerator()
                    .findNearestMapStructure(level, set.get(), from, 100, false);
            if (found == null) return error("I couldn't find a " + what + " anywhere near (in this dimension).");
            BlockPos at = found.getFirst();
            JsonObject r = place(p, at.getX() + 0.5, sp.getY(), at.getZ() + 0.5);
            r.addProperty("what", key);
            return r;
        }
        // otherwise a biome, like "cherry grove" or "minecraft:mushroom_fields"
        ResourceLocation id = ResourceLocation.tryParse(key.contains(":") ? key : "minecraft:" + key);
        Registry<Biome> biomes = level.registryAccess().registryOrThrow(Registries.BIOME);
        if (id == null || !biomes.containsKey(id)) {
            return error("I don't know a place called " + what + ". I can find structures like "
                    + String.join(", ", STRUCTURES.keySet()) + ", or any biome.");
        }
        ResourceKey<Biome> bk = ResourceKey.create(Registries.BIOME, id);
        Pair<BlockPos, Holder<Biome>> found = level.findClosestBiome3d(h -> h.is(bk), from, 6400, 32, 64);
        if (found == null) return error("No " + what + " biome within 6400 blocks.");
        BlockPos at = found.getFirst();
        JsonObject r = place(p, at.getX() + 0.5, at.getY(), at.getZ() + 0.5);
        r.addProperty("what", id.getPath());
        return r;
    }

    /** Knocks hostile mobs within 8 blocks away from you (no damage). */
    static JsonObject protect(ServerPlayer sp) {
        ServerLevel level = sp.serverLevel();
        int n = 0;
        // monsters within 10 blocks, and any that is after the player from further away (a skeleton or a
        // pillager shoots from 15 blocks; a witch throws from 10+)
        for (Mob m : level.getEntitiesOfClass(Mob.class, new AABB(sp.blockPosition()).inflate(24), e -> e instanceof Enemy
                && e.isAlive() && (e.distanceTo(sp) <= 10 || e.getTarget() == sp
                || (e instanceof net.minecraft.world.entity.monster.RangedAttackMob && e.distanceTo(sp) <= 18)))) {
            m.setTarget(null); // dazed: it forgets about the player for a moment
            m.knockback(2.2, sp.getX() - m.getX(), sp.getZ() - m.getZ());
            // dazed for a few seconds, so it doesn't walk straight back (no damage)
            m.addEffect(new net.minecraft.world.effect.MobEffectInstance(
                    net.minecraft.world.effect.MobEffects.MOVEMENT_SLOWDOWN, 80, 2, false, false));
            m.hurtMarked = true; // send the new velocity to the client right away
            level.sendParticles(ParticleTypes.POOF, m.getX(), m.getY() + 0.5, m.getZ(), 8, 0.3, 0.3, 0.3, 0.02);
            n++;
        }
        JsonObject r = ok();
        r.addProperty("pushedAway", n);
        Object[] hb = hurtBy.get(sp.getUUID()); // a friend who just hit them: a playful shove (no harm)
        if (hb != null && System.currentTimeMillis() - (long) hb[1] < 15000) {
            ServerPlayer other = sp.server.getPlayerList().getPlayer((java.util.UUID) hb[0]);
            if (other != null && other.level() == sp.level() && other.distanceTo(sp) <= 12) {
                other.knockback(1.6, sp.getX() - other.getX(), sp.getZ() - other.getZ());
                other.hurtMarked = true;
                level.sendParticles(ParticleTypes.POOF, other.getX(), other.getY() + 1, other.getZ(), 10, 0.3, 0.4, 0.3, 0.02);
                r.addProperty("pushedPlayer", other.getGameProfile().getName());
                hurtBy.remove(sp.getUUID());
            }
        }
        return r;
    }

    /** A playful poke on a player (on request): a small shove away from you, a puff, her giggle. No harm. */
    static JsonObject poke(ServerPlayer you, ServerPlayer who) {
        if (who == you) return error("Poke who? Name another player.");
        double dx = who.getX() - you.getX(), dz = who.getZ() - you.getZ(), d = Math.max(0.1, Math.hypot(dx, dz));
        who.knockback(0.9, -dx / d, -dz / d);
        who.hurtMarked = true;
        who.serverLevel().sendParticles(ParticleTypes.POOF, who.getX(), who.getY() + 1, who.getZ(), 10, 0.3, 0.4, 0.3, 0.02);
        who.serverLevel().playSound(null, who.blockPosition(), net.minecraft.sounds.SoundEvents.CHICKEN_EGG,
                net.minecraft.sounds.SoundSource.PLAYERS, 1f, 1.6f);
        JsonObject r = ok();
        r.addProperty("poked", who.getGameProfile().getName());
        return r;
    }

    /** A torch at your feet or right beside you. Grounded: uses one of your torches. */
    static JsonObject placeTorch(ServerPlayer sp, Abilities.Style style) {
        ServerLevel level = sp.serverLevel();
        boolean free = style == Abilities.Style.MAGIC || sp.getAbilities().instabuild;
        int slot = -1;
        if (!free) {
            for (int i = 0; i < sp.getInventory().getContainerSize(); i++) {
                if (sp.getInventory().getItem(i).is(Items.TORCH)) {
                    slot = i;
                    break;
                }
            }
            if (slot < 0) return error("You have no torches, and in grounded style I can only place yours. Craft some with coal and sticks!");
        }
        BlockPos base = sp.blockPosition();
        int[][] offsets = {{0, 0}, {1, 0}, {-1, 0}, {0, 1}, {0, -1}, {1, 1}, {-1, -1}, {1, -1}, {-1, 1}};
        for (int[] o : offsets) {
            BlockPos at = base.offset(o[0], 0, o[1]);
            if (level.getBlockState(at).isAir() && Blocks.TORCH.defaultBlockState().canSurvive(level, at)) {
                level.setBlockAndUpdate(at, Blocks.TORCH.defaultBlockState());
                if (slot >= 0) sp.getInventory().getItem(slot).shrink(1);
                JsonObject r = ok();
                r.addProperty("placedAt", at.getX() + " " + at.getY() + " " + at.getZ());
                r.addProperty("usedYourTorch", slot >= 0);
                return r;
            }
        }
        return error("There's no good spot for a torch right here (it needs a solid floor). Try one step away.");
    }

    /** Magic style only: makes items appear in your inventory (or at your feet if it's full). */
    static JsonObject give(ServerPlayer sp, String item, int count) {
        String key = item.toLowerCase(Locale.ROOT).trim().replace(' ', '_');
        ResourceLocation id = ResourceLocation.tryParse(key.contains(":") ? key : "minecraft:" + key);
        if (id == null || !BuiltInRegistries.ITEM.containsKey(id)) return error("There's no item called " + item + ".");
        Item it = BuiltInRegistries.ITEM.get(id);
        int n = Math.max(1, Math.min(count, it.getDefaultMaxStackSize() * 4)); // up to four stacks
        int left = n;
        while (left > 0) {
            int k = Math.min(left, it.getDefaultMaxStackSize());
            ItemStack stack = new ItemStack(it, k);
            if (!sp.getInventory().add(stack)) sp.drop(stack, false);
            left -= k;
        }
        JsonObject r = ok();
        r.addProperty("gave", n + " " + id.getPath());
        r.addProperty("to", sp.getGameProfile().getName());
        return r;
    }

    /** Who an action is for: you, or another player on your LAN world named (even roughly) in "to". */
    static ServerPlayer target(MinecraftServer server, ServerPlayer me, String to) {
        if (to == null || to.isBlank() || to.equalsIgnoreCase("me") || to.equalsIgnoreCase("player")) return me;
        Player other = Players.match(server.getPlayerList().getPlayers(), to);
        if (other == null) throw new IllegalArgumentException("nobody called " + to + " is here");
        return (ServerPlayer) other;
    }

    /** Magic style: a potion effect for a while (or health and food at once). */
    static JsonObject effect(ServerPlayer sp, String what) {
        String key = what.toLowerCase(Locale.ROOT).trim().replace(' ', '_');
        JsonObject r = ok();
        r.addProperty("to", sp.getGameProfile().getName());
        switch (key) {
            case "health", "heal", "hearts", "healing", "instant_health" -> {
                sp.setHealth(sp.getMaxHealth());
                r.addProperty("healed", "back to full health");
                return r;
            }
            case "food", "hunger", "feed", "saturation" -> {
                sp.getFoodData().eat(20, 20f);
                r.addProperty("fed", "not hungry any more");
                return r;
            }
            default -> { }
        }
        var effect = switch (key) {
            case "haste", "dig_speed", "mining" -> net.minecraft.world.effect.MobEffects.DIG_SPEED;
            case "night_vision", "see_in_the_dark" -> net.minecraft.world.effect.MobEffects.NIGHT_VISION;
            case "speed", "swiftness", "fast" -> net.minecraft.world.effect.MobEffects.MOVEMENT_SPEED;
            case "regeneration", "regen" -> net.minecraft.world.effect.MobEffects.REGENERATION;
            case "fire_resistance" -> net.minecraft.world.effect.MobEffects.FIRE_RESISTANCE;
            case "water_breathing" -> net.minecraft.world.effect.MobEffects.WATER_BREATHING;
            case "jump_boost", "jump", "leaping" -> net.minecraft.world.effect.MobEffects.JUMP;
            case "strength" -> net.minecraft.world.effect.MobEffects.DAMAGE_BOOST;
            case "resistance" -> net.minecraft.world.effect.MobEffects.DAMAGE_RESISTANCE;
            case "slow_falling", "feather_falling" -> net.minecraft.world.effect.MobEffects.SLOW_FALLING;
            case "invisibility" -> net.minecraft.world.effect.MobEffects.INVISIBILITY;
            case "luck" -> net.minecraft.world.effect.MobEffects.LUCK;
            case "conduit_power" -> net.minecraft.world.effect.MobEffects.CONDUIT_POWER;
            case "dolphins_grace" -> net.minecraft.world.effect.MobEffects.DOLPHINS_GRACE;
            // playful ones, short: a friend slowed down, floating up a moment, glowing
            case "slowness", "slow", "slow_down" -> net.minecraft.world.effect.MobEffects.MOVEMENT_SLOWDOWN;
            case "levitation", "levitate", "float", "fly_up" -> net.minecraft.world.effect.MobEffects.LEVITATION;
            case "glowing", "glow", "outline" -> net.minecraft.world.effect.MobEffects.GLOWING;
            default -> null;
        };
        if (effect == null && key.matches("poison|wither|instant_damage|harming|damage|blindness|nausea|hunger|weakness|"
                + "darkness|bad_omen|mining_fatigue|unluck|bad_luck|infested|oozing|weaving|wind_charged")) {
            return error("That one would hurt them: I only do kind or playful effects (slowness, a little levitation, glowing).");
        }
        if (effect == null) return error("There's no effect called " + what + " I can give (haste, night vision, speed, "
                + "regeneration, fire resistance, water breathing, jump boost, strength, resistance, slow falling, "
                + "invisibility, or health and food).");
        boolean strong = key.equals("regeneration") || key.equals("regen") || key.equals("strength") || key.equals("resistance");
        int seconds = effect == net.minecraft.world.effect.MobEffects.LEVITATION ? 4
                : effect == net.minecraft.world.effect.MobEffects.MOVEMENT_SLOWDOWN ? 20
                : effect == net.minecraft.world.effect.MobEffects.GLOWING ? 60 : strong ? 45 : 180;
        sp.addEffect(new net.minecraft.world.effect.MobEffectInstance(effect, seconds * 20, 0));
        r.addProperty("effect", key.replace('_', ' '));
        r.addProperty("seconds", seconds);
        return r;
    }

    /** Another player in your world (LAN), by name (even roughly: "robin" for riverrobin). */
    static JsonObject findPlayer(Minecraft mc, String name, String from) {
        LocalPlayer you = mc.player;
        java.util.List<Player> all = new java.util.ArrayList<>();
        for (Player o : mc.level.players()) if (o.isAlive()) all.add(o);
        // who asks (a friend, in chat): the answer is from where they stand
        Player p = from.isBlank() ? you : java.util.Objects.requireNonNullElse(Players.match(all, from), you);
        java.util.List<Player> others = new java.util.ArrayList<>();
        for (Player o : all) if (o != p) others.add(o);
        if (others.isEmpty()) return error("Nobody else is here: it's just the two of you.");
        boolean meansYou = p != you && (name.toLowerCase(Locale.ROOT).matches(".*\\b(player|host|you|your|owner)\\b.*")
                || Players.score(Players.squash(you.getGameProfile().getName()), Players.squash(name)) >= 2);
        Player who = meansYou ? you : name.isBlank() && others.size() == 1 ? others.get(0) : Players.match(others, name);
        if (who == null) {
            JsonObject r = error("Nobody called " + name + " here.");
            r.addProperty("hereNow", String.join(", ", others.stream().map(o -> o.getGameProfile().getName()).toList()));
            return r;
        }
        JsonObject res = place(p, who.getX(), who.getY(), who.getZ());
        lastTargetPlayer = who.getGameProfile().getName();
        lastTargetEntity = who.getId();
        res.addProperty("found", true);
        res.addProperty("player", who.getGameProfile().getName());
        return res;
    }

    /**
     * Another player in the world, asked of the world's game (it knows everyone, near or far). A friend
     * asking "where am I?" gets where they are from the player she lives with.
     */
    static JsonObject findPlayerServer(MinecraftServer server, ServerPlayer you, String name, String from) {
        java.util.List<ServerPlayer> all = new java.util.ArrayList<>();
        for (ServerPlayer o : server.getPlayerList().getPlayers()) if (o.isAlive() && !o.isSpectator()) all.add(o);
        ServerPlayer asker = from.isBlank() ? you : java.util.Objects.requireNonNullElse(Players.match(all, from), you);
        String n = name.toLowerCase(Locale.ROOT).trim();
        boolean self = asker != you && (n.isEmpty() || n.matches("(me|myself|i|where am i)")
                || Players.score(Players.squash(asker.getGameProfile().getName()), Players.squash(name)) >= 2);
        if (self) { // "where am I?": from where the player she lives with stands
            JsonObject r = place(you, asker.getX(), asker.getY(), asker.getZ());
            r.addProperty("self", true);
            String host = you.getGameProfile().getName();
            String dir = r.get("direction").getAsString().replace("-", " on their ");
            r.addProperty("where", r.get("distance").getAsLong() + " blocks from " + host + ", " + dir + " ("
                    + r.get("compass").getAsString() + " of them)");
            r.addProperty("player", asker.getGameProfile().getName());
            r.addProperty("fromPlayer", you.getGameProfile().getName());
            r.addProperty("note", "This is where " + asker.getGameProfile().getName() + " is, seen from "
                    + you.getGameProfile().getName() + " (the player you live beside).");
            if (asker.level() != you.level()) r.addProperty("otherDimension", asker.level().dimension().location().getPath());
            return r;
        }
        java.util.List<ServerPlayer> others = new java.util.ArrayList<>();
        for (ServerPlayer o : all) if (o != asker) others.add(o);
        if (others.isEmpty()) return error("Nobody else is in this world right now.");
        boolean meansYou = asker != you && (n.matches(".*\\b(player|host|you|your|owner)\\b.*")
                || Players.score(Players.squash(you.getGameProfile().getName()), Players.squash(name)) >= 2);
        ServerPlayer who = meansYou ? you : name.isBlank() && others.size() == 1 ? others.get(0) : Players.match(others, name);
        if (who == null) {
            JsonObject r = error("Nobody called " + name + " in this world.");
            r.addProperty("hereNow", String.join(", ", others.stream().map(o -> o.getGameProfile().getName()).toList()));
            return r;
        }
        if (who.level() != asker.level()) {
            JsonObject r = error(who.getGameProfile().getName() + " is in another dimension ("
                    + who.level().dimension().location().getPath().replace('_', ' ') + ").");
            r.addProperty("player", who.getGameProfile().getName());
            return r;
        }
        JsonObject res = place(asker, who.getX(), who.getY(), who.getZ());
        lastTargetEntity = who.getId();
        lastTargetPlayer = who.getGameProfile().getName();
        res.addProperty("found", true);
        res.addProperty("player", who.getGameProfile().getName());
        res.addProperty("entity", who.getId());
        var held = who.getMainHandItem();
        res.addProperty("holding", held.isEmpty() ? "nothing" : BuiltInRegistries.ITEM.getKey(held.getItem()).getPath().replace('_', ' '));
        String act = activityOf(who.getUUID());
        res.addProperty("lately", act.isEmpty() ? "nothing the world noticed in the last two minutes" : act);
        return res;
    }

    /** Where a player is now (for leading to someone who walks, even far away): the world's game knows. */
    public static CompletableFuture<JsonObject> whereIs(Minecraft mc, String name) {
        MinecraftServer server = mc.getSingleplayerServer();
        JsonObject args = new JsonObject();
        args.addProperty("name", name);
        if (server == null) {
            if (remote == null) return done(error("no world's game to ask"));
            JsonObject req = new JsonObject();
            req.add("args", args);
            req.addProperty("power", "ADVISOR");
            req.addProperty("style", "GROUNDED");
            return remote.apply("find_player", req);
        }
        CompletableFuture<JsonObject> f = new CompletableFuture<>();
        java.util.UUID you = mc.player.getUUID();
        server.execute(() -> {
            ServerPlayer sp = server.getPlayerList().getPlayer(you);
            ServerPlayer who = sp == null ? null : Players.match(server.getPlayerList().getPlayers(), name);
            if (who == null) f.complete(error("gone"));
            else {
                JsonObject r = ok();
                r.addProperty("x", who.getX());
                r.addProperty("y", who.getY());
                r.addProperty("z", who.getZ());
                f.complete(r);
            }
        });
        return f;
    }

    static JsonObject setTime(MinecraftServer server, String time) {
        long t = switch (time.toLowerCase(Locale.ROOT).trim()) {
            case "sunrise", "dawn", "morning" -> 0;
            case "noon", "midday" -> 6000;
            case "sunset", "evening", "dusk" -> 12000;
            case "night" -> 13000;
            case "midnight" -> 18000;
            default -> 1000; // "day"
        };
        for (ServerLevel l : server.getAllLevels()) { // the next time it is that time, never backwards
            long now = l.getDayTime(), target = now / 24000 * 24000 + t;
            l.setDayTime(target < now ? target + 24000 : target);
        }
        JsonObject r = ok();
        r.addProperty("time", time);
        return r;
    }

    static JsonObject setWeather(MinecraftServer server, String weather) {
        ServerLevel l = server.getLevel(Level.OVERWORLD);
        if (l == null) return error("No overworld?");
        switch (weather.toLowerCase(Locale.ROOT).trim()) {
            case "rain" -> l.setWeatherParameters(0, 6000, true, false);
            case "thunder", "storm" -> l.setWeatherParameters(0, 6000, true, true);
            default -> l.setWeatherParameters(12000, 0, false, false);
        }
        JsonObject r = ok();
        r.addProperty("weather", weather);
        return r;
    }

    // ------------------------------------------------------------------ helpers

    /** Where something is, in words the AI can say: distance, direction from where you look, height. */
    static JsonObject place(Player p, double x, double y, double z) {
        lastTarget = new double[]{x, y, z};
        lastTargetEntity = -1;
        JsonObject r = ok();
        r.addProperty("x", Math.round(x - 0.5));
        r.addProperty("y", Math.round(y - 0.5));
        r.addProperty("z", Math.round(z - 0.5));
        double dx = x - p.getX(), dz = z - p.getZ();
        r.addProperty("distance", Math.round(Math.sqrt(dx * dx + dz * dz)));
        r.addProperty("direction", Direction8.relative(p.getYRot(), dx, dz));
        r.addProperty("compass", Places.compass(dx, dz));
        long up = Math.round(y - p.getY());
        r.addProperty("heightDifference", up);
        // a ready sentence, so the AI doesn't have to (and can't get it wrong)
        String dir = Direction8.relative(p.getYRot(), dx, dz).replace("-", " on your ");
        String height = up > 2 ? ", " + up + " blocks up" : up < -2 ? ", " + (-up) + " blocks down" : ", at your level";
        r.addProperty("where", Math.round(Math.sqrt(dx * dx + dz * dz)) + " blocks away, " + dir + " ("
                + Places.compass(dx, dz) + ")" + height);
        return r;
    }

    /**
     * Breaks what the player is looking at (within 6 blocks): a whole tree if it's a log, else that one
     * block. What it drops goes into their inventory, as if mined with the item in their hand (in
     * grounded style no better tool than yours: stone by hand crumbles to nothing). Never unbreakable
     * blocks, never anything that holds items (chests, furnaces...).
     */
    static JsonObject harvest(ServerPlayer sp) {
        ServerLevel level = sp.serverLevel();
        net.minecraft.world.phys.HitResult hit = sp.pick(6, 1f, false);
        BlockPos start = hit instanceof net.minecraft.world.phys.BlockHitResult bh
                && hit.getType() == net.minecraft.world.phys.HitResult.Type.BLOCK ? bh.getBlockPos() : null;
        // looking at leaves, or at nothing: they want wood, so the nearest trunk (asked for wood, she
        // once broke the leaf in front of her and cheered)
        if (start == null || level.getBlockState(start).is(net.minecraft.tags.BlockTags.LEAVES)) {
            BlockPos log = nearestLog(level, start != null ? start : sp.blockPosition(), 6);
            if (log != null) start = log;
            else if (start == null) return error("The player isn't looking at a block, and there's no tree close enough (6 blocks).");
        }
        net.minecraft.world.level.block.state.BlockState first = level.getBlockState(start);
        if (first.getDestroySpeed(level, start) < 0 || level.getBlockEntity(start) != null || first.isAir()) {
            return error("That one won't budge (or it holds things).");
        }
        java.util.List<BlockPos> todo = new java.util.ArrayList<>();
        boolean tree = first.is(net.minecraft.tags.BlockTags.LOGS);
        if (tree) { // the whole trunk and branches: connected logs, up from where you look, at most 96
            java.util.ArrayDeque<BlockPos> q = new java.util.ArrayDeque<>(java.util.List.of(start));
            java.util.Set<BlockPos> seen = new java.util.HashSet<>(q);
            while (!q.isEmpty() && todo.size() < 96) {
                BlockPos b = q.poll();
                todo.add(b);
                for (BlockPos n : BlockPos.betweenClosed(b.offset(-1, 0, -1), b.offset(1, 1, 1))) {
                    BlockPos m = n.immutable();
                    if (m.getY() >= start.getY() && !seen.contains(m) && level.getBlockState(m).is(net.minecraft.tags.BlockTags.LOGS)) {
                        seen.add(m);
                        q.add(m);
                    }
                }
            }
        } else {
            todo.add(start);
        }
        ItemStack tool = sp.getMainHandItem();
        int broken = 0;
        java.util.Map<String, Integer> got = new java.util.LinkedHashMap<>();
        for (BlockPos b : todo) {
            net.minecraft.world.level.block.state.BlockState st = level.getBlockState(b);
            for (ItemStack drop : Block.getDrops(st, level, b, level.getBlockEntity(b), sp, tool)) {
                got.merge(BuiltInRegistries.ITEM.getKey(drop.getItem()).getPath(), drop.getCount(), Integer::sum);
                if (!sp.getInventory().add(drop)) sp.drop(drop, false);
            }
            level.destroyBlock(b, false, sp);
            broken++;
        }
        JsonObject r = ok();
        r.addProperty("broken", broken);
        r.addProperty("what", tree ? "a tree (" + broken + " logs)" : BuiltInRegistries.BLOCK.getKey(first.getBlock()).getPath());
        StringBuilder items = new StringBuilder();
        got.forEach((k, v) -> items.append(items.length() > 0 ? ", " : "").append(v).append(" ").append(k.replace('_', ' ')));
        r.addProperty("gaveThePlayer", items.length() > 0 ? items.toString() : "nothing (it crumbled: the right tool is needed)");
        if (items.length() == 0) { // (a broken leaf is not a success: say it as it is)
            r.addProperty("ok", false);
            r.addProperty("error", "You broke " + r.get("what").getAsString().replace('_', ' ')
                    + ", but nothing came of it: the player got nothing.");
        }
        return r;
    }

    /** The nearest log within r blocks (the trunk of the tree they mean). */
    static BlockPos nearestLog(ServerLevel level, BlockPos around, int r) {
        BlockPos best = null;
        double bestD = Double.MAX_VALUE;
        for (BlockPos b : BlockPos.betweenClosed(around.offset(-r, -r, -r), around.offset(r, r, r))) {
            if (!level.getBlockState(b).is(net.minecraft.tags.BlockTags.LOGS)) continue;
            double d = b.distSqr(around);
            if (d < bestD) {
                bestD = d;
                best = b.immutable();
            }
        }
        return best;
    }

    public static JsonObject ok() {
        JsonObject o = new JsonObject();
        o.addProperty("ok", true);
        return o;
    }

    public static JsonObject error(String why) {
        JsonObject o = new JsonObject();
        o.addProperty("ok", false);
        o.addProperty("error", why);
        return o;
    }

    private static CompletableFuture<JsonObject> done(JsonObject o) {
        return CompletableFuture.completedFuture(o);
    }

    static String str(JsonObject o, String k, String d) {
        return o != null && o.has(k) && !o.get(k).isJsonNull() ? o.get(k).getAsString() : d;
    }

    static int num(JsonObject o, String k, int d) {
        try {
            return o != null && o.has(k) ? o.get(k).getAsInt() : d;
        } catch (RuntimeException e) {
            return d;
        }
    }
}
