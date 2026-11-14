package dev.kindredspirit.settings;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import dev.kindredspirit.KindredConfig;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;

/**
 * Where the settings screen reads and saves (#5). With her brain on this computer: her dashboard, so the screen and
 * the dashboard's Settings page are the same settings, profiles included. Otherwise: the mod's own settings file.
 * Every call is off the game thread (the screen gets the answer on its next frame).
 */
public interface SettingsStore {
    CompletableFuture<List<SettingsModel.Entry>> load();

    /** Saves one value (null: back to the default); the answer is an error to show, or "" when it's saved. */
    CompletableFuture<String> set(SettingsModel.Entry e, JsonElement value);

    /** The saved profiles (empty without the dashboard); "*" in front marks the one in use. */
    CompletableFuture<List<String>> profiles();

    CompletableFuture<String> profile(String action, String name);

    String where();

    final class Dashboard implements SettingsStore {
        private static final HttpClient HTTP = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
        private final String base;

        public Dashboard(String base) {
            this.base = base;
        }

        @Override
        public String where() {
            return "Saved on her dashboard: the same settings as its Settings page";
        }

        private CompletableFuture<JsonElement> call(String path, JsonObject body) {
            HttpRequest.Builder b = HttpRequest.newBuilder(URI.create(base + path)).timeout(Duration.ofSeconds(15));
            if (body != null) b.header("Content-Type", "application/json").POST(HttpRequest.BodyPublishers.ofString(body.toString()));
            return HTTP.sendAsync(b.build(), HttpResponse.BodyHandlers.ofString()).thenApply(r -> {
                JsonElement j = JsonParser.parseString(r.body().isEmpty() ? "{}" : r.body());
                if (r.statusCode() != 200) {
                    String err = j.isJsonObject() && j.getAsJsonObject().has("error")
                            ? j.getAsJsonObject().get("error").getAsString() : "the dashboard said " + r.statusCode();
                    throw new IllegalStateException(err);
                }
                return j;
            });
        }

        @Override
        public CompletableFuture<List<SettingsModel.Entry>> load() {
            return call("api/settings/editable", null).thenApply(j -> SettingsModel.fromDashboard(j.getAsJsonObject()));
        }

        @Override
        public CompletableFuture<String> set(SettingsModel.Entry e, JsonElement value) {
            return call("api/settings", SettingsModel.change(e, value)).handle((j, err) -> err == null ? "" : message(err));
        }

        @Override
        public CompletableFuture<List<String>> profiles() {
            return call("api/profiles", null).thenApply(j -> {
                List<String> out = new ArrayList<>();
                JsonArray list = j.getAsJsonObject().getAsJsonArray("profiles");
                if (list != null) for (JsonElement p : list) {
                    JsonObject o = p.getAsJsonObject();
                    out.add((o.has("active") && o.get("active").getAsBoolean() ? "*" : "") + o.get("name").getAsString());
                }
                return out;
            });
        }

        @Override
        public CompletableFuture<String> profile(String action, String name) {
            JsonObject body = new JsonObject();
            body.addProperty("action", action);
            body.addProperty("name", name);
            return call("api/profiles", body).handle((j, err) -> err == null ? "" : message(err));
        }
    }

    /** A friend's game: the mod's own settings (kindredspirit.json), at once. */
    final class Local implements SettingsStore {
        private final KindredConfig cfg;

        public Local(KindredConfig cfg) {
            this.cfg = cfg;
        }

        @Override
        public String where() {
            return "Her brain is on another computer: only this game's own settings here";
        }

        @Override
        public CompletableFuture<List<SettingsModel.Entry>> load() {
            return CompletableFuture.completedFuture(SettingsModel.fromFields(cfg, new KindredConfig()));
        }

        @Override
        public CompletableFuture<String> set(SettingsModel.Entry e, JsonElement value) {
            try {
                var f = KindredConfig.class.getField(e.path);
                JsonElement v = value != null ? value : e.fallback;
                if (v == null) return CompletableFuture.completedFuture("no default to go back to");
                Class<?> t = f.getType();
                f.set(cfg, t == boolean.class ? v.getAsBoolean() : t == int.class ? v.getAsInt() : t == float.class
                        ? v.getAsFloat() : t == double.class ? v.getAsDouble() : v.getAsString());
                cfg.save();
                return CompletableFuture.completedFuture("");
            } catch (ReflectiveOperationException | RuntimeException x) {
                return CompletableFuture.completedFuture("couldn't save: " + x.getMessage());
            }
        }

        @Override
        public CompletableFuture<List<String>> profiles() {
            return CompletableFuture.completedFuture(List.of());
        }

        @Override
        public CompletableFuture<String> profile(String action, String name) {
            return CompletableFuture.completedFuture("profiles live on her dashboard");
        }
    }

    static String message(Throwable err) {
        Throwable t = err instanceof java.util.concurrent.CompletionException && err.getCause() != null ? err.getCause() : err;
        return t instanceof java.net.ConnectException || t instanceof java.net.http.HttpTimeoutException
                ? "her dashboard isn't answering (is she awake?)" : String.valueOf(t.getMessage());
    }
}
