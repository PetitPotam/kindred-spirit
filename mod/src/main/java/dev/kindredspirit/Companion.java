package dev.kindredspirit;

import dev.kindredspirit.util.Mood;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.Vec3;

/**
 * Where the companion is and how it feels, updated once per drawn frame. Nothing here exists in
 * the world: it is a picture drawn on your screen only, so your save files never change.
 */
public final class Companion {
    public enum Activity { IDLE, LISTENING, THINKING, SPEAKING }

    // position (smoothed, so it drifts after you instead of being glued to the camera)
    public double x, y, z;
    private boolean placed;

    public Mood mood = Mood.OFFLINE;
    /** Current color, eased toward the mood's color. */
    public int rgb = Mood.OFFLINE.rgb;
    public Activity activity = Activity.IDLE;

    public String subtitle = "";
    public long subtitleUntil;

    /** Bounce phase in "hops"; one hop = 1.0. */
    public float hop;
    public float squish;      // 0 = round, >0 = flattened
    public float lift;        // height of the current hop, blocks
    public float mouth;       // 0 closed .. 1 open
    public float blink;       // 0 open .. 1 shut
    public float shiver;      // sideways wobble when scared
    private long nextBlink = 3000;
    private long lastNanos;
    private float clock;      // seconds since start

    public void say(String text, double audioSeconds, long now) {
        subtitle = text == null ? "" : text;
        long readMs = 2500 + 60L * subtitle.length();
        long audioMs = (long) (audioSeconds * 1000) + 1500;
        subtitleUntil = now + Math.max(readMs, audioMs);
    }

    /** More voice arrived for the same line: keep the subtitle up while it plays. */
    public void extend(double audioSeconds, long now) {
        subtitleUntil = Math.max(subtitleUntil, now + (long) (audioSeconds * 1000) + 1500);
    }

    public boolean showSubtitle(long now) {
        return !subtitle.isEmpty() && now < subtitleUntil;
    }

    /** Advance the animation by real time (not game ticks, so it stays smooth when the game is paused or lagging). */
    public void update(Player player, float partialTick, KindredConfig cfg, float voiceLevel) {
        long nanos = System.nanoTime();
        float dt = lastNanos == 0 ? 0f : Math.min(0.1f, (nanos - lastNanos) / 1e9f);
        lastNanos = nanos;
        clock += dt;

        // Target: beside your eyes, following where you face horizontally (not your pitch, so
        // looking down at your feet does not drop it under the floor).
        Vec3 eye = player.getEyePosition(partialTick);
        double yaw = Math.toRadians(player.getViewYRot(partialTick));
        double fx = -Math.sin(yaw), fz = Math.cos(yaw);
        double rx = -Math.cos(yaw), rz = -Math.sin(yaw);
        double tx = eye.x + rx * cfg.offsetRight + fx * cfg.offsetForward;
        double ty = eye.y + cfg.offsetUp;
        double tz = eye.z + rz * cfg.offsetRight + fz * cfg.offsetForward;
        double dist2 = (tx - x) * (tx - x) + (ty - y) * (ty - y) + (tz - z) * (tz - z);
        if (!placed || dist2 > 144) { // first frame or teleport: appear right there
            x = tx; y = ty; z = tz;
            placed = true;
        } else {
            double k = 1 - Math.exp(-dt * 5.0); // ~0.2 s to catch up: floaty but never lost
            x += (tx - x) * k;
            y += (ty - y) * k;
            z += (tz - z) * k;
        }

        // Color eases toward the mood (about half a second).
        rgb = Mood.blend(rgb, mood.rgb, 1 - (float) Math.exp(-dt * 4.0));

        // Bounce: little hops, squashing at the bottom like a slime landing.
        float speed = mood.speed * (activity == Activity.LISTENING ? 0.4f : 1f);
        hop += dt * 1.1f * speed;
        float phase = hop - (float) Math.floor(hop);
        float arc = (float) Math.sin(Math.PI * phase);   // 0 at landing, 1 at the top
        lift = 0.07f * mood.height * arc;
        float landing = (float) Math.pow(1 - arc, 6);    // only close to the landing
        squish = 0.16f * mood.height * landing;
        if (activity == Activity.LISTENING) squish -= 0.05f; // stretches up, all ears
        shiver = mood == Mood.SCARED ? (float) Math.sin(clock * 55) * 0.012f : 0f;

        // Mouth follows the voice; a soft smile otherwise.
        float targetMouth = activity == Activity.SPEAKING ? Math.min(1f, voiceLevel * 1.4f) : 0f;
        mouth += (targetMouth - mouth) * Math.min(1f, dt * 18f);

        // Blink every few seconds; sleepy keeps them half shut.
        long ms = (long) (clock * 1000);
        if (ms >= nextBlink) {
            blink = 1f;
            nextBlink = ms + 2500 + (long) (Math.random() * 3500);
        }
        blink = Math.max(mood == Mood.SLEEPY || mood == Mood.OFFLINE ? 0.55f : 0f, blink - dt * 8f);
    }
}
