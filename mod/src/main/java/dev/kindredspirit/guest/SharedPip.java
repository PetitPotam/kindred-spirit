package dev.kindredspirit.guest;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import dev.kindredspirit.Companion;
import dev.kindredspirit.life.Behavior;
import dev.kindredspirit.life.Emote;
import dev.kindredspirit.util.Mood;

import java.util.UUID;

/**
 * Light mode, on a friend's computer: the host's Pip, shown here as the host sees her. One Pip, the
 * host's AI and voice; this game only draws her. Her body moves here (beside whoever she follows,
 * smooth at any frame rate), and the rest comes from the host a few times a second: mood, what she's
 * doing, her words, her gestures, where she leads, when she leaves. Talking to her goes through chat
 * ("Pip, ..."), which the host's game passes to her brain.
 */
public final class SharedPip {
    private JsonObject state;
    private long lastAt;
    private int playedSeen = -1;

    public void receive(String json) {
        try {
            state = JsonParser.parseString(json).getAsJsonObject();
            lastAt = System.currentTimeMillis();
        } catch (RuntimeException e) {
            state = null;
        }
    }

    /** The host's Pip is here (a state came in the last 3 seconds). */
    public boolean active(long nowMs) {
        return state != null && nowMs - lastAt < 3000;
    }

    public void forget() {
        state = null;
        if (last != null) last.life.puppet = null;
        playedSeen = -1;
        GuestBridge.hidden = null;
    }

    public String name() {
        return state != null && state.has("name") ? state.get("name").getAsString() : "Pip";
    }

    public String skin() {
        return state != null && state.has("skin") ? state.get("skin").getAsString() : "";
    }

    /** Every tick: her mood, words, gestures and where she goes, from the host. */
    private Companion last;

    public void apply(Companion c, long nowMs) {
        if (state == null) return;
        last = c;
        Behavior life = c.life;
        double now = c.now();
        c.follow = uuid("follow");
        GuestBridge.hidden = uuid("standIn"); // (the Allay stand-in for friends without the mod: not drawn here)
        c.mood = Mood.parse(str("mood"), c.mood);
        try {
            c.activity = Behavior.Activity.valueOf(str("activity"));
        } catch (IllegalArgumentException e) {
            c.activity = Behavior.Activity.IDLE;
        }
        long left = state.has("subtitleLeft") ? state.get("subtitleLeft").getAsLong() : 0;
        if (left > 0) {
            c.subtitle = str("subtitle");
            c.subtitleUntil = nowMs + left;
        } else if (nowMs > c.subtitleUntil) {
            c.subtitle = "";
        }
        int played = state.has("played") ? state.get("played").getAsInt() : 0;
        if (playedSeen >= 0 && played != playedSeen) {
            Emote e = Emote.parse(str("emote"));
            if (e != null) life.play(e, now);
        }
        playedSeen = played;
        String mode = str("mode");
        switch (mode) { // (where she floats comes from the host; the mode is for her arrow, her trail, her fading)
            case "GUIDE" -> {
                double gx = num("gx"), gy = num("gy"), gz = num("gz");
                if (life.mode != Behavior.Mode.GUIDE) life.guide(gx, gy, gz, now);
                else life.retarget(gx, gy, gz);
            }
            case "HIDE" -> life.hide(2, now);
            default -> {
                if (life.mode == Behavior.Mode.GUIDE || life.mode == Behavior.Mode.HIDE) life.setMode(Behavior.Mode.FOLLOW, now);
            }
        }
        if (state.has("x")) { // she floats where she really is, smoothly (her springs fill the gaps between updates)
            double[] at = {num("x"), num("y"), num("z")};
            double dx = at[0] - life.x, dy = at[1] - life.y, dz = at[2] - life.z;
            if (life.puppet == null || dx * dx + dy * dy + dz * dz > 16 * 16) life.placeAt(at[0], at[1], at[2]);
            life.puppet = at;
        }
    }

    private String str(String k) {
        return state.has(k) && !state.get(k).isJsonNull() ? state.get(k).getAsString() : "";
    }

    private double num(String k) {
        return state.has(k) ? state.get(k).getAsDouble() : 0;
    }

    private UUID uuid(String k) {
        try {
            String s = str(k);
            return s.isEmpty() ? null : UUID.fromString(s);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }

    /** On the host: what friends with the mod need to show her as you see her. */
    public static JsonObject describe(Companion c, String name, UUID follow, UUID standIn, long nowMs) {
        Behavior life = c.life;
        JsonObject o = new JsonObject();
        o.addProperty("name", name);
        o.addProperty("skin", c.skin.id());
        o.addProperty("mood", c.mood.name());
        o.addProperty("activity", c.activity.name());
        if (follow != null) o.addProperty("follow", follow.toString());
        if (standIn != null) o.addProperty("standIn", standIn.toString());
        o.addProperty("x", life.x);
        o.addProperty("y", life.y);
        o.addProperty("z", life.z);
        o.addProperty("mode", life.mode.name());
        if (life.mode == Behavior.Mode.GUIDE) {
            double[] g = life.guideTarget();
            o.addProperty("gx", g[0]);
            o.addProperty("gy", g[1]);
            o.addProperty("gz", g[2]);
        }
        if (c.showSubtitle(nowMs)) {
            o.addProperty("subtitle", c.subtitle);
            o.addProperty("subtitleLeft", c.subtitleUntil - nowMs);
        }
        if (life.lastPlayed != null) o.addProperty("emote", life.lastPlayed.name());
        o.addProperty("played", life.played);
        return o;
    }
}
