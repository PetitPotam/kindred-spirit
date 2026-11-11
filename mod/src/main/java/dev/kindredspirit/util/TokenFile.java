package dev.kindredspirit.util;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.SecureRandom;
import java.util.HexFormat;

/**
 * The shared secret between the mod and the brain. Both read ~/.kindred-spirit/token; whichever
 * starts first creates it (readable only by you). Nothing to copy or paste.
 */
public final class TokenFile {
    private TokenFile() {}

    public static Path defaultPath() {
        return Path.of(System.getProperty("user.home"), ".kindred-spirit", "token");
    }

    public static String readOrCreate(Path path) throws IOException {
        if (Files.isRegularFile(path)) {
            String t = Files.readString(path, StandardCharsets.UTF_8).trim();
            if (!t.isEmpty()) return t;
        }
        Files.createDirectories(path.getParent());
        byte[] bytes = new byte[24];
        new SecureRandom().nextBytes(bytes);
        String token = HexFormat.of().formatHex(bytes);
        Path tmp = path.resolveSibling(path.getFileName() + ".tmp");
        Files.writeString(tmp, token + "\n", StandardCharsets.UTF_8);
        try {
            Files.setPosixFilePermissions(tmp, PosixFilePermissions.fromString("rw-------"));
        } catch (UnsupportedOperationException ignored) {
            // Windows: the file lives in the user's own profile folder.
        }
        try {
            Files.move(tmp, path); // fails if the brain created it a moment ago: then use theirs
        } catch (IOException raced) {
            Files.deleteIfExists(tmp);
            return Files.readString(path, StandardCharsets.UTF_8).trim();
        }
        return token;
    }
}
