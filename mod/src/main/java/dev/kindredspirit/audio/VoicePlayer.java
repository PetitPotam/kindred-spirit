package dev.kindredspirit.audio;

import dev.kindredspirit.KindredSpiritClient;
import dev.kindredspirit.util.Wav;

import javax.sound.sampled.AudioInputStream;
import javax.sound.sampled.AudioSystem;
import javax.sound.sampled.Clip;
import javax.sound.sampled.FloatControl;
import javax.sound.sampled.LineEvent;
import java.io.ByteArrayInputStream;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * Plays the companion's voice on its own thread. A reply arrives sentence by sentence: the first
 * sentence starts a new line ({@link #play}), the rest are queued behind it ({@link #enqueue}).
 * Starting a new line drops whatever was still playing or queued, which is what you want when a
 * danger warning interrupts small talk. The renderer asks {@link #level()} for mouth movement.
 */
public final class VoicePlayer {
    private static final int WINDOW_MS = 40;

    private record Piece(byte[] wav, float[] envelope, float volume, int generation) {}

    private final LinkedBlockingQueue<Piece> queue = new LinkedBlockingQueue<>();
    private volatile int generation;
    private volatile Clip clip;
    private volatile float[] envelope = new float[0];
    private volatile boolean busy;

    public VoicePlayer() {
        Thread t = new Thread(this::run, "kindred-voice");
        t.setDaemon(true);
        t.start();
    }

    /** Starts a new line, dropping anything older. Returns the clip length in seconds. */
    public double play(byte[] wav, float volume) {
        stop();
        return enqueue(wav, volume);
    }

    /** Plays after what is already queued. Returns the clip length in seconds (0 if unreadable). */
    public double enqueue(byte[] wav, float volume) {
        Wav.Info info = Wav.parse(wav);
        if (info == null) return 0;
        queue.add(new Piece(wav, Wav.envelope(wav, WINDOW_MS), volume, generation));
        return info.seconds();
    }

    /** Silences the current line and forgets the queued ones. */
    public void stop() {
        generation++;
        queue.clear();
        Clip c = clip;
        if (c != null) c.stop(); // wakes the audio thread through the STOP event
    }

    public boolean isPlaying() {
        return busy || !queue.isEmpty();
    }

    /** 0..1, how open the mouth should be now. Cheap: one array lookup. */
    public float level() {
        Clip c = clip;
        float[] env = envelope;
        if (c == null || env.length == 0) return 0;
        int i = (int) (c.getMicrosecondPosition() / 1000 / WINDOW_MS);
        return i >= 0 && i < env.length ? env[i] : 0;
    }

    private void run() {
        while (true) {
            Piece p;
            try {
                p = queue.take();
            } catch (InterruptedException e) {
                return;
            }
            if (p.generation != generation) continue;
            busy = true;
            try (AudioInputStream in = AudioSystem.getAudioInputStream(new ByteArrayInputStream(p.wav))) {
                Clip c = AudioSystem.getClip();
                CountDownLatch done = new CountDownLatch(1);
                c.addLineListener(e -> {
                    if (e.getType() == LineEvent.Type.STOP) done.countDown();
                });
                c.open(in);
                if (c.isControlSupported(FloatControl.Type.MASTER_GAIN)) {
                    FloatControl gain = (FloatControl) c.getControl(FloatControl.Type.MASTER_GAIN);
                    float db = p.volume <= 0.0001f ? gain.getMinimum() : (float) (20 * Math.log10(p.volume));
                    gain.setValue(Math.max(gain.getMinimum(), Math.min(gain.getMaximum(), db)));
                }
                envelope = p.envelope;
                clip = c;
                if (p.generation == generation) {
                    c.start();
                    done.await(c.getMicrosecondLength() / 1000 + 1500, TimeUnit.MILLISECONDS);
                }
                clip = null;
                envelope = new float[0];
                c.close();
            } catch (Exception e) {
                KindredSpiritClient.LOG.warn("Could not play voice: {}", e.toString());
                clip = null;
            } finally {
                busy = false;
            }
        }
    }
}
