package dev.kindredspirit.audio;

import dev.kindredspirit.KindredSpiritClient;
import dev.kindredspirit.util.Wav;

import javax.sound.sampled.AudioFormat;
import javax.sound.sampled.AudioSystem;
import javax.sound.sampled.TargetDataLine;
import java.io.ByteArrayOutputStream;
import java.util.function.BiConsumer;

/**
 * Push-to-talk microphone: 16 kHz mono 16-bit, the format Whisper wants, so nothing is resampled.
 * Records on its own thread; the result (a WAV) is handed back on that thread.
 */
public final class VoiceRecorder {
    public static final int RATE = 16000;
    private static final AudioFormat FORMAT = new AudioFormat(RATE, 16, 1, true, false);

    private volatile boolean recording;
    private volatile String lastError = "";

    public boolean isRecording() {
        return recording;
    }

    public String lastError() {
        return lastError;
    }

    /**
     * @param onDone gets (wav, peak). Peak is the loudest sample (0..32768): near 0 means the
     *               microphone gave silence, usually a missing macOS permission.
     */
    public void start(int maxSeconds, BiConsumer<byte[], Integer> onDone) {
        if (recording) return;
        recording = true;
        Thread t = new Thread(() -> run(maxSeconds, onDone), "kindred-mic");
        t.setDaemon(true);
        t.start();
    }

    public void stop() {
        recording = false;
    }

    private void run(int maxSeconds, BiConsumer<byte[], Integer> onDone) {
        ByteArrayOutputStream pcm = new ByteArrayOutputStream(RATE * 2 * 5);
        TargetDataLine line = null;
        try {
            line = AudioSystem.getTargetDataLine(FORMAT);
            line.open(FORMAT, RATE / 5); // 100 ms buffer
            line.start();
            byte[] buf = new byte[RATE / 10]; // 50 ms chunks
            long limit = (long) maxSeconds * RATE * 2;
            while (recording && pcm.size() < limit) {
                int n = line.read(buf, 0, buf.length);
                if (n > 0) pcm.write(buf, 0, n);
            }
            lastError = "";
        } catch (Exception e) {
            lastError = e.getMessage() == null ? e.toString() : e.getMessage();
            KindredSpiritClient.LOG.warn("Microphone unavailable: {}", lastError);
        } finally {
            recording = false;
            if (line != null) {
                line.stop();
                line.close();
            }
        }
        byte[] data = pcm.toByteArray();
        if (data.length < RATE * 2 * 3 / 10) return; // under 0.3 s: an accidental tap
        onDone.accept(Wav.encodePcm16Mono(data, RATE), Wav.peak(data));
    }
}
