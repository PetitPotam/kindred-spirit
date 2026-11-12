package dev.kindredspirit.senses;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import dev.kindredspirit.util.Direction8;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.client.resources.sounds.SoundInstance;
import net.minecraft.client.sounds.SoundEventListener;
import net.minecraft.client.sounds.WeighedSoundEvents;
import net.minecraft.network.chat.Component;
import net.minecraft.sounds.SoundSource;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * What she hears: the sounds the game plays around you, by the names it already gives them for
 * subtitles ("Zombie groans", "Lava pops", "Door creaks"). So she can hear a zombie behind a wall
 * or water somewhere below, without seeing it. Your own footsteps and blocks you place or break
 * right next to you are left out (that's you, not news).
 */
public final class Hearing implements SoundEventListener {
    private record Heard(long at, String what, double x, double y, double z, SoundSource source, float range) {}

    private final Deque<Heard> heard = new ArrayDeque<>();

    @Override
    public void onPlaySound(SoundInstance sound, WeighedSoundEvents events, float range) {
        Component subtitle = events.getSubtitle();
        if (subtitle == null || sound.isRelative()) return; // music and interface sounds have none / are "in your head"
        String what = subtitle.getString();
        if (what.isEmpty()) return;
        LocalPlayer p = Minecraft.getInstance().player;
        if (p != null && (sound.getSource() == SoundSource.PLAYERS || sound.getSource() == SoundSource.BLOCKS)
                && p.distanceToSqr(sound.getX(), sound.getY(), sound.getZ()) < 36) return; // you, at work right here
        synchronized (heard) {
            heard.addLast(new Heard(System.currentTimeMillis(), what, sound.getX(), sound.getY(), sound.getZ(),
                    sound.getSource(), range));
            while (heard.size() > 64) heard.removeFirst();
        }
    }

    /** Sounds of the last few seconds, one per kind (the nearest), with where they came from. */
    public JsonArray recent(LocalPlayer p, long windowMs) {
        long now = System.currentTimeMillis();
        Map<String, Heard> nearest = new LinkedHashMap<>();
        synchronized (heard) {
            heard.removeIf(h -> now - h.at() > 30000);
            for (Heard h : heard) {
                if (now - h.at() > windowMs) continue;
                double d2 = p.distanceToSqr(h.x(), h.y(), h.z());
                if (d2 > (double) h.range() * h.range()) continue; // the game plays it, but too far to really hear
                Heard old = nearest.get(h.what());
                if (old == null || p.distanceToSqr(h.x(), h.y(), h.z()) < p.distanceToSqr(old.x(), old.y(), old.z())) {
                    nearest.put(h.what(), h);
                }
            }
        }
        JsonArray out = new JsonArray();
        for (Heard h : nearest.values()) {
            JsonObject o = new JsonObject();
            o.addProperty("what", h.what());
            o.addProperty("distance", Math.round(Math.sqrt(p.distanceToSqr(h.x(), h.y(), h.z()))));
            o.addProperty("direction", Direction8.relative(p.getYRot(), h.x() - p.getX(), h.z() - p.getZ()));
            o.addProperty("above", Math.round(h.y() - p.getY()));
            o.addProperty("ago", (now - h.at()) / 1000);
            out.add(o);
            if (out.size() >= 10) break;
        }
        return out;
    }
}
