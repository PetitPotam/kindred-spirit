package dev.kindredspirit;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import dev.kindredspirit.life.Behavior;
import net.fabricmc.loader.api.FabricLoader;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/** Settings in config/kindredspirit.json. Missing fields keep their defaults; the file is rewritten complete. */
public final class KindredConfig {
    /** What the companion is called (subtitles and chat). The brain has its own copy for the AI. */
    public String name = "Pip";
    /** Which skin it wears: /kindred skins lists them; add your own in config/kindredspirit/skins/. */
    public String skin = "slime";
    /** What it may do: advisor (talks, finds, guides), helper (also protects you, places torches), allpowerful (also time, weather). */
    public String power = "helper";
    /** grounded (uses only what really exists, like your torches) or magic (can make things appear). */
    public String style = "grounded";
    /** Let her play pranks (a sound behind you, borrowing a block you just placed). When she does is up to her (brain.toml [heart]). */
    public boolean allowPranks = true;
    /** Let her moods change the weather in singleplayer (rain when she cries). Up to her: brain.toml [heart]. */
    public boolean allowMoodWeather = true;
    /** Her glow lights the dark around her (singleplayer; an invisible light that moves with her, never left behind). */
    public boolean glow = true;
    /** While she leads the way: an arrow and the distance at the top of the screen. */
    public boolean guideArrow = true;
    /** While she leads the way: a faint trail of sparkles behind her. */
    public boolean guideTrail = true;
    /** Which chat messages go to her: auto (everything in singleplayer, "Pip, ..." on servers), all,
     *  name (only messages that start with her name) or command (only /kindred ...). */
    public String chatMode = "auto";
    /** Show the little heart meter when your bond with her changes. */
    public boolean showBond = true;
    /** With your world open to LAN, friends without the mod see her (as a stand-in) and can talk to her. */
    public boolean lanGuests = true;
    /** Friends on your LAN world may ask for her powers too (gifts, effects, finding, leading), within her
     *  power and style; off = they can only talk with her. */
    public boolean lanGuestPowers = true;
    /** Joining a friend's world where their Pip lives: "host" = you see and share their Pip (one Pip, their
     *  AI and voice; you talk to her in chat), "own" = your own Pip and brain, as at home. */
    public String sharedPip = "host";
    /** Whom she floats beside on a LAN world: "" = you, or a friend's name (/kindred follow, the dashboard). */
    public String follow = "";
    public String brainHost = "127.0.0.1";
    public int brainPort = 47811;
    /** Empty = ~/.kindred-spirit/token, shared with the brain. */
    public String tokenFile = "";
    /** auto, low, medium or high. auto follows your frame rate and graphics setting. */
    public String quality = "auto";
    public boolean worldSubtitles = true;
    public boolean hudCaptions = false;
    /** Keep the subtitles above it when the HUD is hidden (F1), e.g. for filming. */
    public boolean subtitlesWithHiddenHud = true;
    /** Also write what you said and what it answered in your chat (only on your screen). */
    public boolean chatLog = true;
    /** Multiplies the game's Voice/Speech volume slider. */
    public float voiceVolume = 1.0f;
    /** Where it floats, in blocks from your eyes. */
    public float offsetRight = 0.85f;
    public float offsetForward = 1.9f;
    public float offsetUp = -0.3f;
    public float size = 1.0f;
    /** Push-to-talk limit. The local Whisper is tuned for clips up to 15 s (that makes it ~2x faster). */
    public int maxRecordSeconds = 15;
    /** Its liveliness, one switch per behavior (see Behavior.Settings); also /kindred life. */
    public Behavior.Settings life = new Behavior.Settings();

    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

    public static Path path() {
        return FabricLoader.getInstance().getConfigDir().resolve("kindredspirit.json");
    }

    public static KindredConfig load() {
        Path p = path();
        KindredConfig cfg = null;
        try {
            if (Files.exists(p)) cfg = GSON.fromJson(Files.readString(p, StandardCharsets.UTF_8), KindredConfig.class);
        } catch (Exception e) {
            KindredSpiritClient.LOG.warn("Could not read {} ({}); using defaults", p, e.toString());
        }
        if (cfg == null) cfg = new KindredConfig();
        if (cfg.life == null) cfg.life = new Behavior.Settings();
        cfg.save();
        try { // the defaults, next to it: the dashboard's "reset to default" reads them
            Files.writeString(p.resolveSibling("kindredspirit.defaults.json"), GSON.toJson(new KindredConfig()),
                    StandardCharsets.UTF_8);
        } catch (IOException ignored) {
        }
        return cfg;
    }

    private long written = -1, seen = -1;

    /** Changed by someone else (the dashboard)? Then take the new values, in place. True if it did. */
    public boolean reloadIfChanged() {
        try {
            long m = Files.getLastModifiedTime(path()).toMillis();
            if (m == written || m == seen) return false;
            seen = m;
            KindredConfig other = GSON.fromJson(Files.readString(path(), StandardCharsets.UTF_8), KindredConfig.class);
            if (other == null) return false;
            copy(other, this, KindredConfig.class);
            if (other.life != null) copy(other.life, life, Behavior.Settings.class);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    private static <T> void copy(T from, T to, Class<T> type) throws IllegalAccessException {
        for (java.lang.reflect.Field f : type.getFields()) {
            int mod = f.getModifiers();
            if (java.lang.reflect.Modifier.isStatic(mod) || java.lang.reflect.Modifier.isFinal(mod)) continue;
            if (f.getType() == Behavior.Settings.class) continue; // (copied field by field: others hold it)
            f.set(to, f.get(from));
        }
    }

    public void save() {
        try {
            Files.createDirectories(path().getParent());
            Files.writeString(path(), GSON.toJson(this), StandardCharsets.UTF_8);
            written = Files.getLastModifiedTime(path()).toMillis();
        } catch (IOException e) {
            KindredSpiritClient.LOG.warn("Could not save {}: {}", path(), e.toString());
        }
    }
}
