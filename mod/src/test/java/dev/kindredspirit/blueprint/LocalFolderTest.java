package dev.kindredspirit.blueprint;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Every blueprint in a real folder reads (run with KINDRED_BLUEPRINT_DIR set, e.g. her blueprints folder
 * filled with Minecraft's own village houses, portals and ships); skipped otherwise.
 */
class LocalFolderTest {
    @Test
    @EnabledIfEnvironmentVariable(named = "KINDRED_BLUEPRINT_DIR", matches = ".+")
    void everyBlueprintInTheFolderReads() throws Exception {
        Path dir = Path.of(System.getenv("KINDRED_BLUEPRINT_DIR"));
        List<String> bad = new ArrayList<>();
        int n = 0;
        try (var files = Files.list(dir)) {
            for (Path f : (Iterable<Path>) files::iterator) {
                String name = f.getFileName().toString();
                if (!name.matches(".*\\.(nbt|schem|litematic)$")) continue;
                n++;
                try {
                    Blueprint bp = Blueprints.read(f);
                    if (bp == null) bad.add(name + ": null");
                } catch (Exception e) {
                    bad.add(name + ": " + e);
                }
            }
        }
        System.out.println("read " + n + " blueprints, " + bad.size() + " failed: " + bad);
        assertTrue(bad.isEmpty(), bad.toString());
    }
}
