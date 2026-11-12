package dev.kindredspirit;

import com.google.gson.JsonObject;
import com.mojang.blaze3d.platform.InputConstants;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.tree.LiteralCommandNode;
import dev.kindredspirit.act.Abilities;
import dev.kindredspirit.act.Actions;
import dev.kindredspirit.util.Direction8;
import dev.kindredspirit.audio.VoicePlayer;
import dev.kindredspirit.audio.VoiceRecorder;
import dev.kindredspirit.guest.GuestBridge;
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
import net.minecraft.core.BlockPos;
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
    /** Light mode: in a friend's LAN world, you see and share their Pip (see SharedPip). */
    private final dev.kindredspirit.guest.SharedPip shared = new dev.kindredspirit.guest.SharedPip();
    private volatile boolean sharing;
    private String notice = "";
    private long noticeUntil;
    private String caption = "";
    private long captionUntil;

    public static KindredSpiritClient get() {
        return instance;
    }

    /** Playing alone: singleplayer and not opened to LAN (with friends on LAN, chat is for them too). */
    static boolean alone(Minecraft mc) {
        var server = mc.getSingleplayerServer();
        return server != null && !server.isPublished();
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
        // her building works block by block on the (integrated) server
        net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents.END_SERVER_TICK.register(
                dev.kindredspirit.act.Builder::tick);
        // friends on your LAN world without the mod: they see a stand-in for her and can talk to her;
        // friends with the mod see her as you do (light mode: SharedPip), with no AI of their own
        net.fabricmc.fabric.api.networking.v1.PayloadTypeRegistry.playS2C().register(
                dev.kindredspirit.guest.PipPayload.TYPE, dev.kindredspirit.guest.PipPayload.CODEC);
        net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking.registerGlobalReceiver(
                dev.kindredspirit.guest.PipPayload.TYPE, (payload, context) -> {
                    String json = payload.json();
                    context.client().execute(() -> shared.receive(json));
                });
        GuestBridge.state = () -> {
            Minecraft m = Minecraft.getInstance();
            if (m.player == null) return null;
            return dev.kindredspirit.guest.SharedPip.describe(companion, displayName, companion.anchor(m).getUUID(),
                    GuestBridge.hidden, System.currentTimeMillis()).toString();
        };
        GuestBridge.enabled = () -> cfg.lanGuests && inWorld && link.connected(); // (no brain here: no Pip to share)
        GuestBridge.name = () -> displayName;
        GuestBridge.where = () -> {
            Behavior life = companion.life;
            return inWorld ? new double[]{life.x, life.y, life.z} : null;
        };
        net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents.END_SERVER_TICK.register(GuestBridge::tick);
        net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents.SERVER_STOPPING.register(GuestBridge::stopping);
        net.fabricmc.fabric.api.message.v1.ServerMessageEvents.CHAT_MESSAGE.register((message, sender, params) ->
                GuestBridge.chat(sender.server, sender, message.signedContent()));
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
            companion.frame(companion.anchor(mc), partial, voice.level());
            renderer.render(ctx, companion, skins.texture(companion.skin), cfg, quality.level(), System.currentTimeMillis());
        });
        HudRenderCallback.EVENT.register((g, delta) -> hud(g));
        // plain chat to her (chatMode): the message goes to her instead of the game's chat
        net.fabricmc.fabric.api.client.message.v1.ClientSendMessageEvents.ALLOW_CHAT.register(message -> {
            Minecraft mc = Minecraft.getInstance();
            if (sharing || !link.connected() || !ChatRoute.forCompanion(cfg.chatMode, alone(mc),
                    displayName, message)) return true;
            talk(message.trim());
            return false;
        });
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
                                + (bond >= 0 ? " | bond: " + bond + " (" + bondLevel + ")" : "")
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
                    // who she floats beside on a LAN world: a friend, or "me"
                    .then(ClientCommandManager.literal("follow")
                            .then(ClientCommandManager.argument("who", StringArgumentType.greedyString())
                                    .suggests((c, b) -> SharedSuggestionProvider.suggest(followable(), b))
                                    .executes(c -> {
                                        JsonObject r = follow(StringArgumentType.getString(c, "who"));
                                        if (r.get("ok").getAsBoolean()) c.getSource().sendFeedback(Component.literal(r.get("now").getAsString()));
                                        else c.getSource().sendError(Component.literal(r.get("error").getAsString()));
                                        return 1;
                                    })))
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
                    // her memory, per world: what she knows, other worlds, bring memories over, forget, start over
                    .then(ClientCommandManager.literal("memory").executes(c -> admin("memory", ""))
                            .then(ClientCommandManager.literal("worlds").executes(c -> admin("worlds", "")))
                            .then(ClientCommandManager.literal("import")
                                    .executes(c -> admin("import", ""))
                                    .then(ClientCommandManager.argument("world", StringArgumentType.greedyString())
                                            .executes(c -> admin("import", StringArgumentType.getString(c, "world")))))
                            .then(ClientCommandManager.literal("forget")
                                    .then(ClientCommandManager.argument("what", StringArgumentType.greedyString())
                                            .executes(c -> admin("forget", StringArgumentType.getString(c, "what"))))))
                    // how she feels about you (five feelings, open hurts), or a fresh start for her heart here
                    .then(ClientCommandManager.literal("heart").executes(c -> admin("heart", ""))
                            .then(ClientCommandManager.literal("fresh").executes(c -> admin("heart", "fresh"))))
                    .then(ClientCommandManager.literal("reset").executes(c -> admin("reset", ""))
                            .then(ClientCommandManager.literal("confirm").executes(c -> admin("reset", "confirm"))))
                    // the gateway's special instructions ("clear" removes them)
                    .then(adminText("persona")).then(adminText("fact")).then(adminText("hint")).then(adminText("model"))
                    .then(ClientCommandManager.literal("instructions").executes(c -> admin("instructions", "")))
                    .then(ClientCommandManager.literal("pause").executes(c -> admin("pause", "")))
                    .then(ClientCommandManager.literal("resume").executes(c -> admin("resume", "")))
                    .then(ClientCommandManager.argument("message", StringArgumentType.greedyString()).executes(c -> {
                        talk(StringArgumentType.getString(c, "message"));
                        return 1;
                    })));
            dispatcher.register(ClientCommandManager.literal("ks").redirect(root));
        });
        net.fabricmc.fabric.api.event.player.AttackEntityCallback.EVENT.register((player, world, hand, entity, hit) -> {
            if (world.isClientSide && (entity instanceof net.minecraft.world.entity.animal.Animal
                    || entity instanceof net.minecraft.world.entity.npc.AbstractVillager
                    || entity instanceof net.minecraft.world.entity.monster.Enemy)) {
                attacked.put(entity.getId(), System.currentTimeMillis());
            }
            if (world.isClientSide && entity instanceof net.minecraft.world.entity.LivingEntity) {
                youDid.add(System.currentTimeMillis(), "hit",
                        words(net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).toString()));
            }
            return net.minecraft.world.InteractionResult.PASS;
        });
        net.fabricmc.fabric.api.event.player.UseBlockCallback.EVENT.register((player, world, hand, hit) -> {
            if (world.isClientSide && player.getItemInHand(hand).getItem() instanceof net.minecraft.world.item.BlockItem bi) {
                BlockPos at = world.getBlockState(hit.getBlockPos()).canBeReplaced() ? hit.getBlockPos()
                        : hit.getBlockPos().relative(hit.getDirection());
                pendingPlace = at;
                pendingBlock = bi.getBlock();
                pendingTicks = 2;
            }
            return net.minecraft.world.InteractionResult.PASS;
        });
        ClientPlayConnectionEvents.JOIN.register((handler, sender, mc) -> {
            inWorld = true;
            joinedAt = System.currentTimeMillis();
            lastInventory = null;
            if (!hearingOn) { // the sound system exists by now
                mc.getSoundManager().addListener(hearing);
                hearingOn = true;
            }
            lastHealth = -1;
            sendAbilities(); // the hello came from the title screen: now we know if it's singleplayer
            event("join");
        });
        // the world is closing: take her light away before it's saved
        net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents.SERVER_STOPPING.register(
                dev.kindredspirit.act.Glow::clearNow);
        ClientPlayConnectionEvents.DISCONNECT.register((handler, mc) -> {
            inWorld = false;
            sharing = false;
            shared.forget();
            companion.follow = null;
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
        for (GuestBridge.Heard h; (h = GuestBridge.next()) != null; ) fromGuest(h);

        if (now >= nextQualityCheck) {
            nextQualityCheck = now + 1000;
            quality.update(mc.getFps(), mc.options.graphicsMode().get() == GraphicsStatus.FAST);
        }
        if (mc.player == null || mc.level == null) return;
        if (tune.playing()) tune.tick(mc, companion.life.x, companion.life.y, companion.life.z);
        if (++configChecks % 40 == 0 && cfg.reloadIfChanged()) { // changed from the dashboard: applied now
            String skin = cfg.skin;
            if (skins.has(skin) && !skin.equals(companion.skin.id())) companion.skin = skins.get(skin);
            sendAbilities(); // power and style
            if (!java.util.Objects.equals(cfg.follow, followApplied) && !sharing) { // the dashboard's "she stays with"
                JsonObject r = follow(cfg.follow);
                if (r.get("ok").getAsBoolean()) notice(r.get("now").getAsString(), 4000);
            }
            LOG.info("settings changed outside the game: applied");
        }
        boolean share = "host".equalsIgnoreCase(cfg.sharedPip) && mc.getSingleplayerServer() == null && shared.active(now);
        if (share != sharing) {
            sharing = share;
            if (share) {
                notice("You see " + shared.name() + ", who lives in this world's host's game. Talk to her in chat: \""
                        + shared.name() + ", ...\"", 7000);
                if (link.connected()) event("leave"); // (your own brain rests: one Pip here)
            } else {
                shared.forget();
                companion.follow = null;
                if (link.connected() && inWorld) event("join");
            }
        }
        if (sharing) {
            shared.apply(companion, now);
            String sk = shared.skin();
            if (skins.has(sk) && !sk.equals(companion.skin.id())) companion.skin = skins.get(sk);
            caption = companion.subtitle;
            captionUntil = companion.subtitleUntil;
        }
        Companion.Touch touch = companion.tick(mc);
        if (touch == Companion.Touch.PETTED) event("petted");
        if (touch == Companion.Touch.HIT) event("hit");
        trackWorld(mc);
        if (companion.life.arrived) {
            companion.life.arrived = false;
            guideEntity = -1;
            event("arrived");
        }
        if (companion.life.wrongWay) {
            companion.life.wrongWay = false;
            event("wrong_way");
        }
        tickGuide(mc);
        if (mc.level.getGameTime() % 4 == 0) { // her glow follows her (a light block, singleplayer)
            Behavior life = companion.life;
            dev.kindredspirit.act.Glow.tick(mc, cfg.glow && !life.hidden() && companion.life.presence > 0.5,
                    life.x, life.y, life.z);
        }

        // push-to-talk: hold the key, speak, release
        boolean held = talkKey.isDown() && mc.screen == null;
        if (held && sharing && !link.connected()) { // no speech-to-text here: type to her instead
            mc.setScreen(new net.minecraft.client.gui.screens.ChatScreen(shared.name() + ", "));
        } else if (held && !recorder.isRecording() && companion.activity != Behavior.Activity.LISTENING) {
            if (!link.connected()) {
                notice("The Kindred brain is not running. Start it with scripts/start.sh", 5000);
            } else {
                voice.stop();
                companion.activity = Behavior.Activity.LISTENING;
                recorder.start(cfg.maxRecordSeconds, this::onRecorded);
                event("listening"); // she stops, and holds back what she'd say while you talk
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
        if (!sharing && (now >= nextSnapshot || (urgent && now - lastUrgentSnapshot > 400))) {
            if (urgent) lastUrgentSnapshot = now;
            nextSnapshot = now + quality.level().snapshotMs;
            dev.kindredspirit.life.Behavior life = companion.life;
            JsonObject snap = Snapshot.build(mc, quality.level().scanRadius,
                    life.hidden() ? null : new net.minecraft.world.phys.Vec3(life.x, life.y, life.z));
            long nowMs = System.currentTimeMillis();
            snap.add("sounds", hearing.recent(mc.player, 8000));
            var beside = companion.anchor(mc);
            if (beside != mc.player) snap.addProperty("following", beside.getGameProfile().getName());
            watchInventory(snap, nowMs);
            com.google.gson.JsonArray did = new com.google.gson.JsonArray();
            for (String d : youDid.summary(nowMs, 30000)) did.add(d);
            snap.add("youDid", did);
            breaks.removeIf(t -> nowMs - t > 60000);
            places.removeIf(t -> nowMs - t > 60000);
            snap.addProperty("brokenRecently", breaks.size());
            snap.addProperty("placedRecently", places.size());
            snap.addProperty("lastPlacedAgo", dev.kindredspirit.act.Pranks.lastPlaced == null ? 9999
                    : (nowMs - dev.kindredspirit.act.Pranks.lastPlacedAt) / 1000);
            if (urgent) snap.addProperty("urgent", true);
            link.send(snap);
        }
    }

    // ------------------------------------------------------------------ talking

    /** Typed message for the companion (/kindred TEXT or /ks TEXT). */
    private com.mojang.brigadier.builder.LiteralArgumentBuilder<net.fabricmc.fabric.api.client.command.v2.FabricClientCommandSource>
            adminText(String name) {
        return ClientCommandManager.literal(name).executes(c -> admin(name, ""))
                .then(ClientCommandManager.argument("text", StringArgumentType.greedyString())
                        .executes(c -> admin(name, StringArgumentType.getString(c, "text"))));
    }

    /** A command the brain answers in chat (memory, reset, special instructions). */
    private int admin(String command, String text) {
        if (!link.connected()) {
            notice("The Kindred brain is not running. Start it with scripts/start.sh", 5000);
            return 0;
        }
        JsonObject o = new JsonObject();
        o.addProperty("type", "admin");
        o.addProperty("command", command);
        o.addProperty("text", text);
        link.send(o);
        return 1;
    }

    /** She floats beside someone else in the world ("me": back beside you). */
    private JsonObject follow(String who) {
        Minecraft mc = Minecraft.getInstance();
        JsonObject r = new JsonObject();
        if (who == null || who.isBlank() || who.matches("(?i)me|you|player|back|myself|" + java.util.regex.Pattern.quote(
                mc.player == null ? "me" : mc.player.getGameProfile().getName()))) {
            companion.follow = null;
            remember("");
            r.addProperty("ok", true);
            r.addProperty("now", displayName + " floats beside you again.");
            return r;
        }
        java.util.List<net.minecraft.world.entity.player.Player> others = new java.util.ArrayList<>();
        if (mc.level != null) for (var o : mc.level.players()) if (o != mc.player) others.add(o);
        var them = dev.kindredspirit.act.Players.match(others, who);
        if (them == null) {
            r.addProperty("ok", false);
            r.addProperty("error", others.isEmpty() ? "Nobody else is here." : "Nobody called " + who + " here (here: "
                    + String.join(", ", others.stream().map(o -> o.getGameProfile().getName()).toList()) + ").");
            return r;
        }
        companion.follow = them.getUUID();
        remember(them.getGameProfile().getName());
        r.addProperty("ok", true);
        r.addProperty("now", displayName + " floats beside " + them.getGameProfile().getName() + " now (/kindred follow me to call her back).");
        r.addProperty("following", them.getGameProfile().getName());
        return r;
    }

    /** Whom she follows, in the settings (the dashboard shows it and can change it). */
    private void remember(String name) {
        followApplied = name;
        if (!name.equals(cfg.follow)) {
            cfg.follow = name;
            cfg.save();
        }
    }

    private String followApplied = "";

    private String[] followable() {
        Minecraft mc = Minecraft.getInstance();
        java.util.List<String> names = new java.util.ArrayList<>(java.util.List.of("me"));
        if (mc.level != null) for (var o : mc.level.players()) if (o != mc.player) names.add(o.getGameProfile().getName());
        return names.toArray(String[]::new);
    }

    /** A friend on your LAN world called her in chat (see GuestBridge): she hears who it was. */
    private void fromGuest(GuestBridge.Heard h) {
        if (!link.connected()) return;
        JsonObject o = new JsonObject();
        o.addProperty("type", "chat");
        o.addProperty("text", h.text());
        o.addProperty("from", h.who());
        o.addProperty("powers", cfg.lanGuestPowers);
        link.send(o);
        companion.activity = Behavior.Activity.THINKING;
        speakingGrace = System.currentTimeMillis() + 15000;
    }

    public void talk(String text) {
        if (!link.connected()) {
            notice("The Kindred brain is not running. Start it with scripts/start.sh", 5000);
            return;
        }
        JsonObject o = new JsonObject();
        o.addProperty("type", "chat");
        o.addProperty("text", text);
        link.send(o);
        logChat(yourLine(text));
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
        if (sharing) o.addProperty("relay", true); // (light mode: your words go to the host's Pip, in chat)
        o.addProperty("wav", Base64.getEncoder().encodeToString(wav));
        link.send(o);
        if (!recorder.lastError().isEmpty()) {
            Minecraft.getInstance().execute(() -> notice("Microphone error: " + recorder.lastError(), 6000));
        }
    }

    // ------------------------------------------------------------------ brain messages (WebSocket thread)

    /** Dev scripts only: as if the brain had sent this message. */
    public void devBrainMessage(JsonObject msg) {
        onBrainMessage(msg);
    }

    private void onBrainMessage(JsonObject msg) {
        String type = str(msg, "type");
        Minecraft mc = Minecraft.getInstance();
        if (sharing && type.matches("say|say_more|audio|tune|act|mood|bond")) return; // (one Pip here: the host's)
        switch (type) {
            case "say" -> {
                // a new line: replaces whatever it was saying
                String text = str(msg, "text");
                Mood mood = Mood.parse(str(msg, "mood"), companion.mood);
                String b64 = str(msg, "audio");
                boolean more = msg.has("more") && msg.get("more").getAsBoolean();
                currentLine = msg.has("line") ? msg.get("line").getAsInt() : currentLine + 1;
                // decoded here, off the game thread, then played on the audio thread
                // while you hold the talk key her voice stays off (the microphone would hear it): subtitle only
                boolean muted = recorder.isRecording();
                double secs = b64.isEmpty() || muted ? 0 : voice.play(Base64.getDecoder().decode(b64), volume(mc));
                if (b64.isEmpty() || muted) voice.stop();
                mc.execute(() -> {
                    long now = System.currentTimeMillis();
                    companion.mood = mood;
                    companion.say(text, secs, now);
                    dev.kindredspirit.record.FrameRecorder.line("pip", text);
                    GuestBridge.say(mc.getSingleplayerServer(), text);
                    Emote gesture = Emote.parse(str(msg, "emote"));
                    if (gesture != null && cfg.life.aiGestures) companion.life.play(gesture, companion.now());
                    boolean talking = secs > 0 || more;
                    companion.activity = talking ? Behavior.Activity.SPEAKING : Behavior.Activity.IDLE;
                    // the audio thread needs a moment to start; the next sentence may still be on its way
                    speakingGrace = now + (more ? 4000 : 600);
                    caption = text;
                    captionUntil = companion.subtitleUntil;
                    logChat(herLine(text));
                });
            }
            case "say_more" -> {
                // the next sentence of the line she's saying, as her answer streams in
                if (!msg.has("line") || msg.get("line").getAsInt() != currentLine) return;
                String more = str(msg, "text");
                mc.execute(() -> {
                    long now = System.currentTimeMillis();
                    companion.sayMore(more, now);
                    caption = companion.subtitle;
                    captionUntil = companion.subtitleUntil;
                    dev.kindredspirit.record.FrameRecorder.line("pip", more);
                    GuestBridge.say(mc.getSingleplayerServer(), more);
                    logChat(Component.literal("   " + more).withStyle(ChatFormatting.WHITE)); // (continues her line)
                });
            }
            case "audio" -> {
                // the next sentence of the current line
                if (!msg.has("line") || msg.get("line").getAsInt() != currentLine || recorder.isRecording()) return;
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
                if (msg.has("relay") && !text.isEmpty() && mc.player != null) { // to the host's Pip, through chat
                    companion.activity = Behavior.Activity.IDLE;
                    mc.player.connection.sendChat(shared.name() + ", " + text);
                    return;
                }
                if (!text.isEmpty()) {
                    logChat(yourLine(text));
                }
            });
            case "mood" -> mc.execute(() -> companion.mood = Mood.parse(str(msg, "mood"), companion.mood));
            case "act" -> mc.execute(() -> applyAct(msg));
            case "bond" -> mc.execute(() -> {
                bond = msg.get("value").getAsInt();
                bondLevel = str(msg, "level");
                if (msg.has("trust")) companion.life.trust = msg.get("trust").getAsInt(); // she flinches when it's low
                double ch = msg.has("change") ? msg.get("change").getAsDouble() : 0;
                if (ch != 0) {
                    bondChange = ch;
                    bondShownUntil = System.currentTimeMillis() + 3500;
                }
            });
            case "do" -> mc.execute(() -> runAction(msg));
            case "tune" -> mc.execute(() -> tune.start(msg)); // a hum, played as music where she floats
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
            case "admin" -> mc.execute(() -> { // the answer to a /kindred command: always shown
                if (mc.gui != null) mc.gui.getChat().addMessage(Component.literal("[" + displayName + "] ")
                        .withStyle(ChatFormatting.LIGHT_PURPLE).append(Component.literal(str(msg, "text")).withStyle(ChatFormatting.GRAY)));
            });
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

    // ------------------------------------------------------------------ what she notices

    private final java.util.List<Long> breaks = new java.util.ArrayList<>(), places = new java.util.ArrayList<>();
    // her senses: what she hears, and what she watched you do (see senses/)
    private final dev.kindredspirit.senses.Hearing hearing = new dev.kindredspirit.senses.Hearing();
    private boolean hearingOn;
    private int configChecks;
    private final dev.kindredspirit.audio.TunePlayer tune = new dev.kindredspirit.audio.TunePlayer(); // her hums
    private final dev.kindredspirit.senses.Recent youDid = new dev.kindredspirit.senses.Recent(120000, 6);
    private java.util.Map<String, Integer> lastInventory;
    private java.util.Set<String> items = null;
    private long itemsCheckedAt;
    private BlockPos pendingPlace;
    private net.minecraft.world.level.block.Block pendingBlock;
    private int pendingTicks;

    /** What you got or used since the last snapshot ("got 4 oak planks", "ate a bread"). */
    private void watchInventory(JsonObject snap, long now) {
        java.util.Map<String, Integer> inv = new java.util.HashMap<>();
        if (snap.has("inventory")) {
            for (var e : snap.getAsJsonObject("inventory").entrySet()) inv.put(e.getKey(), e.getValue().getAsInt());
        }
        if (lastInventory != null) {
            for (var e : inv.entrySet()) {
                int gained = e.getValue() - lastInventory.getOrDefault(e.getKey(), 0);
                if (gained > 0) youDid.add(now, "got", words(e.getKey()), gained);
            }
            for (var e : lastInventory.entrySet()) {
                int lost = e.getValue() - inv.getOrDefault(e.getKey(), 0);
                if (lost <= 0) continue;
                String what = words(e.getKey());
                if (youDid.did(now, "placed", what, 5000)) continue; // (already told as placed)
                net.minecraft.world.item.Item item = net.minecraft.core.registries.BuiltInRegistries.ITEM.get(
                        net.minecraft.resources.ResourceLocation.parse(e.getKey()));
                boolean food = item.components().has(net.minecraft.core.component.DataComponents.FOOD);
                youDid.add(now, food ? "ate" : "used", what, lost);
            }
        }
        lastInventory = inv;
    }

    public void blockBroken(String block) {
        breaks.add(System.currentTimeMillis());
        youDid.add(System.currentTimeMillis(), "broke", words(block));
    }

    /** "minecraft:oak_log" -> "oak log" */
    static String words(String id) {
        if (id == null) return "";
        int c = id.indexOf(':');
        return (c >= 0 && id.startsWith("minecraft:") ? id.substring(c + 1) : id).replace('_', ' ');
    }

    public void advancement(String title) {
        JsonObject o = new JsonObject();
        o.addProperty("type", "event");
        o.addProperty("event", "advancement");
        o.addProperty("detail", title);
        link.send(o);
    }

    /** Which block you're placing (confirmed a tick later) and which items are new in your pockets. */
    private int visiting = -1;
    /** The animal she's leading you to (it walks, so the trip follows it), or -1. */
    private int guideEntity = -1;

    /** While leading: follow a walking animal, and leave a faint trail of sparkles you can follow. */
    private void tickGuide(Minecraft mc) {
        Behavior life = companion.life;
        if (life.mode != Behavior.Mode.GUIDE) {
            guideEntity = -1;
            Snapshot.headingX = Snapshot.headingZ = 0; // (hazards: look where the player looks)
            return;
        }
        double[] gt = life.guideTarget(); // hazards: look along the way she leads
        Snapshot.headingX = gt[0] - mc.player.getX();
        Snapshot.headingZ = gt[2] - mc.player.getZ();
        if (guideEntity >= 0) {
            net.minecraft.world.entity.Entity e = mc.level.getEntity(guideEntity);
            if (e != null && e.isAlive()) life.retarget(e.getX(), e.getY(), e.getZ());
        }
        if (cfg.guideTrail && mc.level.getGameTime() % 4 == 0 && companion.life.presence > 0.5) {
            mc.level.addParticle(net.minecraft.core.particles.ParticleTypes.WAX_OFF,
                    life.x + (Math.random() - 0.5) * 0.4, life.y - 0.15, life.z + (Math.random() - 0.5) * 0.4,
                    0, 0, 0);
        }
    }
    private final java.util.Map<Integer, Long> attacked = new java.util.HashMap<>();

    private void trackWorld(Minecraft mc) {
        // she follows the animal she's visiting as it wanders
        if (visiting >= 0) {
            net.minecraft.world.entity.Entity e = mc.level.getEntity(visiting);
            if (e != null && companion.life.mode == Behavior.Mode.VISIT) {
                companion.life.updateVisit(e.getX(), e.getY() + e.getBbHeight() * 0.6, e.getZ());
            } else {
                visiting = -1;
            }
        }
        // creatures you attacked that died: was it a villager, or many animals?
        if (!attacked.isEmpty()) {
            long t = System.currentTimeMillis();
            attacked.entrySet().removeIf(en -> {
                net.minecraft.world.entity.Entity e = mc.level.getEntity(en.getKey());
                boolean dead = e instanceof net.minecraft.world.entity.LivingEntity le && (le.isDeadOrDying() || !le.isAlive());
                if (dead) {
                    JsonObject o = new JsonObject();
                    o.addProperty("type", "event");
                    o.addProperty("event", "killed");
                    o.addProperty("detail", net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString());
                    o.addProperty("villager", e instanceof net.minecraft.world.entity.npc.AbstractVillager);
                    o.addProperty("monster", e instanceof net.minecraft.world.entity.monster.Enemy);
                    link.send(o);
                    return true;
                }
                return e == null || t - en.getValue() > 5000;
            });
        }
        if (pendingPlace != null && --pendingTicks <= 0) {
            if (mc.level.getBlockState(pendingPlace).is(pendingBlock)) {
                dev.kindredspirit.act.Pranks.lastPlaced = pendingPlace;
                dev.kindredspirit.act.Pranks.lastPlacedAt = System.currentTimeMillis();
                places.add(System.currentTimeMillis());
                youDid.add(System.currentTimeMillis(), "placed",
                        words(net.minecraft.core.registries.BuiltInRegistries.BLOCK.getKey(pendingBlock).toString()));
            }
            pendingPlace = null;
        }
        long now = System.currentTimeMillis();
        if (now - itemsCheckedAt < 1000) return;
        itemsCheckedAt = now;
        java.util.Set<String> current = new java.util.HashSet<>();
        for (net.minecraft.world.item.ItemStack s : mc.player.getInventory().items) {
            if (!s.isEmpty()) current.add(net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(s.getItem()).toString());
        }
        if (items != null && now - joinedAt > 5000) {
            for (String id : current) {
                if (!items.contains(id)) {
                    JsonObject o = new JsonObject();
                    o.addProperty("type", "event");
                    o.addProperty("event", "new_item");
                    o.addProperty("detail", id);
                    link.send(o);
                }
            }
        }
        items = current;
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
        o.addProperty("glow", cfg.glow);
    }

    private void sendAbilities() {
        JsonObject o = new JsonObject();
        o.addProperty("type", "abilities");
        addAbilities(o);
        link.send(o);
    }

    /** For the sandbox test script: run an action as if the brain asked, and log what happened. */
    public void devAction(String action, JsonObject args) {
        JsonObject msg = new JsonObject();
        msg.addProperty("id", "dev");
        msg.addProperty("action", action);
        msg.add("args", args);
        runAction(msg);
    }

    /** The brain asks for an action; the answer goes back as {"type": "done", "id": ..., ...}. */
    private void runAction(JsonObject msg) {
        String id = str(msg, "id"), action = str(msg, "action");
        JsonObject args = msg.has("args") && msg.get("args").isJsonObject() ? msg.getAsJsonObject("args") : new JsonObject();
        java.util.function.Consumer<JsonObject> reply = res -> {
            if (id.equals("dev")) LOG.info("dev action {} -> {}", action, res);
            res.addProperty("type", "done");
            res.addProperty("id", id);
            link.send(res);
        };
        Behavior life = companion.life;
        if (action.equals("follow_player")) {
            reply.accept(follow(str(args, "name")));
            return;
        }
        if (action.equals("guide")) {
            double[] t = Actions.lastTarget;
            int follow = Actions.lastTargetEntity;
            net.minecraft.world.entity.Entity animal = args.has("entity") && Minecraft.getInstance().level != null
                    ? Minecraft.getInstance().level.getEntity(args.get("entity").getAsInt()) : null;
            if (animal != null) {
                t = new double[]{animal.getX(), animal.getY(), animal.getZ()};
                follow = animal.getId();
            } else if (args.has("x") && args.has("z")) {
                follow = -1;
                t = new double[]{args.get("x").getAsDouble() + 0.5, args.has("y") ? args.get("y").getAsDouble() : 64,
                        args.get("z").getAsDouble() + 0.5};
            }
            JsonObject res = new JsonObject();
            if (t == null) {
                res.addProperty("ok", false);
                res.addProperty("error", "Guide where? Find or locate something first, or give coordinates.");
            } else {
                life.guide(t[0], t[1], t[2], companion.now());
                guideEntity = follow;
                res.addProperty("ok", true);
                res.addProperty("guiding", true);
                double dx = t[0] - Minecraft.getInstance().player.getX(), dz = t[2] - Minecraft.getInstance().player.getZ();
                res.addProperty("distance", Math.round(Math.sqrt(dx * dx + dz * dz)));
                res.addProperty("direction", Direction8.relative(Minecraft.getInstance().player.getYRot(), dx, dz));
                res.addProperty("following", follow >= 0 ? "someone moving (you follow them as they walk)" : "a fixed place");
            }
            reply.accept(res);
            return;
        }
        if (action.equals("bonk") || action.equals("play_hit") || action.equals("mood_weather")) {
            boolean allowed = action.equals("mood_weather") ? cfg.allowMoodWeather : cfg.allowPranks;
            if (!allowed) {
                JsonObject no = new JsonObject();
                no.addProperty("ok", false);
                no.addProperty("error", "turned off in kindredspirit.json");
                reply.accept(no);
                return;
            }
            Minecraft m = Minecraft.getInstance();
            (action.equals("bonk") ? dev.kindredspirit.act.Pranks.bonk(m, life.x, life.z)
                    : action.equals("play_hit") ? dev.kindredspirit.act.Pranks.playHit(m, life.x, life.z)
                    : dev.kindredspirit.act.Pranks.weather(m, args.has("weather") ? args.get("weather").getAsString() : "clear"))
                    .thenAccept(res -> m.execute(() -> reply.accept(res)));
            if (!action.equals("mood_weather")) life.play(dev.kindredspirit.life.Emote.HOP, companion.now());
            return;
        }
        if (action.equals("prank_sound") || action.equals("steal_block") || action.equals("return_block")) {
            if (!cfg.allowPranks && !action.equals("return_block")) {
                JsonObject no = new JsonObject();
                no.addProperty("ok", false);
                no.addProperty("error", "pranks are turned off");
                reply.accept(no);
                return;
            }
            if (action.equals("prank_sound")) {
                reply.accept(dev.kindredspirit.act.Pranks.sound(Minecraft.getInstance(), args.has("sound") ? args.get("sound").getAsString() : "creeper"));
            } else {
                (action.equals("steal_block") ? dev.kindredspirit.act.Pranks.steal(Minecraft.getInstance())
                        : dev.kindredspirit.act.Pranks.giveBack(Minecraft.getInstance()))
                        .thenAccept(res -> Minecraft.getInstance().execute(() -> reply.accept(res)));
            }
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
        if (msg.has("closeness")) life.closeness = msg.get("closeness").getAsDouble();
        if (msg.has("visit") && mc.level != null) {
            net.minecraft.world.entity.Entity e = mc.level.getEntity(msg.get("visit").getAsInt());
            if (e != null) {
                visiting = e.getId();
                life.visit(e.getX(), e.getY() + e.getBbHeight() * 0.6, e.getZ(), seconds, now);
            }
        }
        switch (str(msg, "move")) {
            case "hide" -> life.hide(seconds, now);
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

    /** "Pip: ..." with her name in her mood color (a little lighter, so yellow and blue read on the chat). */
    private Component herLine(String text) {
        int col = Mood.blend(companion.mood == Mood.OFFLINE ? 0x9FD8E6 : companion.mood.rgb, 0xFFFFFF, 0.25f);
        return Component.empty() // (an empty root, so her name's bold doesn't spill onto her words)
                .append(Component.literal(displayName).withStyle(st -> st.withColor(col).withBold(true)))
                .append(Component.literal(": ").withStyle(ChatFormatting.DARK_GRAY))
                .append(Component.literal(text).withStyle(ChatFormatting.WHITE));
    }

    /** What you said to her: quieter than her lines, so the conversation reads as hers. */
    private Component yourLine(String text) {
        return Component.literal("You \u2192 " + displayName + ": ").withStyle(ChatFormatting.DARK_GRAY)
                .append(Component.literal(text).withStyle(ChatFormatting.GRAY));
    }

    private void logChat(Component c) {
        Minecraft mc = Minecraft.getInstance();
        if (cfg.chatLog && mc.gui != null) mc.gui.getChat().addMessage(c);
    }

    private int bond = -1;
    private String bondLevel = "";
    private double bondChange;
    private long bondShownUntil;

    /** A soft dark panel like vanilla's subtitles, with a thin accent on the left in her color. */
    private static void panel(GuiGraphics g, int x0, int y0, int x1, int y1, int alpha, int accent) {
        g.fill(x0, y0, x1, y1, (Math.round(alpha * 0.62f) << 24));
        if (accent != 0) g.fill(x0, y0, x0 + 2, y1, (alpha << 24) | (accent & 0xFFFFFF));
    }

    private int herColor() {
        return Mood.blend(companion.mood == Mood.OFFLINE ? 0x9FD8E6 : companion.mood.rgb, 0xFFFFFF, 0.2f);
    }

    private void hud(GuiGraphics g) {
        Minecraft mc = Minecraft.getInstance();
        if (mc.options.hideGui || mc.player == null) return;
        long now = System.currentTimeMillis();
        int w = g.guiWidth(), h = g.guiHeight();
        var font = mc.font;
        if (companion.activity == Behavior.Activity.LISTENING) { // a pulsing red dot while the microphone is open
            String s = "Listening\u2026 release " + talkKey.getTranslatedKeyMessage().getString() + " to send";
            int tw = font.width(s) + 12, x = (w - tw) / 2, y = h - 80;
            panel(g, x - 4, y - 3, x + tw + 4, y + 10, 230, 0);
            int pulse = (int) (150 + 105 * Math.sin(now / 160.0));
            g.fill(x + 1, y + 1, x + 7, y + 7, (pulse << 24) | 0xFF5C6B);
            g.drawString(font, s, x + 12, y, 0xFFFFFFFF);
        }
        if (cfg.hudCaptions && now < captionUntil && !caption.isEmpty()) { // like film subtitles: her name in her color
            String name = displayName + "  ";
            int nameW = font.width(name), max = Math.min(320, w - 40);
            var lines = font.split(Component.literal(caption), max - nameW);
            int widest = 0;
            for (var line : lines) widest = Math.max(widest, font.width(line));
            int tw = nameW + widest, x = (w - tw) / 2, y = h - 92 - lines.size() * 10;
            float fade = Math.min(1f, (captionUntil - now) / 400f);
            int a = Math.max(8, (int) (fade * 255));
            panel(g, x - 5, y - 3, x + tw + 5, y + lines.size() * 10 + 1, a, herColor());
            g.drawString(font, displayName, x, y, (a << 24) | herColor());
            for (var line : lines) {
                g.drawString(font, line, x + nameW, y, (a << 24) | 0xFFFFFF);
                y += 10;
            }
        }
        if (!sharing && !link.connected() && inWorld && now - joinedAt > 3000 && now - joinedAt < 15000) {
            notice("Kindred brain not connected yet: run scripts/start.sh, then /kindred reconnect", 2000);
        }
        int rightY = 6;
        if (cfg.showBond && bond >= 0 && now < bondShownUntil) { // the little heart meter, top right
            float fade = Math.min(1f, (bondShownUntil - now) / 600f);
            int a = Math.max(8, (int) (fade * 255)) << 24;
            int heart = bondChange >= 0 ? 0xFF6B8B : 0x9A8FB8;
            String title = "\u2764 " + displayName + " \u00b7 " + bondLevel;
            double ch = Math.abs(bondChange) < 10 ? Math.round(bondChange * 10) / 10.0 : Math.round(bondChange);
            String d = (bondChange > 0 ? "+" : bondChange < 0 ? "\u2212" : "") + (ch == Math.rint(ch) ? String.valueOf((long) Math.abs(ch)) : String.valueOf(Math.abs(ch)));
            int bw = Math.max(98, font.width(title) + font.width(d) + 10);
            int x = w - bw - 8, y = rightY + 3;
            panel(g, x - 5, y - 4, x + bw + 5, y + 21, (int) (fade * 255), heart);
            g.drawString(font, title, x, y, a | 0xFFFFFF);
            g.drawString(font, d, x + bw - font.width(d), y, a | heart);
            g.fill(x, y + 12, x + bw, y + 15, a | 0x3A3550);
            g.fill(x, y + 12, x + Math.max(1, (int) (bw * Math.min(100, bond) / 100.0)), y + 15, a | heart);
            for (int t : new int[]{15, 35, 65, 85}) g.fill(x + bw * t / 100, y + 12, x + bw * t / 100 + 1, y + 15, a | 0x15121D); // the levels
        }
        if (now < noticeUntil && !notice.isEmpty()) { // something worth knowing, top left, fading out
            var lines = font.split(Component.literal(notice), Math.max(120, Math.min(300, w - 140)));
            int widest = 0;
            for (var line : lines) widest = Math.max(widest, font.width(line));
            float fade = Math.min(1f, (noticeUntil - now) / 500f);
            int a = Math.max(8, (int) (fade * 255));
            int y = 6;
            panel(g, 4, y - 3, 4 + widest + 10, y + lines.size() * 10 + 1, a, 0xFFD27A);
            for (var line : lines) {
                g.drawString(font, line, 10, y, (a << 24) | 0xFFE9B8);
                y += 10;
            }
        }
        Behavior life = companion.life;
        if (cfg.guideArrow && life.mode == Behavior.Mode.GUIDE) { // which way, and how far, at a glance
            double[] t = life.guideTarget();
            double dx = t[0] - mc.player.getX(), dz = t[2] - mc.player.getZ();
            String arrow = Direction8.arrow(mc.player.getYRot(), dx, dz);
            String rest = "  " + displayName + " leads you \u00b7 " + Math.round(Math.hypot(dx, dz)) + " blocks";
            double rise = t[1] - mc.player.getY();
            if (rise > 3) rest += " \u2191" + Math.round(rise);
            if (rise < -3) rest += " \u2193" + Math.round(-rise);
            int aw = font.width(arrow), tw = aw + font.width(rest), x = (w - tw) / 2;
            panel(g, x - 5, 4, x + tw + 5, 18, 230, herColor());
            g.drawString(font, arrow, x, 7, 0xFF000000 | herColor());
            g.drawString(font, rest, x + aw, 7, 0xFFFFE9A8);
        }
    }

    private static String str(JsonObject o, String key) {
        return o.has(key) && !o.get(key).isJsonNull() ? o.get(key).getAsString() : "";
    }
}
