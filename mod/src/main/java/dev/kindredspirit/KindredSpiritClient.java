package dev.kindredspirit;

import com.google.gson.JsonObject;
import com.mojang.blaze3d.platform.InputConstants;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.tree.LiteralCommandNode;
import dev.kindredspirit.audio.VoicePlayer;
import dev.kindredspirit.audio.VoiceRecorder;
import dev.kindredspirit.render.CompanionRenderer;
import dev.kindredspirit.util.Mood;
import dev.kindredspirit.util.Quality;
import dev.kindredspirit.util.TokenFile;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.command.v2.ClientCommandManager;
import net.fabricmc.fabric.api.client.command.v2.ClientCommandRegistrationCallback;
import net.fabricmc.fabric.api.client.command.v2.FabricClientCommandSource;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayConnectionEvents;
import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.fabricmc.fabric.api.client.rendering.v1.WorldRenderEvents;
import net.minecraft.ChatFormatting;
import net.minecraft.client.GraphicsStatus;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.network.chat.Component;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.entity.monster.Creeper;
import org.lwjgl.glfw.GLFW;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.file.Path;
import java.util.Base64;

/**
 * Kindred Spirit, client side. The mod only sees, draws and plays sound; everything the companion
 * thinks happens in the brain (a Python program beside the game) over a local WebSocket.
 * Nothing is registered in the game (no entities, blocks or items) and nothing is written to your
 * world, so it is safe to add to or remove from any save.
 */
public final class KindredSpiritClient implements ClientModInitializer {
    public static final Logger LOG = LoggerFactory.getLogger("kindredspirit");
    private static KindredSpiritClient instance;

    private KindredConfig cfg;
    private Quality quality;
    private BrainLink link;
    private final Companion companion = new Companion();
    private final CompanionRenderer renderer = new CompanionRenderer();
    private final VoiceRecorder recorder = new VoiceRecorder();
    private final VoicePlayer voice = new VoicePlayer();
    private KeyMapping talkKey;
    private DevScript devScript;

    private String displayName;
    private long nextSnapshot, nextUrgentCheck, nextQualityCheck, lastUrgentSnapshot;
    private float lastHealth = -1;
    private boolean creeperClose;
    private boolean inWorld;
    private long joinedAt;
    private String notice = "";
    private long noticeUntil;
    private String caption = "";
    private long captionUntil;

    public static KindredSpiritClient get() {
        return instance;
    }

