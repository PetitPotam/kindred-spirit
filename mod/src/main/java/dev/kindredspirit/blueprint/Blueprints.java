package dev.kindredspirit.blueprint;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Map;

/**
 * Reading any blueprint file, whatever made it: the format is recognised from what's inside (the
 * extension is only a hint, since build sites rename files freely).
 *
 * <ul>
 *   <li>vanilla structure templates {@code .nbt} (structure blocks, {@code /place template}, villages,
 *       Create's schematics): {@link StructureFormat}</li>
 *   <li>Sponge {@code .schem} v1-v3 (WorldEdit, FAWE, most build sites): {@link SpongeFormat}</li>
 *   <li>Litematica {@code .litematic}: {@link LitematicFormat}</li>
 * </ul>
 *
 * Not read: MCEdit/Schematica {@code .schematic} from before 1.13 (numeric block ids that need the
 * game's whole id table of the time; WorldEdit on a 1.13+ game converts them to {@code .schem}), and
 * Building Gadgets' templates (their own compressed copy format, shared in game).
 */
public final class Blueprints {
    private Blueprints() {}

    /** Biggest file we open: a compressed schematic of a whole castle is a few MB. */
    public static final long MAX_FILE_BYTES = 16L * 1024 * 1024;

    public static Blueprint read(Path file) throws IOException {
        long size = Files.size(file);
        if (size > MAX_FILE_BYTES) throw new BlueprintException(file.getFileName() + " is too big (" + size / 1024 / 1024 + " MB)");
        return read(Files.readAllBytes(file), file.getFileName().toString());
    }

    /** @param fileName for the blueprint's name when the file has none, e.g. {@code cozy_cottage.schem} */
    public static Blueprint read(byte[] data, String fileName) throws IOException {
        Map<String, Object> root;
        try {
            root = Nbt.read(data);
        } catch (IOException e) {
            throw new BlueprintException(fileName + " isn't a schematic I can read (" + e.getMessage() + ")", e);
        }
        String name = baseName(fileName);
        if (LitematicFormat.looksLike(root)) return LitematicFormat.read(root, name);
        if (SpongeFormat.looksLike(root)) return SpongeFormat.read(root, name);
        if (StructureFormat.looksLike(root)) return StructureFormat.read(root, name);
        if (root.containsKey("Materials") && root.get("Blocks") instanceof byte[]) {
            throw new BlueprintException(fileName + " is an old MCEdit/Schematica schematic from before Minecraft 1.13; "
                    + "open it with WorldEdit in a newer game and save it as .schem");
        }
        throw new BlueprintException(fileName + " isn't a structure, Sponge or Litematica schematic");
    }

    /** Saves as a vanilla structure file (gzip NBT), the most widely readable kind. */
    public static void writeStructure(Blueprint bp, Path file, int dataVersion) throws IOException {
        Files.write(file, Nbt.writeCompressed(StructureFormat.write(bp, dataVersion)));
    }

    /** The game data version of Minecraft 1.21.1, what this mod writes. */
    public static final int DATA_VERSION_1_21_1 = 3955;

    static String baseName(String fileName) {
        String n = fileName == null ? "" : fileName;
        int slash = Math.max(n.lastIndexOf('/'), n.lastIndexOf('\\'));
        n = n.substring(slash + 1);
        String lower = n.toLowerCase(Locale.ROOT);
        for (String ext : new String[]{".litematic", ".schematic", ".schem", ".nbt"}) {
            if (lower.endsWith(ext)) return n.substring(0, n.length() - ext.length());
        }
        return n;
    }
}
