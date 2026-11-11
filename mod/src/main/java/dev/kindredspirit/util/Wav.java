package dev.kindredspirit.util;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/**
 * Tiny WAV helper: wrap 16-bit mono PCM into a WAV file, read one back, and measure how loud it is.
 * No Minecraft classes here, so it is covered by plain unit tests.
 */
public final class Wav {
    private Wav() {}

    /** Parsed WAV: where the 16-bit samples are and how fast they play. */
    public record Info(int sampleRate, int channels, int bitsPerSample, int dataOffset, int dataLength) {
        public double seconds() {
            int frame = channels * bitsPerSample / 8;
            return frame == 0 || sampleRate == 0 ? 0 : (double) dataLength / frame / sampleRate;
        }
    }

    public static byte[] encodePcm16Mono(byte[] pcm, int sampleRate) {
        ByteBuffer h = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN);
        h.put("RIFF".getBytes()).putInt(36 + pcm.length).put("WAVE".getBytes());
        h.put("fmt ".getBytes()).putInt(16).putShort((short) 1).putShort((short) 1)
                .putInt(sampleRate).putInt(sampleRate * 2).putShort((short) 2).putShort((short) 16);
        h.put("data".getBytes()).putInt(pcm.length);
        ByteArrayOutputStream out = new ByteArrayOutputStream(44 + pcm.length);
        out.writeBytes(h.array());
        out.writeBytes(pcm);
        return out.toByteArray();
    }

    /** Reads the "fmt " and "data" chunks; returns null if this is not a PCM WAV we understand. */
    public static Info parse(byte[] wav) {
        if (wav == null || wav.length < 12 || !tag(wav, 0, "RIFF") || !tag(wav, 8, "WAVE")) return null;
        ByteBuffer b = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN);
        int pos = 12, rate = 0, channels = 0, bits = 0;
        while (pos + 8 <= wav.length) {
            int size = b.getInt(pos + 4);
            if (size < 0) return null;
            if (tag(wav, pos, "fmt ") && pos + 24 <= wav.length) {
                channels = b.getShort(pos + 10);
                rate = b.getInt(pos + 12);
                bits = b.getShort(pos + 22);
            } else if (tag(wav, pos, "data")) {
                int len = Math.min(size, wav.length - pos - 8);
                return rate > 0 ? new Info(rate, channels, bits, pos + 8, len) : null;
            }
            pos += 8 + size + (size & 1);
        }
        return null;
    }

    /**
     * Loudness of each window (0..1, roughly), used to move the companion's mouth while it speaks.
     * Computed once per reply, off the render thread.
     */
    public static float[] envelope(byte[] wav, int windowMs) {
        Info info = parse(wav);
        if (info == null || info.bitsPerSample != 16 || info.channels < 1) return new float[0];
        int frameBytes = 2 * info.channels;
        int frames = info.dataLength / frameBytes;
        int perWindow = Math.max(1, info.sampleRate * windowMs / 1000);
        float[] env = new float[(frames + perWindow - 1) / perWindow];
        ByteBuffer b = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN);
        float max = 1e-6f;
        for (int w = 0; w < env.length; w++) {
            double sum = 0;
            int start = w * perWindow, end = Math.min(frames, start + perWindow);
            for (int f = start; f < end; f += 2) { // every other sample is plenty for a mouth
                short s = b.getShort(info.dataOffset + f * frameBytes);
                sum += (double) s * s;
            }
            int n = Math.max(1, (end - start + 1) / 2);
            env[w] = (float) Math.sqrt(sum / n);
            max = Math.max(max, env[w]);
        }
        for (int i = 0; i < env.length; i++) env[i] = Math.min(1f, env[i] / max);
        return env;
    }

    /** Peak absolute sample of 16-bit little-endian PCM, 0..32768. */
    public static int peak(byte[] pcm) {
        int peak = 0;
        for (int i = 0; i + 1 < pcm.length; i += 2) {
            int s = Math.abs((short) ((pcm[i] & 0xff) | (pcm[i + 1] << 8)));
            if (s > peak) peak = s;
        }
        return peak;
    }

    private static boolean tag(byte[] a, int at, String t) {
        if (at + 4 > a.length) return false;
        for (int i = 0; i < 4; i++) if (a[at + i] != t.charAt(i)) return false;
        return true;
    }
}
