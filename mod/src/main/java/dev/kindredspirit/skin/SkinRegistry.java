package dev.kindredspirit.skin;

import dev.kindredspirit.util.Mc;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.mojang.blaze3d.platform.NativeImage;
import dev.kindredspirit.KindredSpiritClient;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.texture.DynamicTexture;
import net.minecraft.resources.Identifier;
import net.minecraft.server.packs.resources.Resource;
import net.minecraft.server.packs.resources.ResourceManager;

import java.io.InputStream;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Stream;

/**
 * Finds every skin, from three places (later ones win when two share a name):
 * <ol>
 *   <li>built into the mod: {@code assets/kindredspirit/skins/*.json}</li>
 *   <li>resource packs: the same path inside any enabled pack</li>
 *   <li>your skins folder: {@code config/kindredspirit/skins/}. Drop a {@code name.png} there and
 *       it is a skin (texture wrapped on the ball); add {@code name.json} to choose shape and colors.</li>
 * </ol>
 * Reloaded with the game's resources (F3+T) or with {@code /kindred skins reload}.
 */
public final class SkinRegistry {
    public static final Identifier WHITE = rl("textures/companion/white.png");
    private final Map<String, Skin> skins = new TreeMap<>();
    private final Map<String, Identifier> textures = new TreeMap<>();
    private final List<Identifier> userTextures = new ArrayList<>();

    public static Path userDir() {
        return FabricLoader.getInstance().getConfigDir().resolve("kindredspirit").resolve("skins");
    }

    public synchronized List<String> ids() {
        return new ArrayList<>(skins.keySet());
    }

    public synchronized Skin get(String id) {
        Skin s = skins.get(id);
        return s != null ? s : skins.getOrDefault("slime", Skin.fallback());
    }

    public synchronized boolean has(String id) {
        return skins.containsKey(id);
    }

    /** The texture to draw the body with (white when the skin has none, so the tint shows). */
    public synchronized Identifier texture(Skin skin) {
        return textures.getOrDefault(skin.id(), WHITE);
    }

    /** Must run on the game thread (it uploads textures). */
    public synchronized void reload(ResourceManager rm) {
        skins.clear();
        textures.clear();
        Map<Identifier, Resource> found = rm.listResources("skins",
                loc -> loc.getNamespace().equals("kindredspirit") && loc.getPath().endsWith(".json"));
        for (Map.Entry<Identifier, Resource> e : found.entrySet()) {
            String id = baseName(e.getKey().getPath());
            try (Reader r = e.getValue().openAsReader()) {
                Skin skin = Skin.parse(id, JsonParser.parseReader(r).getAsJsonObject());
                skins.put(id, skin);
                if (!skin.texture().isEmpty()) textures.put(id, Identifier.parse(skin.texture()));
            } catch (Exception ex) {
                KindredSpiritClient.LOG.warn("Skin {} is not valid JSON: {}", e.getKey(), ex.toString());
            }
        }
        loadUserFolder();
        KindredSpiritClient.LOG.info("Skins: {}", skins.keySet());
    }

    private void loadUserFolder() {
        Minecraft mc = Minecraft.getInstance();
        for (Identifier old : userTextures) mc.getTextureManager().release(old);
        userTextures.clear();
        Path dir = userDir();
        try {
            Files.createDirectories(dir);
        } catch (Exception ignored) {
            return;
        }
        try (Stream<Path> files = Files.list(dir)) {
            for (Path p : files.sorted().toList()) {
                String file = p.getFileName().toString();
                String lower = file.toLowerCase(Locale.ROOT);
                String id = sanitize(baseName(file));
                if (lower.endsWith(".json")) {
                    JsonObject o = JsonParser.parseString(Files.readString(p, StandardCharsets.UTF_8)).getAsJsonObject();
                    Skin skin = Skin.parse(id, o);
                    skins.put(id, skin);
                    if (!skin.texture().isEmpty()) {
                        Path png = dir.resolve(skin.texture());
                        if (Files.isRegularFile(png)) textures.put(id, upload(id, png));
                        else if (skin.texture().contains(":")) textures.put(id, Identifier.parse(skin.texture()));
                    }
                } else if (lower.endsWith(".png") && !Files.exists(dir.resolve(baseName(file) + ".json"))
                        && !isReferenced(dir, file)) {
                    JsonObject o = new JsonObject(); // a PNG on its own: wrap it on a ball, no tint
                    o.addProperty("tint", "none");
                    o.addProperty("shell", false);
                    o.addProperty("texture", file);
                    skins.put(id, Skin.parse(id, o));
                    textures.put(id, upload(id, p));
                }
            }
        } catch (Exception e) {
            KindredSpiritClient.LOG.warn("Could not read your skins folder {}: {}", dir, e.toString());
        }
    }

    /** True if some JSON in the folder uses this PNG as its texture (then it is not a skin by itself). */
    private static boolean isReferenced(Path dir, String png) {
        try (Stream<Path> files = Files.list(dir)) {
            return files.filter(f -> f.toString().toLowerCase(Locale.ROOT).endsWith(".json")).anyMatch(f -> {
                try {
                    return Files.readString(f).contains("\"" + png + "\"");
                } catch (Exception e) {
                    return false;
                }
            });
        } catch (Exception e) {
            return false;
        }
    }

    private Identifier upload(String id, Path png) throws Exception {
        try (InputStream in = Files.newInputStream(png)) {
            NativeImage img = NativeImage.read(in);
            Identifier loc = rl("userskin/" + id);
            Minecraft.getInstance().getTextureManager().register(loc, Mc.texture("kindredspirit:userskin/" + id, img));
            userTextures.add(loc);
            return loc;
        }
    }

    private static String baseName(String path) {
        String f = path.substring(path.lastIndexOf('/') + 1);
        int dot = f.lastIndexOf('.');
        return dot > 0 ? f.substring(0, dot) : f;
    }

    static String sanitize(String s) {
        String out = s.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9_.-]", "_");
        return out.isEmpty() ? "skin" : out;
    }

    private static Identifier rl(String path) {
        return Identifier.fromNamespaceAndPath("kindredspirit", path);
    }
}
