package dev.kindredspirit;

import dev.kindredspirit.life.Behavior;
import dev.kindredspirit.skin.Skin;
import dev.kindredspirit.util.Mood;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.animal.Animal;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.entity.monster.Creeper;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.entity.npc.AbstractVillager;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import java.util.Comparator;
import java.util.List;

/**
 * The companion as the game sees it: feeds what the player is doing into {@link Behavior} (its
 * "life") and keeps what only matters for drawing: mood color, subtitle, mouth, skin.
 * Nothing here exists in the world: it is a picture on your screen, so saves never change.
 */
public final class Companion {
    public final Behavior life;
    public Mood mood = Mood.OFFLINE;
    /** Current color, eased toward the mood's color. */
    public int rgb = Mood.OFFLINE.rgb;
    public Behavior.Activity activity = Behavior.Activity.IDLE;
    public Skin skin = Skin.fallback();

    public String subtitle = "";
    public long subtitleUntil;
    public float mouth;

    private final Behavior.Senses senses = new Behavior.Senses();
    private final long start = System.nanoTime();
    private long lastFrame;
    private int tickCount;

    public Companion(KindredConfig cfg) {
        life = new Behavior(cfg.offsetRight, cfg.offsetUp, cfg.offsetForward, 0.2 * cfg.size, System.nanoTime());
    }

    public double now() {
        return (System.nanoTime() - start) / 1e9;
    }

    public void say(String text, double audioSeconds, long nowMs) {
        subtitle = text == null ? "" : text;
        long readMs = 2500 + 60L * subtitle.length();
        long audioMs = (long) (audioSeconds * 1000) + 1500;
        subtitleUntil = nowMs + Math.max(readMs, audioMs);
    }

    /** More voice arrived for the same line: keep the subtitle up while it plays. */
    public void extend(double audioSeconds, long nowMs) {
        subtitleUntil = Math.max(subtitleUntil, nowMs + (long) (audioSeconds * 1000) + 1500);
    }

    public boolean showSubtitle(long nowMs) {
        return !subtitle.isEmpty() && nowMs < subtitleUntil;
    }

    /**
     * 20 times a second: tell the companion what is going on. The world scan (mobs, animals, items)
     * runs every 5th tick only and stays within a few blocks, so it costs next to nothing.
     * @return true when the player just petted it
     */
    public boolean tick(Minecraft mc) {
        LocalPlayer p = mc.player;
        ClientLevel level = mc.level;
        if (p == null || level == null) return false;
        Behavior.Senses s = senses;
        s.now = now();
        Vec3 eye = p.getEyePosition();
        Vec3 look = p.getViewVector(1f);
        s.ex = eye.x; s.ey = eye.y; s.ez = eye.z;
        s.lx = look.x; s.ly = look.y; s.lz = look.z;
        s.yawDeg = p.getYRot();
        s.speed = p.getDeltaMovement().horizontalDistance() * 20;
        s.sneaking = p.isShiftKeyDown();
        HitResult hit = mc.hitResult;
        Entity target = mc.crosshairPickEntity;
        if (target != null) {
            s.hasLookHit = true;
            s.hx = target.getX(); s.hy = target.getY() + target.getBbHeight() * 0.8; s.hz = target.getZ();
        } else if (hit instanceof BlockHitResult bh && hit.getType() == HitResult.Type.BLOCK) {
            s.hasLookHit = true;
            Vec3 l = bh.getLocation();
            s.hx = l.x; s.hy = l.y; s.hz = l.z;
        } else {
            s.hasLookHit = false;
        }
        if (tickCount++ % 5 == 0) scan(p, level);
        life.tick(s, activity, mood, (x, y, z) -> {
            BlockPos pos = BlockPos.containing(x, y, z);
            return !level.getBlockState(pos).getCollisionShape(level, pos).isEmpty();
        });
        if (life.petted) {
            life.petted = false;
            for (int i = 0; i < 3; i++) { // little hearts, drawn on your screen only
                level.addParticle(ParticleTypes.HEART, life.x + (Math.random() - 0.5) * 0.3,
                        life.y + 0.25 + Math.random() * 0.2, life.z + (Math.random() - 0.5) * 0.3, 0, 0.02, 0);
            }
            return true;
        }
        return false;
    }

    private void scan(LocalPlayer p, ClientLevel level) {
        senses.threats.clear();
        senses.interests.clear();
        List<Mob> mobs = level.getEntitiesOfClass(Mob.class, p.getBoundingBox().inflate(12),
                m -> m instanceof Enemy && m.isAlive());
        mobs.sort(Comparator.comparingDouble(m -> m.distanceToSqr(p)));
        for (Mob m : mobs) senses.threats.add(new double[]{m.getX(), m.getY(), m.getZ(), m instanceof Creeper ? 1 : 0});
        for (Entity e : level.getEntities(p, p.getBoundingBox().inflate(10), e -> e.isAlive()
                && (e instanceof Animal || e instanceof AbstractVillager || e instanceof ItemEntity || e instanceof Player))) {
            if (senses.interests.size() >= 6) break;
            senses.interests.add(new double[]{e.getX(), e.getY(), e.getZ()});
        }
    }

    /** Every drawn frame: move smoothly toward what {@link #tick} decided. */
    public void frame(Player player, float partialTick, float voiceLevel) {
        long nanos = System.nanoTime();
        double dt = lastFrame == 0 ? 0 : Math.min(0.1, (nanos - lastFrame) / 1e9);
        lastFrame = nanos;
        Vec3 eye = player.getEyePosition(partialTick);
        Vec3 look = player.getViewVector(partialTick);
        life.frame(eye.x, eye.y, eye.z, player.getViewYRot(partialTick), look.x, look.y, look.z,
                now(), dt, activity, mood, voiceLevel, skin.shape() == Skin.Shape.WISP);
        rgb = Mood.blend(rgb, mood.rgb, 1 - (float) Math.exp(-dt * 4.0));
        float targetMouth = activity == Behavior.Activity.SPEAKING ? Math.min(1f, voiceLevel * 1.4f) : 0f;
        mouth += (targetMouth - mouth) * (float) Math.min(1, dt * 18);
    }
}