    @Override
    public void onInitializeClient() {
        instance = this;
        cfg = KindredConfig.load();
        displayName = cfg.name;
        quality = new Quality(cfg.quality);
        String token;
        try {
            token = TokenFile.readOrCreate(cfg.tokenFile.isBlank() ? TokenFile.defaultPath() : Path.of(cfg.tokenFile));
        } catch (Exception e) {
            LOG.error("Could not read or create the brain token: {}", e.toString());
            token = "";
        }
        link = new BrainLink(cfg.brainHost, cfg.brainPort, token, this::onBrainMessage, this::onBrainOpen, this::onBrainClose);

        talkKey = KeyBindingHelper.registerKeyBinding(new KeyMapping(
                "key.kindredspirit.talk", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_V, "category.kindredspirit"));

        ClientTickEvents.END_CLIENT_TICK.register(this::tick);
        WorldRenderEvents.AFTER_ENTITIES.register(ctx -> {
            Minecraft mc = Minecraft.getInstance();
            if (mc.player == null || mc.player.isSpectator()) return;
            float partial = ctx.tickCounter().getGameTimeDeltaPartialTick(false);
            if (companion.activity == Companion.Activity.SPEAKING && !voice.isPlaying()
                    && System.currentTimeMillis() > speakingGrace) {
                companion.activity = Companion.Activity.IDLE;
            }
            companion.update(mc.player, partial, cfg, voice.level());
            renderer.render(ctx, companion, cfg, quality.level(), System.currentTimeMillis());
        });
        HudRenderCallback.EVENT.register((g, delta) -> hud(g));
        ClientCommandRegistrationCallback.EVENT.register((dispatcher, registry) -> {
            LiteralCommandNode<FabricClientCommandSource> root = dispatcher.register(ClientCommandManager.literal("kindred")
                    .then(ClientCommandManager.literal("reconnect").executes(c -> {
                        link.reconnectNow();
                        c.getSource().sendFeedback(Component.literal("Reconnecting to the Kindred brain..."));
                        return 1;
                    }))
                    .then(ClientCommandManager.literal("status").executes(c -> {
                        c.getSource().sendFeedback(Component.literal("Brain: " + (link.connected() ? "connected" : "not connected")
                                + " | quality: " + quality.level().name().toLowerCase() + (quality.isAuto() ? " (auto)" : "")
                                + " | mood: " + companion.mood.name().toLowerCase()));
                        return 1;
                    }))
                    .then(ClientCommandManager.argument("message", StringArgumentType.greedyString()).executes(c -> {
                        talk(StringArgumentType.getString(c, "message"));
                        return 1;
                    })));
            dispatcher.register(ClientCommandManager.literal("ks").redirect(root));
        });
        ClientPlayConnectionEvents.JOIN.register((handler, sender, mc) -> {
            inWorld = true;
            joinedAt = System.currentTimeMillis();
            lastHealth = -1;
            event("join");
        });
        ClientPlayConnectionEvents.DISCONNECT.register((handler, mc) -> {
            inWorld = false;
            voice.stop();
            event("leave");
        });
        devScript = DevScript.load();
        LOG.info("Kindred Spirit ready: brain at ws://{}:{}, quality {}", cfg.brainHost, cfg.brainPort, cfg.quality);
    }

    private long speakingGrace;
    private volatile int currentLine;

    private float volume(Minecraft mc) {
        return cfg.voiceVolume * mc.options.getSoundSourceVolume(SoundSource.MASTER)
                * mc.options.getSoundSourceVolume(SoundSource.VOICE);
    }

    // ------------------------------------------------------------------ game tick (20 per second)

    private void tick(Minecraft mc) {
        link.tick();
        if (devScript != null) devScript.tick(mc);
        long now = System.currentTimeMillis();

        if (now >= nextQualityCheck) {
            nextQualityCheck = now + 1000;
            quality.update(mc.getFps(), mc.options.graphicsMode().get() == GraphicsStatus.FAST);
        }
        if (mc.player == null || mc.level == null) return;

        // push-to-talk: hold the key, speak, release
        boolean held = talkKey.isDown() && mc.screen == null;
        if (held && !recorder.isRecording() && companion.activity != Companion.Activity.LISTENING) {
            if (!link.connected()) {
                notice("The Kindred brain is not running. Start it with scripts/start.sh", 5000);
            } else {
                voice.stop();
                companion.activity = Companion.Activity.LISTENING;
                recorder.start(cfg.maxRecordSeconds, this::onRecorded);
            }
        } else if (!held && companion.activity == Companion.Activity.LISTENING) {
            recorder.stop();
            companion.activity = Companion.Activity.THINKING;
            speakingGrace = now + 15000; // give up "thinking" if nothing comes back
        }
        if (companion.activity == Companion.Activity.THINKING && now > speakingGrace) {
            companion.activity = Companion.Activity.IDLE;
        }

        if (!link.connected()) return;
        // Urgent: health dropped, or a creeper just came close. Checked every 5 ticks over a small
        // area, so it costs almost nothing, and the warning does not wait for the next snapshot.
        boolean urgent = false;
        float health = mc.player.getHealth();
        if (lastHealth >= 0 && health < lastHealth) urgent = true;
        lastHealth = health;
        if (now >= nextUrgentCheck) {
            nextUrgentCheck = now + 250;
            boolean close = !mc.level.getEntitiesOfClass(Creeper.class, mc.player.getBoundingBox().inflate(9),
                    Creeper::isAlive).isEmpty();
            if (close && !creeperClose) urgent = true;
            creeperClose = close;
        }
        if (now >= nextSnapshot || (urgent && now - lastUrgentSnapshot > 400)) {
            if (urgent) lastUrgentSnapshot = now;
            nextSnapshot = now + quality.level().snapshotMs;
            JsonObject snap = Snapshot.build(mc, quality.level().scanRadius);
            if (urgent) snap.addProperty("urgent", true);
            link.send(snap);
        }
    }

