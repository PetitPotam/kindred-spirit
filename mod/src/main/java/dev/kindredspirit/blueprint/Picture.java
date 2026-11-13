package dev.kindredspirit.blueprint;

import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.function.Function;
import java.util.zip.CRC32;
import java.util.zip.Deflater;

/**
 * Little pictures of a blueprint for the dashboard: seen from above (the highest block of each column,
 * lighter the higher it is) and from the front (the +z side, the nearest block of each spot, darker the
 * deeper it is). Each block is a few pixels of one colour: in the game, Minecraft's own map colours; here, a
 * guess by name. Written as PNG with the JDK's deflate, no image library (none is safe to load inside the
 * game on every system). Plain Java.
 */
public final class Picture {
    private Picture() {}

    /** Transparent: nothing to draw. */
    public static final int NONE = -1;

    public static byte[] top(Blueprint bp, Function<BlockSpec, Integer> color) throws IOException {
        int s = scale(Math.max(bp.width(), bp.length()));
        int w = bp.width(), l = bp.length();
        int[] px = new int[w * l], height = new int[w * l], base = new int[w * l];
        for (int z = 0; z < l; z++) {
            for (int x = 0; x < w; x++) {
                int c = NONE, hy = -1;
                for (int y = bp.height() - 1; y >= 0 && c == NONE; y--) {
                    BlockSpec b = bp.at(x, y, z);
                    if (b == null || b.isAir()) continue;
                    int col = color.apply(b);
                    if (col != NONE) {
                        c = col;
                        hy = y;
                    }
                }
                base[x + z * w] = c;
                height[x + z * w] = hy;
            }
        }
        // shaded like a Minecraft map: lighter where higher than the block to the north, darker where lower
        for (int z = 0; z < l; z++) {
            for (int x = 0; x < w; x++) {
                int i = x + z * w, c = base[i];
                if (c == NONE) {
                    px[i] = NONE;
                    continue;
                }
                int north = z > 0 && base[i - w] != NONE ? height[i - w] : height[i];
                double f = 0.8 + 0.25 * (height[i] + 1) / bp.height();
                if (height[i] > north) f *= 1.15;
                else if (height[i] < north) f *= 0.78;
                px[i] = shade(c, f);
            }
        }
        return png(px, w, l, s);
    }

    public static byte[] front(Blueprint bp, Function<BlockSpec, Integer> color) throws IOException {
        int s = scale(Math.max(bp.width(), bp.height()));
        int w = bp.width(), h = bp.height();
        int[] px = new int[w * h];
        for (int y = 0; y < h; y++) {
            for (int x = 0; x < w; x++) {
                int c = NONE;
                for (int z = bp.length() - 1; z >= 0 && c == NONE; z--) {
                    BlockSpec b = bp.at(x, y, z);
                    if (b == null || b.isAir()) continue;
                    int col = color.apply(b);
                    if (col != NONE) c = shade(col, 1.0 - 0.5 * (bp.length() - 1 - z) / Math.max(1, bp.length()));
                }
                px[x + (h - 1 - y) * w] = c; // (top of the picture is the top of the build)
            }
        }
        return png(px, w, h, s);
    }

    static int scale(int side) {
        return Math.max(2, Math.min(16, 256 / Math.max(1, side)));
    }

    static int shade(int rgb, double f) {
        int r = (int) Math.min(255, ((rgb >> 16) & 255) * f), g = (int) Math.min(255, ((rgb >> 8) & 255) * f),
                b = (int) Math.min(255, (rgb & 255) * f);
        return (r << 16) | (g << 8) | b;
    }

