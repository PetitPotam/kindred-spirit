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
                case FIND_PLAYER -> done(findPlayer(mc, str(args, "name", ""), str(args, "from", "")));
                case LOCATE -> onServer(mc, s -> locate(s, mc.player, str(args, "what", "village")));
                case GUIDE, STOP_GUIDE, FOLLOW_PLAYER -> done(ok()); // handled by the companion itself
                case PROTECT -> onServer(mc, s -> protect(target(s, mc.player, str(args, "to", ""))));
                case PLACE_TORCH -> onServer(mc, s -> placeTorch(s, mc.player, style));
                case HARVEST -> onServer(mc, s -> harvest(s, mc.player));
                case BUILD -> onServer(mc, s -> Builder.start(s, mc.player, args, style));
                case GIVE_ITEM -> onServer(mc, s -> give(target(s, mc.player, str(args, "to", "")), str(args, "item", ""), num(args, "count", 1)));
                case GIVE_EFFECT -> onServer(mc, s -> effect(target(s, mc.player, str(args, "to", "")), str(args, "effect", "")));
                case SET_TIME -> onServer(mc, s -> setTime(s, str(args, "time", "day")));
                case SET_WEATHER -> onServer(mc, s -> setWeather(s, str(args, "weather", "clear")));
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

    private static CompletableFuture<JsonObject> onServer(Minecraft mc, Function<MinecraftServer, JsonObject> job) {
        MinecraftServer server = mc.getSingleplayerServer();
        if (server == null) return done(error("I can only do that in singleplayer (or when you host LAN) for now."));
        CompletableFuture<JsonObject> f = new CompletableFuture<>();
        server.execute(() -> {
            try {
                f.complete(job.apply(server));
            } catch (RuntimeException e) {
                f.complete(error("That didn't work: " + e.getMessage()));
            }
        });
        return f;
    }

    static ServerPlayer serverPlayer(MinecraftServer server, LocalPlayer p) {
        ServerPlayer sp = server.getPlayerList().getPlayer(p.getUUID());
        if (sp == null) throw new IllegalStateException("player not found on the server");
        return sp;
    }

    @SuppressWarnings("unchecked")
    static JsonObject locate(MinecraftServer server, LocalPlayer p, String what) {
        ServerPlayer sp = serverPlayer(server, p);
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
        return r;
    }

    /** A torch at your feet or right beside you. Grounded: uses one of your torches. */
    static JsonObject placeTorch(MinecraftServer server, LocalPlayer p, Abilities.Style style) {
        ServerPlayer sp = serverPlayer(server, p);
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
    static ServerPlayer target(MinecraftServer server, LocalPlayer you, String to) {
        ServerPlayer me = serverPlayer(server, you);
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
            default -> null;
        };
        if (effect == null) return error("There's no effect called " + what + " I can give (haste, night vision, speed, "
                + "regeneration, fire resistance, water breathing, jump boost, strength, resistance, slow falling, "
                + "invisibility, or health and food).");
        boolean strong = key.equals("regeneration") || key.equals("regen") || key.equals("strength") || key.equals("resistance");
        int seconds = strong ? 45 : 180;
        sp.addEffect(new net.minecraft.world.effect.MobEffectInstance(effect, seconds * 20, 0));
        r.addProperty("effect", key.replace('_', ' '));
        r.addProperty("seconds", seconds);
        return r;
    }

    /** Another player in your world (LAN), by name (even roughly: "walid" for waterwalid). */
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
        lastTargetEntity = who.getId();
        res.addProperty("found", true);
        res.addProperty("player", who.getGameProfile().getName());
        return res;
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
    static JsonObject harvest(MinecraftServer server, LocalPlayer p) {
        ServerPlayer sp = serverPlayer(server, p);
        ServerLevel level = sp.serverLevel();
        net.minecraft.world.phys.HitResult hit = sp.pick(6, 1f, false);
        if (!(hit instanceof net.minecraft.world.phys.BlockHitResult bh) || hit.getType() != net.minecraft.world.phys.HitResult.Type.BLOCK) {
            return error("The player isn't looking at a block or a tree close enough (6 blocks).");
        }
        BlockPos start = bh.getBlockPos();
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
        return r;
    }

    static JsonObject ok() {
        JsonObject o = new JsonObject();
        o.addProperty("ok", true);
        return o;
    }

    static JsonObject error(String why) {
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