    // ------------------------------------------------------------------ talking

    /** Typed message for the companion (/kindred TEXT or /ks TEXT). */
    public void talk(String text) {
        if (!link.connected()) {
            notice("The Kindred brain is not running. Start it with scripts/start.sh", 5000);
            return;
        }
        JsonObject o = new JsonObject();
        o.addProperty("type", "chat");
        o.addProperty("text", text);
        link.send(o);
        logChat(Component.literal("You → " + displayName + ": ").withStyle(ChatFormatting.GRAY)
                .append(Component.literal(text).withStyle(ChatFormatting.WHITE)));
        companion.activity = Companion.Activity.THINKING;
        speakingGrace = System.currentTimeMillis() + 15000;
    }

    private void onRecorded(byte[] wav, int peak) {
        JsonObject o = new JsonObject();
        o.addProperty("type", "voice");
        o.addProperty("peak", peak);
        o.addProperty("wav", Base64.getEncoder().encodeToString(wav));
        link.send(o);
        if (!recorder.lastError().isEmpty()) {
            Minecraft.getInstance().execute(() -> notice("Microphone error: " + recorder.lastError(), 6000));
        }
    }

    // ------------------------------------------------------------------ brain messages (WebSocket thread)

    private void onBrainMessage(JsonObject msg) {
        String type = str(msg, "type");
        Minecraft mc = Minecraft.getInstance();
        switch (type) {
            case "say" -> {
                // a new line: replaces whatever it was saying
                String text = str(msg, "text");
                Mood mood = Mood.parse(str(msg, "mood"), companion.mood);
                String b64 = str(msg, "audio");
                boolean more = msg.has("more") && msg.get("more").getAsBoolean();
                currentLine = msg.has("line") ? msg.get("line").getAsInt() : currentLine + 1;
                // decoded here, off the game thread, then played on the audio thread
                double secs = b64.isEmpty() ? 0 : voice.play(Base64.getDecoder().decode(b64), volume(mc));
                if (b64.isEmpty()) voice.stop();
                mc.execute(() -> {
                    long now = System.currentTimeMillis();
                    companion.mood = mood;
                    companion.say(text, secs, now);
                    boolean talking = secs > 0 || more;
                    companion.activity = talking ? Companion.Activity.SPEAKING : Companion.Activity.IDLE;
                    // the audio thread needs a moment to start; the next sentence may still be on its way
                    speakingGrace = now + (more ? 4000 : 600);
                    caption = text;
                    captionUntil = companion.subtitleUntil;
                    logChat(Component.literal(displayName + ": ").withStyle(ChatFormatting.AQUA)
                            .append(Component.literal(text).withStyle(ChatFormatting.WHITE)));
                });
            }
            case "audio" -> {
                // the next sentence of the current line
                if (!msg.has("line") || msg.get("line").getAsInt() != currentLine) return;
                double secs = voice.enqueue(Base64.getDecoder().decode(str(msg, "audio")), volume(mc));
                mc.execute(() -> {
                    long now = System.currentTimeMillis();
                    companion.extend(secs, now);
                    companion.activity = Companion.Activity.SPEAKING;
                    speakingGrace = now + 600;
                    captionUntil = companion.subtitleUntil;
                });
            }
            case "heard" -> mc.execute(() -> {
                String text = str(msg, "text");
                if (!text.isEmpty()) {
                    logChat(Component.literal("You → " + displayName + ": ").withStyle(ChatFormatting.GRAY)
                            .append(Component.literal(text).withStyle(ChatFormatting.WHITE)));
                }
            });
            case "mood" -> mc.execute(() -> companion.mood = Mood.parse(str(msg, "mood"), companion.mood));
            case "state" -> mc.execute(() -> {
                String s = str(msg, "state");
                if (s.equals("thinking")) {
                    companion.activity = Companion.Activity.THINKING;
                    speakingGrace = System.currentTimeMillis() + 15000;
                } else if (s.equals("idle") && companion.activity == Companion.Activity.THINKING) {
                    companion.activity = Companion.Activity.IDLE;
                }
            });
            case "notice" -> mc.execute(() -> notice(str(msg, "text"), 6000));
            case "welcome" -> mc.execute(() -> {
                String n = str(msg, "name");
                if (!n.isEmpty()) displayName = n;
                companion.mood = Mood.parse(str(msg, "mood"), Mood.HAPPY);
            });
            default -> LOG.debug("Unknown message from brain: {}", type);
        }
    }

