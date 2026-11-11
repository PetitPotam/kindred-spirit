package dev.kindredspirit;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import net.fabricmc.loader.api.FabricLoader;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/** Settings in config/kindredspirit.json. Missing fields keep their defaults; the file is rewritten complete. */
public final class KindredConfig {
    /** What the companion is called (subtitles and chat). The brain has its own copy for the AI. */
    public String name = "Pip";
    public String brainHost = "127.0.0.1";
    public int brainPort = 47811;
    /** Empty = ~/.kindred-spirit/token, shared with the brain. */
    public String tokenFile = "";
    /** auto, low, medium or high. auto follows your frame rate and graphics setting. */
    public String quality = "auto";
    public boolean worldSubtitles = true;
    public boolean hudCaptions = false;
    /** Also write what you said and what it answered in your chat (only on your screen). */
    public boolean chatLog = true;
    /** Multiplies the game's Voice/Speech volume slider. */
    public float voiceVolume = 1.0f;
    /** Where it floats, in blocks from your eyes. */
    public float offsetRight = 0.85f;
    public float offsetForward = 1.9f;
    public float offsetUp = -0.3f;
    public float size = 1.0f;
    public int maxRecordSeconds = 30;

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
        cfg.save();
        return cfg;
    }

    public void save() {
        try {
            Files.createDirectories(path().getParent());
            Files.writeString(path(), GSON.toJson(this), StandardCharsets.UTF_8);
        } catch (IOException e) {
            KindredSpiritClient.LOG.warn("Could not save {}: {}", path(), e.toString());
        }
    }
}