    /** A colour by name when the game's isn't at hand (tests, tools outside the game). */
    public static int guessColor(BlockSpec b) {
        String p = b.path();
        if (p.contains("glass")) return 0xC8E6F0;
        if (p.contains("torch") || p.contains("lantern")) return 0xF0C040;
        if (p.contains("water")) return 0x3F76E4;
        if (p.contains("lava")) return 0xE06010;
        if (p.contains("leaves")) return 0x3E7B2C;
        if (p.contains("grass") || p.contains("moss")) return 0x6EA046;
        if (p.contains("dirt") || p.contains("farmland") || p.contains("path")) return 0x86603F;
        if (p.contains("sandstone")) return 0xD8CB9B;
        if (p.contains("sand")) return 0xDBD3A0;
        if (p.contains("snow")) return 0xF2F8F8;
        if (p.contains("ice")) return 0x92B5FC;
        if (p.contains("terracotta")) return 0xA1563A;
        if (p.contains("brick")) return 0x96513F;
        if (p.contains("deepslate") || p.contains("blackstone")) return 0x505058;
        if (p.contains("obsidian")) return 0x1C1828;
        if (p.contains("netherrack")) return 0x6E3434;
        if (p.contains("hay")) return 0xC9A824;
        if (p.contains("wool") || p.contains("carpet") || p.contains("bed")) return 0xE6E6E6;
        for (String[] w : new String[][]{{"dark_oak", "4A3220"}, {"spruce", "6E5232"}, {"birch", "D7C98A"}, {"jungle", "A4724D"},
                {"acacia", "A85A32"}, {"cherry", "E3B3AE"}, {"mangrove", "7A3631"}, {"crimson", "6A344B"}, {"warped", "2B6963"},
                {"bamboo", "D4C26A"}, {"oak", "A0824F"}}) {
            if (p.startsWith(w[0] + "_") || p.contains("_" + w[0] + "_")) return Integer.parseInt(w[1], 16);
        }
        if (p.contains("stone") || p.contains("cobble") || p.contains("andesite") || p.contains("smooth")) return 0x808080;
        if (p.contains("iron")) return 0xD8D8D8;
        if (p.contains("gold")) return 0xF0D040;
        if (p.contains("wheat") || p.contains("carrot") || p.contains("potato") || p.contains("beetroot")) return 0x8CB040;
        return 0x9A9A9A;
    }

    // --- PNG ------------------------------------------------------------------------------------------

    /** RGBA PNG of w x h cells, each s x s pixels; NONE cells are transparent. */
    static byte[] png(int[] cells, int w, int h, int s) throws IOException {
        int W = w * s, H = h * s;
        byte[] raw = new byte[H * (1 + W * 4)];
        int i = 0;
        for (int y = 0; y < H; y++) {
            raw[i++] = 0; // no filter
            for (int x = 0; x < W; x++) {
                int c = cells[(x / s) + (y / s) * w];
                if (c == NONE) {
                    i += 4;
                    continue;
                }
                raw[i++] = (byte) (c >> 16);
                raw[i++] = (byte) (c >> 8);
                raw[i++] = (byte) c;
                raw[i++] = (byte) 255;
            }
        }
        Deflater d = new Deflater(Deflater.BEST_COMPRESSION);
        d.setInput(raw);
        d.finish();
        ByteArrayOutputStream z = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        while (!d.finished()) z.write(buf, 0, d.deflate(buf));
        d.end();
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        DataOutputStream o = new DataOutputStream(out);
        o.write(new byte[]{(byte) 0x89, 'P', 'N', 'G', '\r', '\n', 0x1A, '\n'});
        ByteArrayOutputStream ihdr = new ByteArrayOutputStream();
        DataOutputStream ih = new DataOutputStream(ihdr);
        ih.writeInt(W);
        ih.writeInt(H);
        ih.write(new byte[]{8, 6, 0, 0, 0}); // 8 bits, RGBA, deflate, no filter method, no interlace
        chunk(o, "IHDR", ihdr.toByteArray());
        chunk(o, "IDAT", z.toByteArray());
        chunk(o, "IEND", new byte[0]);
        return out.toByteArray();
    }

    private static void chunk(DataOutputStream o, String type, byte[] data) throws IOException {
        byte[] t = type.getBytes(StandardCharsets.US_ASCII);
        o.writeInt(data.length);
        o.write(t);
        o.write(data);
        CRC32 crc = new CRC32();
        crc.update(t);
        crc.update(data);
        o.writeInt((int) crc.getValue());
    }

    static String safe(String base) {
        return base.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9._-]", "_");
    }
}
