package dev.kindredspirit.blueprint;

import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

/**
 * The game's binary NBT, read and written in plain Java so blueprints can be loaded and tested without
 * Minecraft running (and later read by tools outside the game). Every schematic format we read is NBT:
 * vanilla structure templates, Sponge {@code .schem}, Litematica {@code .litematic}, Create's schematics.
 *
 * <p>Tags become plain Java values: a compound is a {@code Map<String, Object>} (in file order), a list
 * a {@code List<Object>}, byte/int/long arrays are {@code byte[]}/{@code int[]}/{@code long[]}, numbers
 * their boxed types, strings {@code String}. Files are gzip-compressed (all of these formats are);
 * uncompressed NBT is read too.
 *
 * <p>Untrusted files are bounded: at most {@link #MAX_BYTES} of uncompressed data, nesting at most
 * {@link #MAX_DEPTH} deep, and no array or list longer than the bytes left, so a hostile or broken
 * file fails with an error instead of exhausting memory.
 */
public final class Nbt {
    private Nbt() {}

    /** Larger than any sensible blueprint (a 256x256x256 Sponge file of varints is ~17 MB). */
    public static final long MAX_BYTES = 64L * 1024 * 1024;
    public static final int MAX_DEPTH = 512;

    static final byte END = 0, BYTE = 1, SHORT = 2, INT = 3, LONG = 4, FLOAT = 5, DOUBLE = 6,
            BYTE_ARRAY = 7, STRING = 8, LIST = 9, COMPOUND = 10, INT_ARRAY = 11, LONG_ARRAY = 12;

    /** Reads a whole file: gzip or not, the root compound's contents (its name is dropped). */
    public static Map<String, Object> read(byte[] data) throws IOException {
        InputStream in = new ByteArrayInputStream(data);
        if (data.length >= 2 && (data[0] & 0xFF) == 0x1F && (data[1] & 0xFF) == 0x8B) {
            in = new GZIPInputStream(in);
        }
        return read(in);
    }

    public static Map<String, Object> read(InputStream raw) throws IOException {
        Reader r = new Reader(new DataInputStream(new BufferedInputStream(new Limited(raw, MAX_BYTES))));
        byte type = r.in.readByte();
        if (type != COMPOUND) throw new IOException("not NBT: the root is not a compound (tag " + type + ")");
        r.in.readUTF(); // root name, usually ""
        @SuppressWarnings("unchecked")
        Map<String, Object> root = (Map<String, Object>) r.payload(COMPOUND, 0);
        return root;
    }

