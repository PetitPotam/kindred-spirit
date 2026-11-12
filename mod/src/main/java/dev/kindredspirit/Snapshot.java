package dev.kindredspirit;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import dev.kindredspirit.util.Direction8;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.EntityHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Describes the game to the brain: read-only, built on the game thread about once a second
 * (every two seconds on low quality). Only reads what your own client already knows.
 */
public final class Snapshot {
    private Snapshot() {}

    /** Where the player is heading, when she leads the way (else: where they look). Set by the client. */
    public static volatile double headingX, headingZ;

    /**
     * The first danger in the direction the player is heading, up to 5 blocks: lava, or a drop of 5+
     * blocks (and whether it ends in water). Walls stop the look-ahead. Empty when all is fine.
     */
    static JsonArray hazards(Minecraft mc, LocalPlayer p) {
        JsonArray out = new JsonArray();
        net.minecraft.world.level.Level l = mc.level;
        double hx = headingX, hz = headingZ;
        if (hx == 0 && hz == 0) {
            Vec3 v = p.getViewVector(1f);
            hx = v.x;
            hz = v.z;
        }
        double len = Math.sqrt(hx * hx + hz * hz);
        if (len < 1e-3) return out;
        hx /= len;
        hz /= len;
        int y = p.getBlockY();
        BlockPos feet = p.blockPosition();
        for (BlockPos q : BlockPos.betweenClosed(feet.offset(-1, -1, -1), feet.offset(1, 0, 1))) {
            if (l.getFluidState(q).is(net.minecraft.tags.FluidTags.LAVA)) {
                out.add(hazard("lava", 1, 0, p, q));
                return out;
            }
        }
        for (int d = 2; d <= 5; d++) {
            int bx = (int) Math.floor(p.getX() + hx * d), bz = (int) Math.floor(p.getZ() + hz * d);
            BlockPos at = new BlockPos(bx, y, bz);
            if (!l.getBlockState(at).getCollisionShape(l, at).isEmpty()
                    && !l.getBlockState(at.above()).getCollisionShape(l, at.above()).isEmpty()) break; // a wall
            for (int dy = -1; dy <= 0; dy++) {
                if (l.getFluidState(at.offset(0, dy, 0)).is(net.minecraft.tags.FluidTags.LAVA)) {
                    out.add(hazard("lava", d, 0, p, at));
                    return out;
                }
            }
            BlockPos below = at.below();
            if (l.getBlockState(below).getCollisionShape(l, below).isEmpty() && l.getFluidState(below).isEmpty()) {
                int depth = 1;
                BlockPos q = below.below();
                while (depth < 30 && l.getBlockState(q).getCollisionShape(l, q).isEmpty() && l.getFluidState(q).isEmpty()) {
                    depth++;
                    q = q.below();
                }
                if (depth >= 5) {
                    boolean lava = l.getFluidState(q).is(net.minecraft.tags.FluidTags.LAVA);
                    boolean water = l.getFluidState(q).is(net.minecraft.tags.FluidTags.WATER);
                    out.add(hazard(lava ? "drop_lava" : water ? "drop_water" : "drop", d, depth, p, at));
                    return out;
                }
            }
        }
        return out;
    }

    private static JsonObject hazard(String kind, int distance, int depth, LocalPlayer p, BlockPos at) {
        JsonObject h = new JsonObject();
        h.addProperty("kind", kind);
        h.addProperty("distance", distance);
        if (depth > 0) h.addProperty("depth", depth);
        h.addProperty("direction", Direction8.relative(p.getYRot(), at.getX() + 0.5 - p.getX(), at.getZ() + 0.5 - p.getZ()));
        return h;
    }

