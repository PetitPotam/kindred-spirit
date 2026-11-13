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

    /** Who she floats beside: you (null), or another player in the world (on LAN, when you ask her). */
    public java.util.UUID follow;

    private final Behavior.Senses senses = new Behavior.Senses();
    private final long start = System.nanoTime();
    private long lastFrame;
    private int tickCount;

    public Companion(KindredConfig cfg) {
        life = new Behavior(cfg.offsetRight, cfg.offsetUp, cfg.offsetForward, 0.2 * cfg.size, System.nanoTime(), cfg.life);
    }

    public double now() {
        return (System.nanoTime() - start) / 1e9;
    }

    /** Her mouth moves with the words while there's no voice (voice off, muted, or none came), #29. */
    public long mouthUntil;

    public void say(String text, double audioSeconds, long nowMs) {
        subtitle = text == null ? "" : text;
        long readMs = 2500 + 60L * subtitle.length();
        long audioMs = (long) (audioSeconds * 1000) + 1500;
        subtitleUntil = nowMs + Math.max(readMs, audioMs);
        mouthUntil = audioSeconds > 0 ? 0 : nowMs + 300 + 55L * subtitle.length(); // (about as long as saying it)
    }

    /** How open her mouth is with no voice playing: a speaking rhythm while the silent line lasts, else closed. */
    public float silentMouth(long nowMs) {
        if (nowMs >= mouthUntil) return 0f;
        double t = nowMs / 1000.0;
        double v = 0.45 + 0.35 * Math.sin(t * 13.0) * (0.6 + 0.4 * Math.sin(t * 3.7));
        return (float) Math.max(0, Math.min(1, v));
    }

    /** More voice arrived for the same line: keep the subtitle up while it plays. */
    /** The next sentence of the same line (her answer streams in): the subtitle grows. */
    public void sayMore(String text, long nowMs) {
        subtitle = subtitle.isEmpty() ? text : subtitle + " " + text;
        subtitleUntil = Math.max(subtitleUntil, nowMs + 2500 + 60L * text.length());
        if (mouthUntil > 0) mouthUntil = Math.max(mouthUntil, nowMs) + 55L * text.length();
    }

    public void extend(double audioSeconds, long nowMs) {
        mouthUntil = 0; // (her voice came after all)
        subtitleUntil = Math.max(subtitleUntil, nowMs + (long) (audioSeconds * 1000) + 1500);
    }

    public boolean showSubtitle(long nowMs) {
        return !subtitle.isEmpty() && nowMs < subtitleUntil;
    }

    public enum Touch { NONE, PETTED, HIT }

    private boolean attackWasDown, wasHidden, mySneakWas;
    private final Behavior.Senses mine = new Behavior.Senses();

    /**
     * 20 times a second: tell the companion what is going on. The world scan (mobs, animals, items)
     * runs every 5th tick only and stays within a few blocks, so it costs next to nothing.
     * @return whether the player just petted or hit her
     */
    /** The player she floats beside: you, or the one she's following if they're here. */
    public Player anchor(Minecraft mc) {
        if (follow != null && mc.level != null) {
            Player other = mc.level.getPlayerByUUID(follow);
            if (other != null && other.isAlive()) return other;
        }
        return mc.player;
    }

    public Touch tick(Minecraft mc) {
        LocalPlayer p = mc.player;
        ClientLevel level = mc.level;
        if (p == null || level == null) return Touch.NONE;
        Player a = anchor(mc);
        Behavior.Senses s = senses;
        s.now = now();
        Vec3 eye = a.getEyePosition();
        Vec3 look = a.getViewVector(1f);
        s.ex = eye.x; s.ey = eye.y; s.ez = eye.z;
        s.lx = look.x; s.ly = look.y; s.lz = look.z;
        s.yawDeg = a.getYRot();
        s.speed = (a == p ? p.getDeltaMovement() : a.position().subtract(a.xo, a.yo, a.zo)).horizontalDistance() * 20;
        s.sneaking = a.isShiftKeyDown();
        HitResult hit = a == p ? mc.hitResult : null;
        Entity target = a == p ? mc.crosshairPickEntity : null;
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
        if (tickCount++ % 5 == 0) scan(a, level);
        life.tick(s, activity, mood, (x, y, z) -> {
            BlockPos pos = BlockPos.containing(x, y, z);
            return !level.getBlockState(pos).getCollisionShape(level, pos).isEmpty();
        });
        if (life.blinked) { // no way through a wall: she popped over to you
            life.blinked = false;
            for (int i = 0; i < 8; i++) {
                level.addParticle(ParticleTypes.POOF, life.x + (Math.random() - 0.5) * 0.4, life.y + (Math.random() - 0.5) * 0.4,
                        life.z + (Math.random() - 0.5) * 0.4, 0, 0.03, 0);
            }
        }
        // a puff when she leaves and when she comes back
        if (life.hidden() != wasHidden) {
            wasHidden = life.hidden();
            for (int i = 0; i < 8; i++) {
                level.addParticle(ParticleTypes.POOF, life.x + (Math.random() - 0.5) * 0.4, life.y + (Math.random() - 0.5) * 0.4,
                        life.z + (Math.random() - 0.5) * 0.4, 0, 0.03, 0);
            }
        }
        // hitting her: the attack key pressed with the crosshair right on her, and no mob, animal or
        // block in front of her (hitting a cow next to her is not hitting her)
        // (always from YOUR eyes: in light mode her body follows the host, but the hand that hits her is yours)
        boolean attack = mc.options.keyAttack.isDown() && mc.screen == null;
        Behavior.Senses me = s;
        if (a != p) {
            Vec3 myEye = p.getEyePosition(), myLook = p.getViewVector(1f);
            me = mine;
            me.ex = myEye.x; me.ey = myEye.y; me.ez = myEye.z;
            me.lx = myLook.x; me.ly = myLook.y; me.lz = myLook.z;
            me.now = s.now;
        }
        HitResult myHit = mc.hitResult;
        Entity myTarget = mc.crosshairPickEntity;
        if (myTarget != null && myTarget.getUUID().equals(dev.kindredspirit.guest.GuestBridge.hidden)) {
            myTarget = null; // her own stand-in (for friends without the mod) floats where she is: it's not in the way
            myHit = null;
        }
        double inTheWay = Double.MAX_VALUE;
        if (myTarget != null) inTheWay = myTarget.distanceTo(p) - 0.3;
        else if (myHit != null && myHit.getType() == HitResult.Type.BLOCK) inTheWay = myHit.getLocation().distanceTo(p.getEyePosition());
        boolean struck = attack && !attackWasDown && !life.hidden() && life.aimedAt(me, inTheWay);
        if (attack && !attackWasDown && a != p && System.getProperty("kindredspirit.devScript") != null) {
            double dx = life.x - me.ex, dy = life.y - me.ey, dz = life.z - me.ez;
            KindredSpiritClient.LOG.info("touch check (dev): along {} dist {} inTheWay {} target {} hidden {} struck {}",
                    String.format("%.2f", dx * me.lx + dy * me.ly + dz * me.lz), String.format("%.2f", Math.sqrt(dx * dx + dy * dy + dz * dz)),
                    inTheWay == Double.MAX_VALUE ? "nothing" : String.format("%.2f", inTheWay), myTarget, life.hidden(), struck);
        }
        if (attack && !struck) life.playerSwings(s.now); // fighting or digging: she gets out of the way
        attackWasDown = attack;
        if (struck) {
            life.play(dev.kindredspirit.life.Emote.STARTLE, s.now);
            level.addParticle(ParticleTypes.DAMAGE_INDICATOR, life.x, life.y + 0.3, life.z, 0, 0.1, 0);
            return Touch.HIT;
        }
        if (a != p) { // a friend's pat on the Pip they see (hers are noticed by the game she lives in)
            boolean sneak = p.isShiftKeyDown();
            if (sneak && !mySneakWas && !life.hidden() && life.aimedAt(me, Double.MAX_VALUE)) life.petted = true;
            mySneakWas = sneak;
        }
        if (life.petted) {
            life.petted = false;
            for (int i = 0; i < 3; i++) { // little hearts, drawn on your screen only
                level.addParticle(ParticleTypes.HEART, life.x + (Math.random() - 0.5) * 0.3,
                        life.y + 0.25 + Math.random() * 0.2, life.z + (Math.random() - 0.5) * 0.3, 0, 0.02, 0);
            }
            return Touch.PETTED;
        }
        return Touch.NONE;
    }

    private void scan(Player p, ClientLevel level) {
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
                now(), dt, activity, mood, voiceLevel, skin.floaty());
        rgb = Mood.blend(rgb, mood.rgb, 1 - (float) Math.exp(-dt * 4.0));
        float targetMouth = activity == Behavior.Activity.SPEAKING ? Math.min(1f, voiceLevel * 1.4f) : 0f;
        mouth += (targetMouth - mouth) * (float) Math.min(1, dt * 18);
    }
}