    private void onBrainOpen() {
        LOG.info("Connected to the Kindred brain");
        JsonObject hello = new JsonObject();
        hello.addProperty("type", "hello");
        hello.addProperty("mod", "0.1.0");
        hello.addProperty("minecraft", "1.21.1");
        hello.addProperty("name", cfg.name);
        link.send(hello);
        Minecraft.getInstance().execute(() -> {
            companion.mood = Mood.HAPPY;
            nextSnapshot = 0;
            if (inWorld) event("join");
        });
    }

    private void onBrainClose() {
        Minecraft.getInstance().execute(() -> {
            companion.mood = Mood.OFFLINE;
            if (companion.activity != Companion.Activity.SPEAKING) companion.activity = Companion.Activity.IDLE;
        });
    }

    private void event(String name) {
        JsonObject o = new JsonObject();
        o.addProperty("type", "event");
        o.addProperty("event", name);
        link.send(o);
    }

    // ------------------------------------------------------------------ HUD

    private void notice(String text, long ms) {
        notice = text;
        noticeUntil = System.currentTimeMillis() + ms;
    }

    private void logChat(Component c) {
        Minecraft mc = Minecraft.getInstance();
        if (cfg.chatLog && mc.gui != null) mc.gui.getChat().addMessage(c);
    }

    private void hud(GuiGraphics g) {
        Minecraft mc = Minecraft.getInstance();
        if (mc.options.hideGui || mc.player == null) return;
        long now = System.currentTimeMillis();
        int w = g.guiWidth(), h = g.guiHeight();
        if (companion.activity == Companion.Activity.LISTENING) {
            String s = "● Listening... release " + talkKey.getTranslatedKeyMessage().getString() + " to send";
            int x = (w - mc.font.width(s)) / 2;
            g.fill(x - 4, h - 80, x + mc.font.width(s) + 4, h - 68, 0x80000000);
            g.drawString(mc.font, s, x, h - 78, 0xFFFF6B8B);
        }
        if (cfg.hudCaptions && now < captionUntil && !caption.isEmpty()) {
            var lines = mc.font.split(Component.literal(displayName + ": " + caption), Math.min(320, w - 40));
            int y = h - 92 - lines.size() * 10;
            for (var line : lines) {
                int x = (w - mc.font.width(line)) / 2;
                g.fill(x - 3, y - 1, x + mc.font.width(line) + 3, y + 9, 0x90000000);
                g.drawString(mc.font, line, x, y, 0xFFFFFFFF);
                y += 10;
            }
        }
        if (!link.connected() && inWorld && now - joinedAt > 3000 && now - joinedAt < 15000) {
            notice("Kindred brain not connected yet: run scripts/start.sh, then /kindred reconnect", 2000);
        }
        if (now < noticeUntil && !notice.isEmpty()) {
            g.drawString(mc.font, notice, 6, 6, 0xFFFFD27A);
        }
    }

    private static String str(JsonObject o, String key) {
        return o.has(key) && !o.get(key).isJsonNull() ? o.get(key).getAsString() : "";
    }
}