    /** Writes a root compound (named ""), gzip-compressed like the game's own files. */
    public static byte[] writeCompressed(Map<String, Object> root) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (GZIPOutputStream gz = new GZIPOutputStream(bytes)) {
            write(root, gz);
        }
        return bytes.toByteArray();
    }

    public static void write(Map<String, Object> root, OutputStream raw) throws IOException {
        DataOutputStream out = new DataOutputStream(raw);
        out.writeByte(COMPOUND);
        out.writeUTF("");
        payload(out, root);
        out.flush();
    }

    // --- reading -------------------------------------------------------------------------------

    private static final class Reader {
        final DataInputStream in;

        Reader(DataInputStream in) {
            this.in = in;
        }

        Object payload(byte type, int depth) throws IOException {
            if (depth > MAX_DEPTH) throw new IOException("NBT nested too deeply");
            return switch (type) {
                case BYTE -> in.readByte();
                case SHORT -> in.readShort();
                case INT -> in.readInt();
                case LONG -> in.readLong();
                case FLOAT -> in.readFloat();
                case DOUBLE -> in.readDouble();
                case BYTE_ARRAY -> {
                    byte[] a = new byte[length(1)];
                    in.readFully(a);
                    yield a;
                }
                case STRING -> string();
                case LIST -> {
                    byte et = in.readByte();
                    int n = in.readInt();
                    if (n <= 0) yield new ArrayList<>();
                    if (et == END) throw new IOException("NBT list of end tags with a length");
                    check(n, 1);
                    List<Object> list = new ArrayList<>(Math.min(n, 4096));
                    for (int i = 0; i < n; i++) list.add(payload(et, depth + 1));
                    yield list;
                }
                case COMPOUND -> {
                    Map<String, Object> map = new LinkedHashMap<>();
                    while (true) {
                        byte t = in.readByte();
                        if (t == END) break;
                        String name = string();
                        map.put(name, payload(t, depth + 1));
                    }
                    yield map;
                }
                case INT_ARRAY -> {
                    int[] a = new int[length(4)];
                    for (int i = 0; i < a.length; i++) a[i] = in.readInt();
                    yield a;
                }
                case LONG_ARRAY -> {
                    long[] a = new long[length(8)];
                    for (int i = 0; i < a.length; i++) a[i] = in.readLong();
                    yield a;
                }
                default -> throw new IOException("unknown NBT tag type " + type);
            };
        }

        String string() throws IOException {
            return in.readUTF(); // NBT strings are Java's modified UTF-8 with a 2-byte length, as readUTF expects
        }

        int length(int elementBytes) throws IOException {
            int n = in.readInt();
            if (n < 0) throw new IOException("negative NBT array length");
            check(n, elementBytes);
            return n;
        }

        static void check(long n, int elementBytes) throws IOException {
            if (n * elementBytes > MAX_BYTES) throw new IOException("NBT array too large: " + n);
        }
    }

    /** Stops reading past a limit (a zip bomb, or a file claiming gigabytes). */
    private static final class Limited extends InputStream {
        private final InputStream in;
        private long left;

        Limited(InputStream in, long limit) {
            this.in = in;
            this.left = limit;
        }

        @Override
        public int read() throws IOException {
            if (left <= 0) throw new IOException("NBT data larger than " + MAX_BYTES + " bytes");
            int b = in.read();
            if (b >= 0) left--;
            return b;
        }

        @Override
        public int read(byte[] b, int off, int len) throws IOException {
            if (left <= 0) throw new IOException("NBT data larger than " + MAX_BYTES + " bytes");
            int n = in.read(b, off, (int) Math.min(len, left));
            if (n > 0) left -= n;
            return n;
        }
    }

    // --- writing -------------------------------------------------------------------------------

    static byte typeOf(Object v) throws IOException {
        if (v instanceof Byte || v instanceof Boolean) return BYTE;
        if (v instanceof Short) return SHORT;
        if (v instanceof Integer) return INT;
        if (v instanceof Long) return LONG;
        if (v instanceof Float) return FLOAT;
        if (v instanceof Double) return DOUBLE;
        if (v instanceof byte[]) return BYTE_ARRAY;
        if (v instanceof String) return STRING;
        if (v instanceof List<?>) return LIST;
        if (v instanceof Map<?, ?>) return COMPOUND;
        if (v instanceof int[]) return INT_ARRAY;
        if (v instanceof long[]) return LONG_ARRAY;
        throw new IOException("can't write " + (v == null ? "null" : v.getClass().getSimpleName()) + " as NBT");
    }

    private static void payload(DataOutputStream out, Object v) throws IOException {
        switch (typeOf(v)) {
            case BYTE -> out.writeByte(v instanceof Boolean b ? (b ? 1 : 0) : (Byte) v);
            case SHORT -> out.writeShort((Short) v);
            case INT -> out.writeInt((Integer) v);
            case LONG -> out.writeLong((Long) v);
            case FLOAT -> out.writeFloat((Float) v);
            case DOUBLE -> out.writeDouble((Double) v);
            case BYTE_ARRAY -> {
                byte[] a = (byte[]) v;
                out.writeInt(a.length);
                out.write(a);
            }
            case STRING -> out.writeUTF((String) v);
            case LIST -> {
                List<?> list = (List<?>) v;
                byte et = list.isEmpty() ? END : typeOf(list.get(0));
                out.writeByte(et);
                out.writeInt(list.size());
                for (Object e : list) {
                    if (typeOf(e) != et) throw new IOException("NBT list with mixed types");
                    payload(out, e);
                }
            }
            case COMPOUND -> {
                for (Map.Entry<?, ?> e : ((Map<?, ?>) v).entrySet()) {
                    if (e.getValue() == null) continue;
                    out.writeByte(typeOf(e.getValue()));
                    out.writeUTF(String.valueOf(e.getKey()));
                    payload(out, e.getValue());
                }
                out.writeByte(END);
            }
            case INT_ARRAY -> {
                int[] a = (int[]) v;
                out.writeInt(a.length);
                for (int x : a) out.writeInt(x);
            }
            case LONG_ARRAY -> {
                long[] a = (long[]) v;
                out.writeInt(a.length);
                for (long x : a) out.writeLong(x);
            }
            default -> throw new IOException("unreachable");
        }
    }

    // --- small helpers for the format readers ---------------------------------------------------

    @SuppressWarnings("unchecked")
    static Map<String, Object> compound(Map<String, Object> m, String key) {
        return m.get(key) instanceof Map<?, ?> c ? (Map<String, Object>) c : null;
    }

    static List<Object> list(Map<String, Object> m, String key) {
        return m.get(key) instanceof List<?> l ? new ArrayList<>(l) : List.of();
    }

    static int integer(Map<String, Object> m, String key, int fallback) {
        return m.get(key) instanceof Number n ? n.intValue() : fallback;
    }

    static String string(Map<String, Object> m, String key, String fallback) {
        return m.get(key) instanceof String s ? s : fallback;
    }

    /** An x, y, z triple stored as a list of numbers, an int array, or a compound {x, y, z}. */
    static int[] triple(Object v) {
        if (v instanceof int[] a && a.length == 3) return a.clone();
        if (v instanceof List<?> l && l.size() == 3 && l.get(0) instanceof Number) {
            return new int[]{((Number) l.get(0)).intValue(), ((Number) l.get(1)).intValue(), ((Number) l.get(2)).intValue()};
        }
        if (v instanceof Map<?, ?> c && c.get("x") instanceof Number x && c.get("y") instanceof Number y
                && c.get("z") instanceof Number z) {
            return new int[]{x.intValue(), y.intValue(), z.intValue()};
        }
        return null;
    }
}
