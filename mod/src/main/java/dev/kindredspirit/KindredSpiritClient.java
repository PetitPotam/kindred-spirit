package dev.kindredspirit;

import com.google.gson.JsonObject;
import com.mojang.blaze3d.platform.InputConstants;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.tree.LiteralCommandNode;
import dev.kindredspirit.act.Abilities;
import dev.kindredspirit.act.Actions;
import dev.kindredspirit.audio.VoicePlayer;
import dev.kindredspirit.audio.VoiceRecorder;
import dev.kindredspirit.life.Behavior;
import dev.kindredspirit.life.Emote;
import dev.kindredspirit.render.CompanionRenderer;
import dev.kindredspirit.skin.SkinRegistry;
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
import net.fabricmc.fabric.api.resource.ResourceManagerHelper;
import net.fabricmc.fabric.api.resource.SimpleSynchronousResourceReloadListener;
import net.minecraft.commands.SharedSuggestionProvider;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.packs.PackType;
import net.minecraft.server.packs.resources.ResourceManager;
import net.minecraft.world.phys.Vec3;
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
    private Companion companion;
    private final SkinRegistry skins = new SkinRegistry();
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

    public Companion companion() {
        return companion;
    }

    @Override
    public void onInitializeClient() {
        instance = this;
        cfg = KindredConfig.load();
        displayName = cfg.name;
        quality = new Quality(cfg.quality);
        companion = new Companion(cfg);
        ResourceManagerHelper.get(PackType.CLIENT_RESOURCES).registerReloadListener(new SimpleSynchronousResourceReloadListener() {
            @Override
            public ResourceLocation getFabricId() {
                return ResourceLocation.fromNamespaceAndPath("kindredspirit", "skins");
            }

            @Override
            public void onResourceManagerReload(ResourceManager manager) {
                skins.reload(manager);
                companion.skin = skins.get(cfg.skin);
            }
        });
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
        WorldRenderEvents.START.register(ctx -> {
            if (devScript != null) devScript.frame(Minecraft.getInstance());
        });
        WorldRenderEvents.AFTER_ENTITIES.register(ctx -> {
            Minecraft mc = Minecraft.getInstance();
            if (mc.player == null || mc.player.isSpectator()) return;
            float partial = ctx.tickCounter().getGameTimeDeltaPartialTick(false);
            if (companion.activity == Behavior.Activity.SPEAKING && !voice.isPlaying()
                    && System.currentTimeMillis() > speakingGrace) {
                companion.activity = Behavior.Activity.IDLE;
            }
            companion.frame(mc.player, partial, voice.level());
            renderer.render(ctx, companion, skins.texture(companion.skin), cfg, quality.level(), System.currentTimeMillis());
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
                                + " | skin: " + companion.skin.id() + " | mode: " + companion.life.mode.name().toLowerCase()
                                + " | quality: " + quality.level().name().toLowerCase() + (quality.isAuto() ? " (auto)" : "")
                                + " | mood: " + companion.mood.name().toLowerCase()));
                        return 1;
                    }))
                    .then(ClientCommandManager.literal("skin")
                            .executes(c -> {
                                c.getSource().sendFeedback(Component.literal("Skin: " + companion.skin.name()
                                        + " (" + companion.skin.id() + "). Others: " + String.join(", ", skins.ids())));
                                return 1;
                            })
                            .then(ClientCommandManager.argument("id", StringArgumentType.word())
                                    .suggests((c, b) -> SharedSuggestionProvider.suggest(skins.ids(), b))
                                    .executes(c -> {
                                        String id = StringArgumentType.getString(c, "id");
                                        if (!skins.has(id)) {
                                            c.getSource().sendError(Component.literal("No skin called " + id + ". Try: " + String.join(", ", skins.ids())));
                                            return 0;
                                        }
                                        setSkin(id);
                                        c.getSource().sendFeedback(Component.literal("Now wearing " + companion.skin.name()));
                                        return 1;
                                    })))
                    .then(ClientCommandManager.literal("skins")
                            .executes(c -> {
                                c.getSource().sendFeedback(Component.literal("Skins: " + String.join(", ", skins.ids())
                                        + ". Add your own in " + SkinRegistry.userDir()));
                                return 1;
                            })
                            .then(ClientCommandManager.literal("reload").executes(c -> {
                                Minecraft.getInstance().execute(() -> {
                                    skins.reload(Minecraft.getInstance().getResourceManager());
                                    companion.skin = skins.get(cfg.skin);
                                });
                                c.getSource().sendFeedback(Component.literal("Skins reloaded"));
                                return 1;
                            })))
                    .then(ClientCommandManager.literal("life")
                            .executes(c -> {
                                c.getSource().sendFeedback(Component.literal("Liveliness: " + LifeSwitches.describe(cfg.life)
                                        + ". Change one with /kindred life <name> <value>, or /kindred life reset."));
                                return 1;
                            })
                            .then(ClientCommandManager.literal("reset").executes(c -> {
                                LifeSwitches.reset(cfg.life);
                                cfg.save();
                                c.getSource().sendFeedback(Component.literal("Liveliness back to the defaults"));
                                return 1;
                            }))
                            .then(ClientCommandManager.argument("name", StringArgumentType.word())
                                    .suggests((c, b) -> SharedSuggestionProvider.suggest(LifeSwitches.names(), b))
                                    .executes(c -> {
                                        String n = StringArgumentType.getString(c, "name");
                                        String v = LifeSwitches.get(cfg.life, n);
                                        if (v == null) {
                                            c.getSource().sendError(Component.literal("No switch called " + n + ". Try: " + String.join(", ", LifeSwitches.names())));
                                            return 0;
                                        }
                                        c.getSource().sendFeedback(Component.literal(n + " = " + v + " (" + LifeSwitches.help(n) + ")"));
                                        return 1;
                                    })
                                    .then(ClientCommandManager.argument("value", StringArgumentType.word())
                                            .suggests((c, b) -> SharedSuggestionProvider.suggest(
                                                    LifeSwitches.suggestions(StringArgumentType.getString(c, "name")), b))
                                            .executes(c -> {
                                                String n = StringArgumentType.getString(c, "name");
                                                String err = LifeSwitches.set(cfg.life, n, StringArgumentType.getString(c, "value"));
                                                if (err != null) {
                                                    c.getSource().sendError(Component.literal(err));
                                                    return 0;
                                                }
                                                cfg.save();
                                                c.getSource().sendFeedback(Component.literal(n + " = " + LifeSwitches.get(cfg.life, n)));
                                                return 1;
                                            }))))
                    .then(ClientCommandManager.literal("power")
                            .executes(c -> {
                                c.getSource().sendFeedback(Component.literal("Power: " + cfg.power + ", style: " + cfg.style
                                        + ". It may: " + String.join(", ", Abilities.allowedIds(Abilities.power(cfg.power), Abilities.style(cfg.style)))));
                                return 1;
                            })
                            .then(ClientCommandManager.argument("level", StringArgumentType.word())
                                    .suggests((c, b) -> SharedSuggestionProvider.suggest(new String[]{"advisor", "helper", "allpowerful"}, b))
                                    .executes(c -> {
                                        String v = StringArgumentType.getString(c, "level").toLowerCase();
                                        if (!v.matches("advisor|helper|allpowerful")) {
                                            c.getSource().sendError(Component.literal("Power is advisor, helper or allpowerful"));
                                            return 0;
                                        }
                                        cfg.power = v;
                                        cfg.save();
                                        sendAbilities();
                                        c.getSource().sendFeedback(Component.literal("Power: " + v));
                                        return 1;
                                    })))
                    .then(ClientCommandManager.literal("style")
                            .then(ClientCommandManager.argument("style", StringArgumentType.word())
                                    .suggests((c, b) -> SharedSuggestionProvider.suggest(new String[]{"grounded", "magic"}, b))
                                    .executes(c -> {
                                        String v = StringArgumentType.getString(c, "style").toLowerCase();
                                        if (!v.matches("grounded|magic")) {
                                            c.getSource().sendError(Component.literal("Style is grounded or magic"));
                                            return 0;
                                        }
                                        cfg.style = v;
                                        cfg.save();
                                        sendAbilities();
                                        c.getSource().sendFeedback(Component.literal("Style: " + v));
                                        return 1;
                                    })))
                    .then(ClientCommandManager.literal("emote")
                            .then(ClientCommandManager.argument("name", StringArgumentType.word())
                                    .suggests((c, b) -> SharedSuggestionProvider.suggest(
                                            java.util.Arrays.stream(Emote.values()).map(e -> e.name().toLowerCase()), b))
                                    .executes(c -> act("emote", StringArgumentType.getString(c, "name")))))
                    .then(ClientCommandManager.literal("mode")
                            .then(ClientCommandManager.argument("mode", StringArgumentType.word())
                                    .suggests((c, b) -> SharedSuggestionProvider.suggest(new String[]{"follow", "stay", "come"}, b))
                                    .executes(c -> act("move", StringArgumentType.getString(c, "mode")))))
                    .then(ClientCommandManager.literal("side")
                            .then(ClientCommandManager.argument("side", StringArgumentType.word())
                                    .suggests((c, b) -> SharedSuggestionProvider.suggest(new String[]{"right", "left", "above", "auto"}, b))
                                    .executes(c -> act("side", StringArgumentType.getString(c, "side")))))
                    .then(ClientCommandManager.literal("look")
                            .then(ClientCommandManager.argument("at", StringArgumentType.word())
                                    .suggests((c, b) -> SharedSuggestionProvider.suggest(new String[]{"me", "there", "ahead", "up", "down", "around"}, b))
                                    .executes(c -> act("look", StringArgumentType.getString(c, "at")))))
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
        if (companion.tick(mc)) event("petted");
        if (companion.life.arrived) {
            companion.life.arrived = false;
            event("arrived");
        }

        // push-to-talk: hold the key, speak, release
        boolean held = talkKey.isDown() && mc.screen == null;
        if (held && !recorder.isRecording() && companion.activity != Behavior.Activity.LISTENING) {
            if (!link.connected()) {
                notice("The Kindred brain is not running. Start it with scripts/start.sh", 5000);
            } else {
                voice.stop();
                companion.activity = Behavior.Activity.LISTENING;
                recorder.start(cfg.maxRecordSeconds, this::onRecorded);
            }
        } else if (!held && companion.activity == Behavior.Activity.LISTENING) {
            recorder.stop();
            companion.activity = Behavior.Activity.THINKING;
            speakingGrace = now + 15000; // give up "thinking" if nothing comes back
        }
        if (companion.activity == Behavior.Activity.THINKING && now > speakingGrace) {
            companion.activity = Behavior.Activity.IDLE;
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
        companion.activity = Behavior.Activity.THINKING;
        speakingGrace = System.currentTimeMillis() + 15000;
    }

    /** As if the player held the talk key and said this (used by the sandbox test script). */
    public void sendVoice(byte[] wav) {
        onRecorded(wav, 9000);
        companion.activity = Behavior.Activity.THINKING;
        speakingGrace = System.currentTimeMillis() + 15000;
    }

    public KindredConfig config() {
        return cfg;
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
                    dev.kindredspirit.record.FrameRecorder.line("pip", text);
                    Emote gesture = Emote.parse(str(msg, "emote"));
                    if (gesture != null && cfg.life.aiGestures) companion.life.play(gesture, companion.now());
                    boolean talking = secs > 0 || more;
                    companion.activity = talking ? Behavior.Activity.SPEAKING : Behavior.Activity.IDLE;
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
                    companion.activity = Behavior.Activity.SPEAKING;
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
            case "act" -> mc.execute(() -> applyAct(msg));
            case "do" -> mc.execute(() -> runAction(msg));
            case "state" -> mc.execute(() -> {
                String s = str(msg, "state");
                if (s.equals("thinking")) {
                    companion.activity = Behavior.Activity.THINKING;
                    speakingGrace = System.currentTimeMillis() + 15000;
                } else if (s.equals("idle") && companion.activity == Behavior.Activity.THINKING) {
                    companion.activity = Behavior.Activity.IDLE;
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
        addAbilities(hello);
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
            if (companion.activity != Behavior.Activity.SPEAKING) companion.activity = Behavior.Activity.IDLE;
        });
    }

    private void event(String name) {
        JsonObject o = new JsonObject();
        o.addProperty("type", "event");
        o.addProperty("event", name);
        if (name.equals("join")) o.addProperty("world", worldId());
        link.send(o);
    }

    /** Which world this is, so the brain keeps a memory per world: the save folder, or the server address. */
    private static String worldId() {
        Minecraft mc = Minecraft.getInstance();
        if (mc.getSingleplayerServer() != null) {
            return "sp:" + mc.getSingleplayerServer().getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT)
                    .toAbsolutePath().normalize().getFileName();
        }
        return mc.getCurrentServer() != null ? "mp:" + mc.getCurrentServer().ip : "unknown";
    }

    private void addAbilities(JsonObject o) {
        Abilities.Power p = Abilities.power(cfg.power);
        Abilities.Style s = Abilities.style(cfg.style);
        o.addProperty("power", p.name().toLowerCase());
        o.addProperty("style", s.name().toLowerCase());
        com.google.gson.JsonArray a = new com.google.gson.JsonArray();
        for (String id : Abilities.allowedIds(p, s)) a.add(id);
        o.add("abilities", a);
        o.addProperty("singleplayer", Minecraft.getInstance().getSingleplayerServer() != null);
    }

    private void sendAbilities() {
        JsonObject o = new JsonObject();
        o.addProperty("type", "abilities");
        addAbilities(o);
        link.send(o);
    }

    /** The brain asks for an action; the answer goes back as {"type": "done", "id": ..., ...}. */
    private void runAction(JsonObject msg) {
        String id = str(msg, "id"), action = str(msg, "action");
        JsonObject args = msg.has("args") && msg.get("args").isJsonObject() ? msg.getAsJsonObject("args") : new JsonObject();
        java.util.function.Consumer<JsonObject> reply = res -> {
            res.addProperty("type", "done");
            res.addProperty("id", id);
            link.send(res);
        };
        Behavior life = companion.life;
        if (action.equals("guide")) {
            double[] t = Actions.lastTarget;
            if (args.has("x") && args.has("z")) {
                t = new double[]{args.get("x").getAsDouble() + 0.5, args.has("y") ? args.get("y").getAsDouble() : 64,
                        args.get("z").getAsDouble() + 0.5};
            }
            JsonObject res = new JsonObject();
            if (t == null) {
                res.addProperty("ok", false);
                res.addProperty("error", "Guide where? Find or locate something first, or give coordinates.");
            } else {
                life.guide(t[0], t[1], t[2], companion.now());
                res.addProperty("ok", true);
                res.addProperty("guiding", true);
                double dx = t[0] - Minecraft.getInstance().player.getX(), dz = t[2] - Minecraft.getInstance().player.getZ();
                res.addProperty("distance", Math.round(Math.sqrt(dx * dx + dz * dz)));
            }
            reply.accept(res);
            return;
        }
        if (action.equals("stop_guide")) {
            if (life.mode == Behavior.Mode.GUIDE) life.setMode(Behavior.Mode.FOLLOW, companion.now());
            JsonObject res = new JsonObject();
            res.addProperty("ok", true);
            reply.accept(res);
            return;
        }
        Actions.run(action, args, Abilities.power(cfg.power), Abilities.style(cfg.style))
                .thenAccept(res -> Minecraft.getInstance().execute(() -> reply.accept(res)));
    }

    // ------------------------------------------------------------------ moving and posing it

    /** A command typed in game: same effect as the brain's "act" message. */
    private int act(String key, String value) {
        JsonObject o = new JsonObject();
        o.addProperty(key, value);
        applyAct(o);
        return 1;
    }

    /**
     * Moves or poses the companion: {"move": "stay|follow|come", "side": "left|right|above|auto",
     * "look": "me|there|ahead|up|down|around", "emote": "spin|nod|...", "seconds": 3}.
     * Sent by the brain (when you say "stay here", "look at me", "do a spin") or by /kindred commands.
     * Everything eases in: it is a request to a living thing, not a teleport.
     */
    public void applyAct(JsonObject msg) {
        Minecraft mc = Minecraft.getInstance();
        Behavior life = companion.life;
        double now = companion.now();
        double seconds = msg.has("seconds") ? msg.get("seconds").getAsDouble() : 4;
        switch (str(msg, "move")) {
            case "stop" -> {
                if (life.mode == Behavior.Mode.GUIDE) life.setMode(Behavior.Mode.FOLLOW, now);
            }
            case "stay" -> life.setMode(Behavior.Mode.STAY, now);
            case "follow" -> life.setMode(Behavior.Mode.FOLLOW, now);
            case "come" -> life.setMode(Behavior.Mode.COME, now, msg.has("seconds") ? seconds : 6);
            default -> { }
        }
        switch (str(msg, "side")) {
            case "left" -> life.setSide(Behavior.Side.LEFT);
            case "right" -> life.setSide(Behavior.Side.RIGHT);
            case "above" -> life.setSide(Behavior.Side.ABOVE);
            case "auto" -> life.setSide(null);
            default -> { }
        }
        Vec3 view = mc.player != null ? mc.player.getViewVector(1f) : new Vec3(0, 0, 1);
        switch (str(msg, "look")) {
            case "me" -> life.lookAt(Behavior.GazeKind.PLAYER, 0, 0, 0, seconds, now);
            case "there" -> life.lookAt(Behavior.GazeKind.SHARED, 0, 0, 0, seconds, now);
            case "ahead" -> life.lookAt(Behavior.GazeKind.DIRECTION, view.x, 0, view.z, seconds, now);
            case "up" -> life.lookAt(Behavior.GazeKind.DIRECTION, view.x * 0.3, 1, view.z * 0.3, seconds, now);
            case "down" -> life.lookAt(Behavior.GazeKind.DIRECTION, view.x * 0.3, -1, view.z * 0.3, seconds, now);
            case "around" -> life.lookAt(Behavior.GazeKind.DIRECTION, -view.z, 0.1, view.x, seconds, now);
            default -> { }
        }
        Emote e = Emote.parse(str(msg, "emote"));
        if (e != null) life.play(e, now);
    }

    private void setSkin(String id) {
        cfg.skin = id;
        cfg.save();
        companion.skin = skins.get(id);
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
        if (companion.activity == Behavior.Activity.LISTENING) {
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
