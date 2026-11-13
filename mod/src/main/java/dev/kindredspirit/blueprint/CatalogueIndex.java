package dev.kindredspirit.blueprint;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;

/**
 * The catalogue of a blueprints folder, kept next to the files: {@code catalogue.json} (an entry per
 * file from {@link Catalogue}, plus counts by category and the folder's SOURCES.txt) and a top and a front
 * picture per file in {@code .catalogue/}. Refreshing re-reads only new or changed files and forgets the
 * removed ones, so it's cheap to run at startup and whenever the folder changes (the dashboard adds and
 * removes files there; removed ones go to {@code .trash/}). The brain's find_blueprint and the dashboard
 * read it. Plain Java.
 */
public final class CatalogueIndex {
    private CatalogueIndex() {}

    public static final String INDEX = "catalogue.json", PICTURES = ".catalogue", TRASH = ".trash";
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create();

    static boolean blueprintFile(Path f) {
        String n = f.getFileName().toString().toLowerCase(Locale.ROOT);
        return !n.startsWith(".") && (n.endsWith(".nbt") || n.endsWith(".schem") || n.endsWith(".litematic")) && Files.isRegularFile(f);
    }

    static List<Path> files(Path dir) throws IOException {
        List<Path> out = new ArrayList<>();
        try (var s = Files.list(dir)) {
            for (Path f : (Iterable<Path>) s::iterator) if (blueprintFile(f)) out.add(f);
        }
        out.sort(null);
        return out;
    }

    /** Whether the folder changed since the index was written (a file added, removed or rewritten). */
    public static boolean stale(Path dir) {
        try {
            Path index = dir.resolve(INDEX);
            if (!Files.exists(index)) return !files(dir).isEmpty();
            long written = Files.getLastModifiedTime(index).toMillis();
            JsonObject idx = read(index);
            Map<String, JsonObject> known = new HashMap<>(entries(idx));
            if (idx.has("errors")) { // (an unreadable file is known too: not read again and again)
                for (JsonElement e : idx.getAsJsonArray("errors")) known.put(e.getAsJsonObject().get("file").getAsString(), e.getAsJsonObject());
            }
            List<Path> now = files(dir);
            if (now.size() != known.size()) return true;
            for (Path f : now) {
                if (!known.containsKey(f.getFileName().toString()) || Files.getLastModifiedTime(f).toMillis() > written) return true;
            }
            Path sources = dir.resolve("SOURCES.txt");
            return Files.exists(sources) && Files.getLastModifiedTime(sources).toMillis() > written;
        } catch (IOException | RuntimeException e) {
            return true;
        }
    }

    /** Brings the catalogue up to date; returns it. {@code color}: a block's colour for the pictures. */
    public static JsonObject refresh(Path dir, Function<BlockSpec, Integer> color) throws IOException {
        Path index = dir.resolve(INDEX), pics = dir.resolve(PICTURES);
        Map<String, JsonObject> old = Files.exists(index) ? entries(read(index)) : Map.of();
        Path sourcesFile = dir.resolve("SOURCES.txt");
        String sourcesText = Files.exists(sourcesFile) ? Files.readString(sourcesFile, StandardCharsets.UTF_8) : "";
        Catalogue.Sources sources = Catalogue.sources(sourcesText);
        boolean sourcesChanged = Files.exists(sourcesFile) && Files.exists(index)
                && Files.getLastModifiedTime(sourcesFile).compareTo(Files.getLastModifiedTime(index)) > 0;
        Files.createDirectories(pics);
        JsonArray entries = new JsonArray(), errors = new JsonArray();
        Map<String, Integer> categories = new TreeMap<>();
        List<String> keep = new ArrayList<>();
        for (Path f : files(dir)) {
            String name = f.getFileName().toString();
            long mtime = Files.getLastModifiedTime(f).toMillis(), bytes = Files.size(f);
            JsonObject e = old.get(name);
            boolean same = e != null && e.has("mtime") && e.get("mtime").getAsLong() == mtime && e.get("bytes").getAsLong() == bytes
                    && Files.exists(dir.resolve(e.get("top").getAsString()));
            if (!same) {
                try {
                    Blueprint bp = Blueprints.read(f);
                    e = Catalogue.describe(name, bp, sources);
                    String safe = Picture.safe(Blueprints.baseName(name));
                    Files.write(pics.resolve(safe + ".top.png"), Picture.top(bp, color));
                    Files.write(pics.resolve(safe + ".front.png"), Picture.front(bp, color));
                    e.addProperty("top", PICTURES + "/" + safe + ".top.png");
                    e.addProperty("front", PICTURES + "/" + safe + ".front.png");
                    e.addProperty("mtime", mtime);
                    e.addProperty("bytes", bytes);
                } catch (IOException | RuntimeException ex) {
                    JsonObject err = new JsonObject();
                    err.addProperty("file", name);
                    err.addProperty("error", String.valueOf(ex.getMessage()));
                    errors.add(err);
                    continue;
                }
            } else if (sourcesChanged) {
                String src = sources.of(name);
                if (src != null) e.addProperty("source", src);
                else e.remove("source");
            }
            entries.add(e);
            keep.add(e.get("top").getAsString());
            keep.add(e.get("front").getAsString());
            categories.merge(e.get("category").getAsString(), 1, Integer::sum);
        }
        // pictures of files that are gone
        try (var s = Files.list(pics)) {
            for (Path p : (Iterable<Path>) s::iterator) {
                if (!keep.contains(PICTURES + "/" + p.getFileName())) Files.deleteIfExists(p);
            }
        }
        JsonObject out = new JsonObject();
        out.addProperty("version", 1);
        out.addProperty("generated", System.currentTimeMillis());
        JsonObject cats = new JsonObject();
        categories.forEach(cats::addProperty);
        out.add("categories", cats);
        out.addProperty("sources", sourcesText);
        out.add("entries", entries);
        out.add("errors", errors);
        Path tmp = dir.resolve(INDEX + ".tmp");
        Files.writeString(tmp, GSON.toJson(out), StandardCharsets.UTF_8);
        Files.move(tmp, index, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        return out;
    }

    static JsonObject read(Path index) throws IOException {
        JsonElement e = JsonParser.parseString(Files.readString(index, StandardCharsets.UTF_8));
        return e.isJsonObject() ? e.getAsJsonObject() : new JsonObject();
    }

    static Map<String, JsonObject> entries(JsonObject index) {
        Map<String, JsonObject> m = new HashMap<>();
        if (index.has("entries")) {
            for (JsonElement e : index.getAsJsonArray("entries")) {
                if (e.isJsonObject() && e.getAsJsonObject().has("file")) m.put(e.getAsJsonObject().get("file").getAsString(), e.getAsJsonObject());
            }
        }
        return m;
    }
}
