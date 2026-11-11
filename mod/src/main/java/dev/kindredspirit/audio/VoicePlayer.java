package dev.kindredspirit.audio;

import dev.kindredspirit.KindredSpiritClient;
import dev.kindredspirit.util.Wav;

import javax.sound.sampled.AudioInputStream;
import javax.sound.sampled.AudioSystem;
import javax.sound.sampled.Clip;
import javax.sound.sampled.FloatControl;
import java.io.ByteArrayInputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Plays the companion's voice (WAV from the brain) on its own thread and tells the renderer how
 * loud it is right now, so the mouth moves with the words. A new line replaces the current one,
 * which is what you want when a danger warning interrupts small talk.
 */
public final class VoicePlayer {
    private static final int WINDOW_MS = 40;
    private final ExecutorService audio = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "kindred-voice");
        t.setDaemon(true);
        return t;
    });
    private volatile Clip clip;
    private volatile float[] envelope = new float[0];

    /** Decodes and starts playing; returns the clip length in seconds (0 if it could not play). */
    public double play(byte[] wav, float volume) {
        Wav.Info info = Wav.parse(wav);
        if (info == null) return 0;
        float[] env = Wav.envelope(wav, WINDOW_MS);
        audio.execute(() -> {
            stopNow();
            try (AudioInputStream in = AudioSystem.getAudioInputStream(new ByteArrayInputStream(wav))) {
                Clip c = AudioSystem.getClip();
                c.open(in);
                if (c.isControlSupported(FloatControl.Type.MASTER_GAIN)) {
                    FloatControl gain = (FloatControl) c.getControl(FloatControl.Type.MASTER_GAIN);
                    float db = volume <= 0.0001f ? gain.getMinimum() : (float) (20 * Math.log10(volume));
                    gain.setValue(Math.max(gain.getMinimum(), Math.min(gain.getMaximum(), db)));
                }
                envelope = env;
                clip = c;
                c.start();
            } catch (Exception e) {
                KindredSpiritClient.LOG.warn("Could not play voice: {}", e.toString());
            }
        });
        return info.seconds();
    }

    public void stop() {
        audio.execute(this::stopNow);
    }

    private void stopNow() {
        Clip c = clip;
        clip = null;
        envelope = new float[0];
        if (c != null) {
            c.stop();
            c.close();
        }
    }

    public boolean isPlaying() {
        Clip c = clip;
        return c != null && c.isRunning();
    }

    /** 0..1, how open the mouth should be now. Cheap: one array lookup. */
    public float level() {
        Clip c = clip;
        float[] env = envelope;
        if (c == null || env.length == 0 || !c.isRunning()) return 0;
        int i = (int) (c.getMicrosecondPosition() / 1000 / WINDOW_MS);
        return i >= 0 && i < env.length ? env[i] : 0;
    }
}