    public static JsonObject build(Minecraft mc, int scanRadius) {
        LocalPlayer p = mc.player;
        JsonObject o = new JsonObject();
        o.addProperty("type", "snapshot");
        if (p == null || mc.level == null) return o;

        o.addProperty("health", round1(p.getHealth()));
        o.addProperty("maxHealth", round1(p.getMaxHealth()));
        o.addProperty("food", p.getFoodData().getFoodLevel());
        o.addProperty("saturation", round1(p.getFoodData().getSaturationLevel()));
        o.addProperty("armor", p.getArmorValue());
        o.addProperty("air", p.getAirSupply());
        o.addProperty("maxAir", p.getMaxAirSupply());
        o.addProperty("onFire", p.isOnFire());
        o.addProperty("gamemode", mc.gameMode == null ? "unknown" : mc.gameMode.getPlayerMode().getName());
        if (p.getLastDamageSource() != null) o.addProperty("lastDamage", p.getLastDamageSource().getMsgId());

        JsonArray effects = new JsonArray();
        for (MobEffectInstance e : p.getActiveEffects()) {
            JsonObject eo = new JsonObject();
            eo.addProperty("id", e.getEffect().unwrapKey().map(k -> k.location().toString()).orElse("?"));
            eo.addProperty("level", e.getAmplifier() + 1);
            eo.addProperty("seconds", e.getDuration() / 20);
            effects.add(eo);
        }
        o.add("effects", effects);

        BlockPos pos = p.blockPosition();
        JsonObject where = new JsonObject();
        where.addProperty("x", pos.getX());
        where.addProperty("y", pos.getY());
        where.addProperty("z", pos.getZ());
        where.addProperty("dimension", mc.level.dimension().location().toString());
        where.addProperty("biome", mc.level.getBiome(pos).unwrapKey().map(k -> k.location().toString()).orElse("?"));
        where.addProperty("facing", p.getDirection().getName());
        where.addProperty("yaw", round1(p.getYRot()));
        where.addProperty("skyVisible", mc.level.canSeeSky(pos.above()));
        where.addProperty("light", mc.level.getMaxLocalRawBrightness(pos));
        o.add("where", where);

        long dayTime = mc.level.getDayTime();
        JsonObject time = new JsonObject();
        time.addProperty("day", dayTime / 24000 + 1);
        time.addProperty("timeOfDay", dayTime % 24000);
        time.addProperty("raining", mc.level.isRaining());
        time.addProperty("thundering", mc.level.isThundering());
        o.add("time", time);

        // inventory, merged by item: "32 cobblestone" rather than every slot
        o.addProperty("holding", itemId(p.getMainHandItem()));
        o.addProperty("offhand", itemId(p.getOffhandItem()));
        Map<String, Integer> counts = new LinkedHashMap<>();
        for (ItemStack s : p.getInventory().items) {
            if (!s.isEmpty()) counts.merge(itemId(s), s.getCount(), Integer::sum);
        }
        JsonObject inv = new JsonObject();
        counts.entrySet().stream().sorted(Map.Entry.<String, Integer>comparingByValue().reversed()).limit(30)
                .forEach(e -> inv.addProperty(e.getKey(), e.getValue()));
        o.add("inventory", inv);
        JsonArray armor = new JsonArray();
        for (ItemStack s : p.getInventory().armor) if (!s.isEmpty()) armor.add(itemId(s));
        o.add("wearing", armor);

        // what you are looking at, up to 24 blocks away
        JsonObject look = new JsonObject();
        Entity target = mc.crosshairPickEntity;
        HitResult hit = p.pick(24, 1f, false);
        if (target != null) {
            look.addProperty("entity", BuiltInRegistries.ENTITY_TYPE.getKey(target.getType()).toString());
            look.addProperty("distance", round1(target.distanceTo(p)));
        } else if (hit instanceof BlockHitResult bh && hit.getType() == HitResult.Type.BLOCK) {
            BlockPos bp = bh.getBlockPos();
            look.addProperty("block", BuiltInRegistries.BLOCK.getKey(mc.level.getBlockState(bp).getBlock()).toString());
            look.addProperty("distance", round1(Math.sqrt(bp.getCenter().distanceToSqr(p.getEyePosition()))));
        } else if (hit instanceof EntityHitResult eh) {
            look.addProperty("entity", BuiltInRegistries.ENTITY_TYPE.getKey(eh.getEntity().getType()).toString());
        }
        o.add("lookingAt", look);

        // hostile mobs nearby, closest first, with a direction you can understand
        List<Mob> mobs = mc.level.getEntitiesOfClass(Mob.class, p.getBoundingBox().inflate(scanRadius),
                m -> m instanceof Enemy && m.isAlive());
        mobs.sort(Comparator.comparingDouble(m -> m.distanceToSqr(p)));
        JsonArray hostiles = new JsonArray();
        for (Mob m : mobs.subList(0, Math.min(12, mobs.size()))) {
            JsonObject mo = new JsonObject();
            mo.addProperty("type", BuiltInRegistries.ENTITY_TYPE.getKey(m.getType()).toString());
            mo.addProperty("distance", round1(m.distanceTo(p)));
            mo.addProperty("direction", Direction8.relative(p.getYRot(), m.getX() - p.getX(), m.getZ() - p.getZ()));
            mo.addProperty("above", round1(m.getY() - p.getY()));
            hostiles.add(mo);
        }
        o.add("hostiles", hostiles);

        // animals and villagers nearby: babies, your pets, species she hasn't met yet
        java.util.List<net.minecraft.world.entity.LivingEntity> near = mc.level.getEntitiesOfClass(
                net.minecraft.world.entity.LivingEntity.class, p.getBoundingBox().inflate(32),
                e -> e.isAlive() && (e instanceof net.minecraft.world.entity.animal.Animal
                        || e instanceof net.minecraft.world.entity.npc.AbstractVillager));
        near.sort(Comparator.comparingDouble(e -> e.distanceToSqr(p)));
        JsonArray animals = new JsonArray();
        for (net.minecraft.world.entity.LivingEntity e : near.subList(0, Math.min(20, near.size()))) {
            JsonObject ao = new JsonObject();
            ao.addProperty("id", e.getId());
            ao.addProperty("type", BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString());
            ao.addProperty("distance", round1(e.distanceTo(p)));
            ao.addProperty("direction", Direction8.relative(p.getYRot(), e.getX() - p.getX(), e.getZ() - p.getZ()));
            ao.addProperty("baby", e.isBaby());
            ao.addProperty("tamed", e instanceof net.minecraft.world.entity.OwnableEntity own
                    && p.getUUID().equals(own.getOwnerUUID()));
            if (e.hasCustomName()) ao.addProperty("name", e.getCustomName().getString());
            animals.add(ao);
        }
        o.add("animals", animals);
        o.add("hazards", hazards(mc, p));
        return o;
    }

    private static String itemId(ItemStack s) {
        return s.isEmpty() ? "" : BuiltInRegistries.ITEM.getKey(s.getItem()).toString();
    }

    private static double round1(double v) {
        return Math.round(v * 10) / 10.0;
    }
}
