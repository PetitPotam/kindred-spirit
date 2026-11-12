package dev.kindredspirit.record;

import com.google.gson.JsonObject;
import com.mojang.blaze3d.pipeline.RenderTarget;
import com.mojang.blaze3d.platform.GlStateManager;
import dev.kindredspirit.KindredSpiritClient;
import net.minecraft.client.Minecraft;
import org.lwjgl.opengl.GL11;
import org.lwjgl.opengl.GL30;
import org.lwjgl.system.MemoryUtil;

import java.io.IOException;
import java.io.OutputStream;
import java.io.Writer;
import java.nio.ByteBuffer;
import java.nio.channels.Channels;
import java.nio.channels.WritableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

/**
 * Records the game for demo videos, driven by the sandbox test script ({@code record start NAME}).
 * Frames are read from the game's own image right before it is shown and piped to ffmpeg at a
 * steady 30 frames per second of real time (a slow frame is repeated, extra frames are skipped,
 * so the video plays at true speed). Everything the companion says is saved as WAV with its time,
 * so an editing script can lay the voices back on exactly. Needs ffmpeg on the PATH; does nothing
 * unless a recording was started. Not meant for players (yet): see "Creator mode" in the roadmap.
 */
public final class FrameRecorder {
    private static final int FPS = 30;
    private static volatile FrameRecorder active;

    private final Path dir;
    private final Process ffmpeg;
    private final WritableByteChannel out;
    private final Writer events;
    private final int width, height, frameBytes;
    private final long start = System.nanoTime();
    private final BlockingQueue<ByteBuffer> free = new ArrayBlockingQueue<>(4), full = new ArrayBlockingQueue<>(4);
    private final Thread writer;
    private long written; // frames written so far
    private int clips;
    private volatile boolean stopping;

    private FrameRecorder(Path dir, int width, int height) throws IOException {
        this.dir = dir;
        this.width = width;
        this.height = height;
        this.frameBytes = width * height * 4;
        Files.createDirectories(dir);
        for (int i = 0; i < 4; i++) free.add(MemoryUtil.memAlloc(frameBytes));
        ffmpeg = new ProcessBuilder("ffmpeg", "-y", "-loglevel", "error",
                "-f", "rawvideo", "-pix_fmt", "rgba", "-s", width + "x" + height, "-r", String.valueOf(FPS), "-i", "-",
                "-vf", "vflip", "-c:v", "h264_videotoolbox", "-b:v", "30M", "-pix_fmt", "yuv420p",
                dir.resolve("video.mp4").toString())
                .redirectErrorStream(true).redirectOutput(dir.resolve("ffmpeg.log").toFile()).start();
        OutputStream os = ffmpeg.getOutputStream();
        out = Channels.newChannel(os);
        events = Files.newBufferedWriter(dir.resolve("events.jsonl"), StandardCharsets.UTF_8);
        writer = new Thread(this::writeLoop, "kindred-recorder");
        writer.setDaemon(true);
        writer.start();
    }

    public static boolean recording() {
        return active != null;
    }

    public static void start(Path dir) {
        stop();
        RenderTarget t = Minecraft.getInstance().getMainRenderTarget();
        try {
            active = new FrameRecorder(dir, t.width, t.height);
            KindredSpiritClient.LOG.info("Recording {}x{} to {}", t.width, t.height, dir);
            active.event("start", null, null);
        } catch (IOException e) {
            KindredSpiritClient.LOG.error("Cannot record (is ffmpeg installed?): {}", e.toString());
        }
    }

    public static void stop() {
        FrameRecorder r = active;
        active = null;
        if (r != null) r.close();
    }

    /** Seconds since the recording started (the video's clock). */
    public static double time() {
        FrameRecorder r = active;
        return r == null ? 0 : (System.nanoTime() - r.start) / 1e9;
    }

    /** A named moment ("mark talk"), or a sound to put back in the edit. */
    public static void mark(String name) {
        FrameRecorder r = active;
        if (r != null) r.event("mark", name, null);
    }

