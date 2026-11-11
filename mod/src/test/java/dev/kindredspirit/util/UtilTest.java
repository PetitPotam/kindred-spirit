package dev.kindredspirit.util;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

/** Logic that runs without Minecraft: ./gradlew test (a few seconds, no game needed). */
class UtilTest {
    @Test
    void wavRoundTrip() {
        byte[] pcm = new byte[16000 * 2]; // one second of 16 kHz mono
        for (int i = 0; i < 16000; i++) {
            short s = (short) (Math.sin(i / 10.0) * 12000);
            pcm[2 * i] = (byte) s;
            pcm[2 * i + 1] = (byte) (s >> 8);
        }
        byte[] wav = Wav.encodePcm16Mono(pcm, 16000);
        Wav.Info info = Wav.parse(wav);
        assertNotNull(info);
        assertEquals(16000, info.sampleRate());
        assertEquals(1, info.channels());
        assertEquals(16, info.bitsPerSample());
        assertEquals(1.0, info.seconds(), 1e-6);
        assertTrue(Wav.peak(pcm) > 11000 && Wav.peak(pcm) <= 12000);
    }

    @Test
    void envelopeFollowsLoudness() {
        byte[] pcm = new byte[16000 * 2];
        for (int i = 8000; i < 16000; i++) { // silent first half, loud second half
            short s = (short) ((i % 2 == 0) ? 10000 : -10000);
            pcm[2 * i] = (byte) s;
            pcm[2 * i + 1] = (byte) (s >> 8);
        }
        float[] env = Wav.envelope(Wav.encodePcm16Mono(pcm, 16000), 100);
        assertEquals(10, env.length);
        assertEquals(0f, env[0], 0.01f);
        assertEquals(1f, env[9], 0.01f);
    }

    @Test
    void badWavIsRejected() {
        assertNull(Wav.parse(new byte[]{1, 2, 3}));
        assertNull(Wav.parse(null));
        assertEquals(0, Wav.envelope(new byte[10], 40).length);
    }

    @Test
    void directionsMatchMinecraftYaw() {
        // yaw 0 = facing south (+Z); your right is west (-X)
        assertEquals("ahead", Direction8.relative(0, 0, 5));
        assertEquals("behind", Direction8.relative(0, 0, -5));
        assertEquals("right", Direction8.relative(0, -5, 0));
        assertEquals("left", Direction8.relative(0, 5, 0));
        assertEquals("behind-left", Direction8.relative(0, 4, -4));
        // yaw 90 = facing west (-X)
        assertEquals("ahead", Direction8.relative(90, -5, 0));
        assertEquals("behind", Direction8.relative(90, 5, 0));
    }

    @Test
    void autoQualityStepsDownWhenSlowAndUpWhenFast() {
        Quality q = new Quality("auto");
        assertEquals(Quality.Level.MEDIUM, q.level());
        for (int i = 0; i < Quality.SECONDS_BEFORE_DOWN; i++) q.update(20, false);
        assertEquals(Quality.Level.LOW, q.level());
        for (int i = 0; i < Quality.SECONDS_BEFORE_UP; i++) q.update(120, false);
        assertEquals(Quality.Level.MEDIUM, q.level());
        for (int i = 0; i < Quality.SECONDS_BEFORE_UP; i++) q.update(120, false);
        assertEquals(Quality.Level.HIGH, q.level());
        q.update(120, true); // switched to Fast graphics: capped at MEDIUM
        assertEquals(Quality.Level.MEDIUM, q.level());
    }

    @Test
    void oneSlowSecondDoesNotDropQuality() {
        Quality q = new Quality("auto");
        q.update(20, false);
        q.update(60, false);
        q.update(20, false);
        assertEquals(Quality.Level.MEDIUM, q.level());
    }

    @Test
    void fixedQualityNeverChanges() {
        Quality q = new Quality("high");
        for (int i = 0; i < 10; i++) q.update(5, false);
        assertEquals(Quality.Level.HIGH, q.level());
        assertFalse(q.isAuto());
    }

    @Test
    void sphereIsUnitAndOutwardFacing() {
        SphereMesh m = new SphereMesh(12, 8);
        assertEquals(96, m.quads);
        for (int i = 0; i < m.quads * 4; i++) {
            double x = m.xyz[i * 3], y = m.xyz[i * 3 + 1], z = m.xyz[i * 3 + 2];
            assertEquals(1.0, Math.sqrt(x * x + y * y + z * z), 1e-5);
        }
        // first non-degenerate quad on the equator: its winding normal must point outward
        int q = 4 * 12 + 3; // stack 4 of 8 (just below the equator), any slice
        float[] a = corner(m, q, 0), b = corner(m, q, 1), c = corner(m, q, 2);
        double[] n = cross(sub(b, a), sub(c, a));
        double dot = n[0] * a[0] + n[1] * a[1] + n[2] * a[2];
        assertTrue(dot > 0, "quads must be counter-clockwise seen from outside");
    }

    @Test
    void moodColors() {
        assertEquals(0x000000, Mood.blend(0x000000, 0xFFFFFF, 0f));
        assertEquals(0xFFFFFF, Mood.blend(0x000000, 0xFFFFFF, 1f));
        int mid = Mood.blend(0x000000, 0xFFFFFF, 0.5f);
        assertTrue(mid == 0x808080 || mid == 0x7F7F7F);
        assertEquals(Mood.SCARED, Mood.parse(" scared ", Mood.HAPPY));
        assertEquals(Mood.HAPPY, Mood.parse("nonsense", Mood.HAPPY));
        assertEquals(0x7F7F7F, Mood.shade(0xFEFEFE, 0.5f));
    }

    @Test
    void tokenIsCreatedOnceAndReused(@TempDir Path dir) throws Exception {
        Path f = dir.resolve("sub").resolve("token");
        String a = TokenFile.readOrCreate(f);
        String b = TokenFile.readOrCreate(f);
        assertEquals(48, a.length());
        assertEquals(a, b);
        assertEquals(a, Files.readString(f).trim());
    }

    private static float[] corner(SphereMesh m, int quad, int k) {
        int i = (quad * 4 + k) * 3;
        return new float[]{m.xyz[i], m.xyz[i + 1], m.xyz[i + 2]};
    }

    private static double[] sub(float[] a, float[] b) {
        return new double[]{a[0] - b[0], a[1] - b[1], a[2] - b[2]};
    }

    private static double[] cross(double[] u, double[] v) {
        return new double[]{u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]};
    }
}
