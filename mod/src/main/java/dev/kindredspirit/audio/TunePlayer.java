package dev.kindredspirit.audio;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.core.Holder;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.sounds.SoundEvent;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;

import java.util.ArrayDeque;
import java.util.Deque;

/**
 * Her hums, played as music: the brain sends a little tune ("tune": notes in semitones and beats,
 * an instrument for her mood) and it's played with the game's note-block sounds where she floats,
 * a music note popping out of her for each one. Only on your screen.
 */
public final class TunePlayer {
    private record Note(Integer semi, int beats) {}

    private final Deque<Note> notes = new ArrayDeque<>();
    private Holder<SoundEvent> instrument = SoundEvents.NOTE_BLOCK_BELL;
    private long beatMs = 260, nextAt;

    public void start(JsonObject msg) {
        notes.clear();
        instrument = switch (msg.has("instrument") ? msg.get("instrument").getAsString() : "bell") {
            case "chime" -> SoundEvents.NOTE_BLOCK_CHIME;
            case "flute" -> SoundEvents.NOTE_BLOCK_FLUTE;
            case "harp" -> SoundEvents.NOTE_BLOCK_HARP;
            case "xylophone" -> SoundEvents.NOTE_BLOCK_XYLOPHONE;
            default -> SoundEvents.NOTE_BLOCK_BELL;
        };
        beatMs = msg.has("beat_ms") ? Math.max(120, Math.min(600, msg.get("beat_ms").getAsLong())) : 260;
        if (msg.has("notes")) {
            for (JsonElement e : msg.getAsJsonArray("notes")) {
                JsonObject n = e.getAsJsonObject();
                Integer semi = n.has("semi") && !n.get("semi").isJsonNull() ? n.get("semi").getAsInt() : null;
                notes.add(new Note(semi, n.has("beats") ? Math.max(1, n.get("beats").getAsInt()) : 1));
                if (notes.size() >= 48) break;
            }
        }
        nextAt = System.currentTimeMillis();
    }

    /** Every client tick: the next note when it's time, from where she floats. */
    public void tick(Minecraft mc, double x, double y, double z) {
        if (notes.isEmpty() || mc.level == null || System.currentTimeMillis() < nextAt) return;
        Note n = notes.poll();
        nextAt = System.currentTimeMillis() + n.beats() * beatMs;
        if (n.semi() == null) return; // a breath
        int semi = Math.max(-12, Math.min(12, n.semi()));
        float pitch = (float) Math.pow(2, semi / 12.0); // note blocks go from 0.5 to 2
        mc.level.playLocalSound(x, y, z, instrument.value(), SoundSource.NEUTRAL, 0.55f, pitch, false);
        // the note particle's colour comes from its x speed (0..1 across the two octaves)
        mc.level.addParticle(ParticleTypes.NOTE, x, y + 0.45, z, (semi + 12) / 24.0, 0, 0);
    }

    public boolean playing() {
        return !notes.isEmpty();
    }
}