    public static void sound(String kind, byte[] wav) {
        FrameRecorder r = active;
        if (r == null) return;
        try {
            String file = kind + "-" + (++r.clips) + ".wav";
            Files.write(r.dir.resolve(file), wav);
            r.event(kind, null, file);
        } catch (IOException e) {
            KindredSpiritClient.LOG.warn("Could not save a sound: {}", e.toString());
        }
    }

    /** What someone said, for captions in the edit. */
    private static volatile int pipLines;

    /** How many lines the companion has said since the game started (for scripts that wait for her). */
    public static int pipLines() {
        return pipLines;
    }

    public static void line(String who, String text) {
        if ("pip".equals(who)) pipLines++;
        FrameRecorder r = active;
        if (r != null) r.event("line", who, null, text);
    }

    public static void soundFile(String kind, Path wav) {
        FrameRecorder r = active;
        if (r != null) r.event(kind, null, wav.toAbsolutePath().toString());
    }

    private void event(String type, String name, String file) {
        event(type, name, file, null);
    }

    private synchronized void event(String type, String name, String file, String text) {
        JsonObject o = new JsonObject();
        o.addProperty("t", Math.round((System.nanoTime() - start) / 1e6) / 1000.0);
        o.addProperty("type", type);
        if (name != null) o.addProperty("name", name);
        if (file != null) o.addProperty("file", file);
        if (text != null) o.addProperty("text", text);
        try {
            events.write(o + "\n");
            events.flush();
        } catch (IOException ignored) {
        }
    }

    /** Called on the render thread right before each frame is shown. */
    public static void captureFrame() {
        FrameRecorder r = active;
        if (r != null) r.capture();
    }

    private void capture() {
        long due = (long) Math.floor((System.nanoTime() - start) / 1e9 * FPS);
        if (due < written + full.size()) return; // this 1/30 s slot is already filled
        RenderTarget t = Minecraft.getInstance().getMainRenderTarget();
        if (t.width != width || t.height != height) return; // window resized: skip
        ByteBuffer buf = free.poll();
        if (buf == null) return; // ffmpeg is behind: the writer repeats the last frame instead
        buf.clear();
        GlStateManager._glBindFramebuffer(GL30.GL_READ_FRAMEBUFFER, t.frameBufferId);
        GL11.glReadPixels(0, 0, width, height, GL11.GL_RGBA, GL11.GL_UNSIGNED_BYTE, buf);
        GlStateManager._glBindFramebuffer(GL30.GL_READ_FRAMEBUFFER, 0);
        buf.limit(frameBytes);
        full.add(buf);
    }

    private void writeLoop() {
        ByteBuffer last = null;
        try {
            while (!stopping || !full.isEmpty()) {
                ByteBuffer b = full.poll(100, java.util.concurrent.TimeUnit.MILLISECONDS);
                if (b == null) continue;
                long due = (long) Math.floor((System.nanoTime() - start) / 1e9 * FPS);
                // fill any gap with the previous frame, so time in the video stays real time
                while (last != null && written < due - 1) {
                    last.rewind();
                    while (last.hasRemaining()) out.write(last);
                    written++;
                }
                b.rewind();
                while (b.hasRemaining()) out.write(b);
                written++;
                if (last != null) free.add(last);
                last = b;
            }
        } catch (Exception e) {
            KindredSpiritClient.LOG.warn("Recorder stopped: {}", e.toString());
        }
    }

    private void close() {
        event("stop", null, null);
        stopping = true;
        try {
            writer.join(5000);
            out.close();
            events.close();
            ffmpeg.waitFor();
            KindredSpiritClient.LOG.info("Recording saved: {} ({} frames)", dir.resolve("video.mp4"), written);
        } catch (Exception e) {
            KindredSpiritClient.LOG.warn("Recording did not close cleanly: {}", e.toString());
        }
    }
}
