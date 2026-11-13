package dev.kindredspirit;

import dev.kindredspirit.util.Mc;
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
import net.fabricmc.fabric.api.client.command.v2.ClientCommands;
import net.fabricmc.fabric.api.client.command.v2.ClientCommandRegistrationCallback;
import net.fabricmc.fabric.api.client.command.v2.FabricClientCommandSource;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
//? if >=26.1 {
import net.fabricmc.fabric.api.client.keymapping.v1.KeyMappingHelper;
import net.fabricmc.fabric.api.client.rendering.v1.hud.HudElementRegistry;
import net.fabricmc.fabric.api.client.rendering.v1.level.LevelRenderEvents;
//?} else {
/*import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;
import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.fabricmc.fabric.api.client.rendering.v1.WorldRenderEvents;
*///?}
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayConnectionEvents;
import net.fabricmc.fabric.api.resource.ResourceManagerHelper;
import net.fabricmc.fabric.api.resource.SimpleSynchronousResourceReloadListener;
import net.minecraft.commands.SharedSuggestionProvider;
import net.minecraft.resources.Identifier;
import net.minecraft.server.packs.PackType;
import net.minecraft.server.packs.resources.ResourceManager;
import net.minecraft.world.phys.Vec3;
import net.minecraft.core.BlockPos;
import net.minecraft.ChatFormatting;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.network.chat.Component;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.entity.monster.Creeper;
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
    private KeyMapping dashboardKey;
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
    /** Visiting: your Pip (your brain) in a friend's LAN world whose game has Kindred. */
    private volatile boolean visitingWorld;
    /**
     * This computer has her brain (it was set up here, or it connected): only then is there a Pip of its own
     * to show, grey while the brain is off. A friend with only the mod sees Pip when someone's Pip is there.
     */
    private volatile boolean brainHere = java.nio.file.Files.exists(
            Path.of(System.getProperty("user.home"), ".kindred-spirit", "brain.toml"));
    private int visitTicks;
    /** #92: the "Pip needs her brain" hint, once per game, a few seconds into the player's own world. */
    private boolean hintShown;
    private int ticksInWorld;
    private final java.util.Map<String, java.util.concurrent.CompletableFuture<JsonObject>> visitPending =
            new java.util.concurrent.ConcurrentHashMap<>();

    private void sendVisit(JsonObject o) {
        if (Minecraft.getInstance().getConnection() == null) return;
        net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking.send(
                new dev.kindredspirit.guest.VisitPayload(o.toString()));
    }

    private void sayVisiting(String text) {
        if (!visitingWorld || text == null || text.isBlank()) return;
        JsonObject o = new JsonObject();
        o.addProperty("kind", "say");
        o.addProperty("text", text);
        sendVisit(o);
    }

    /** One of her powers, done by the friend's game that hosts this world. */
    private java.util.concurrent.CompletableFuture<JsonObject> visitAct(String action, JsonObject req) {
        String id = java.util.UUID.randomUUID().toString();
        var f = new java.util.concurrent.CompletableFuture<JsonObject>();
        visitPending.put(id, f);
        req.addProperty("kind", "act");
        req.addProperty("id", id);
        req.addProperty("action", action);
        Minecraft.getInstance().execute(() -> sendVisit(req));
        return f.completeOnTimeout(Actions.error("This world's game didn't answer."), 10, java.util.concurrent.TimeUnit.SECONDS)
                .whenComplete((r, e) -> visitPending.remove(id));
    }

    private void standInHere(String json) {
        try {
            GuestBridge.hidden = java.util.UUID.fromString(
                    com.google.gson.JsonParser.parseString(json).getAsJsonObject().get("standIn").getAsString());
        } catch (RuntimeException ignored) {
        }
    }

    /** Your visiting Pip was hit or petted by someone in the friend's world: her brain hears who. */
    private void touchedThere(String json) {
        try {
            JsonObject r = com.google.gson.JsonParser.parseString(json).getAsJsonObject();
            eventBy(str(r, "what"), str(r, "by"));
        } catch (RuntimeException ignored) {
        }
    }

    private void eventBy(String name, String by) {
        if (!name.equals("hit") && !name.equals("petted")) return;
        LOG.info("{} {} Pip", by, name.equals("hit") ? "hit" : "petted");
        JsonObject o = new JsonObject();
        o.addProperty("type", "event");
        o.addProperty("event", name);
        o.addProperty("by", by);
        link.send(o);
    }

    private void visitDone(String json) {
        try {
            JsonObject r = com.google.gson.JsonParser.parseString(json).getAsJsonObject();
            var f = visitPending.remove(str(r, "id"));
            r.remove("type");
            r.remove("id");
            if (f != null) f.complete(r);
        } catch (RuntimeException ignored) {
        }
    }
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

    public KeyMapping dashboardKey() { return dashboardKey; }

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
            public Identifier getFabricId() {
                return Identifier.fromNamespaceAndPath("kindredspirit", "skins");
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

        //? if >=26.1 {
        KeyMapping.Category keys = KeyMapping.Category.register(Identifier.fromNamespaceAndPath("kindredspirit", "main"));
        talkKey = KeyMappingHelper.registerKeyMapping(new KeyMapping("key.kindredspirit.talk", InputConstants.KEY_V, keys));
        dashboardKey = KeyMappingHelper.registerKeyMapping(new KeyMapping("key.kindredspirit.dashboard", InputConstants.KEY_K, keys));
        //?} else {
        /*talkKey = KeyBindingHelper.registerKeyBinding(new KeyMapping(
                "key.kindredspirit.talk", InputConstants.Type.KEYSYM, InputConstants.KEY_V, "category.kindredspirit"));
        dashboardKey = KeyBindingHelper.registerKeyBinding(new KeyMapping(
                "key.kindredspirit.dashboard", InputConstants.Type.KEYSYM, InputConstants.KEY_K, "category.kindredspirit"));
        *///?}

        ClientTickEvents.END_CLIENT_TICK.register(this::tick);
        // her stand-in (friends without the mod): a hit or a pat on it is a touch on her; it never takes items
        net.fabricmc.fabric.api.event.player.AttackEntityCallback.EVENT.register((player, world, hand, entity, hit) -> {
            if (Mc.clientSide(world) && entity.getUUID().equals(GuestBridge.hidden)) {
                return net.minecraft.world.InteractionResult.FAIL; // (you see her, not the stand-in: your game reports the hit)
            }
            if (!Mc.clientSide(world) && GuestBridge.standIn(entity) && player instanceof net.minecraft.server.level.ServerPlayer sp) {
                GuestBridge.touch(Mc.server(sp), sp, "hit");
                return net.minecraft.world.InteractionResult.FAIL;
            }
            return net.minecraft.world.InteractionResult.PASS;
        });
        net.fabricmc.fabric.api.event.player.UseEntityCallback.EVENT.register((player, world, hand, entity, hit) -> {
            if (GuestBridge.standIn(entity)) {
                if (!Mc.clientSide(world) && hand == net.minecraft.world.InteractionHand.MAIN_HAND
                        && player instanceof net.minecraft.server.level.ServerPlayer sp) GuestBridge.touch(Mc.server(sp), sp, "petted");
                return net.minecraft.world.InteractionResult.SUCCESS;
            }
            return net.minecraft.world.InteractionResult.PASS;
        });
        // what each player does, as your world's game sees it (so what she says about a friend is real)
        net.fabricmc.fabric.api.event.player.PlayerBlockBreakEvents.AFTER.register((world, player, pos, state, be) ->
                Actions.playerDid(player, "broke " + state.getBlock().getName().getString().toLowerCase(java.util.Locale.ROOT)));
        net.fabricmc.fabric.api.event.player.UseBlockCallback.EVENT.register((player, world, hand, hit) -> {
            var item = player.getItemInHand(hand);
            if (!Mc.clientSide(world) && item.getItem() instanceof net.minecraft.world.item.BlockItem) {
                Actions.playerDid(player, "placed " + item.getHoverName().getString().toLowerCase(java.util.Locale.ROOT));
            }
            return net.minecraft.world.InteractionResult.PASS;
        });
        net.fabricmc.fabric.api.entity.event.v1.ServerLivingEntityEvents.AFTER_DEATH.register((entity, source) -> {
            if (source.getEntity() instanceof net.minecraft.server.level.ServerPlayer killer && entity != killer) {
                Actions.playerDid(killer, "killed " + entity.getType().getDescription().getString().toLowerCase(java.util.Locale.ROOT));
            }
        });
        // a friend hitting you, seen by your world's game: protect then pushes them away (playfully)
        net.fabricmc.fabric.api.entity.event.v1.ServerLivingEntityEvents.ALLOW_DAMAGE.register((entity, source, amount) -> {
            if (entity instanceof net.minecraft.server.level.ServerPlayer victim
                    && source.getEntity() instanceof net.minecraft.server.level.ServerPlayer attacker) {
                Actions.playerHurt(victim, attacker);
            }
            if (source.getEntity() instanceof net.minecraft.server.level.ServerPlayer attacker && entity != attacker
                    && !(entity instanceof net.minecraft.server.level.ServerPlayer)) {
                Actions.playerDid(attacker, "hit " + entity.getType().getDescription().getString().toLowerCase(java.util.Locale.ROOT));
            }
            if (entity instanceof net.minecraft.server.level.ServerPlayer victim && amount >= 2) {
                Actions.playerDid(victim, "got hurt");
            }
            return true;
        });
        // her building works block by block on the (integrated) server
        net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents.END_SERVER_TICK.register(
                dev.kindredspirit.act.Builder::tick);
        // jobs (mine, chop, collect, craft, your things back) through her hands, and building from a blueprint
        dev.kindredspirit.job.Jobs.register();
        // the catalogue of her blueprint folders (descriptions, sizes, pictures), for find_blueprint and the dashboard
        dev.kindredspirit.act.BlueprintCatalogue.start();
        net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents.END_SERVER_TICK.register(
                dev.kindredspirit.act.BlueprintBuild::tick);
        // friends on your LAN world without the mod: they see a stand-in for her and can talk to her;
        // friends with the mod see her as you do (light mode: SharedPip), with no AI of their own
        net.fabricmc.fabric.api.networking.v1.PayloadTypeRegistry.clientboundPlay().register(
                dev.kindredspirit.guest.PipPayload.TYPE, dev.kindredspirit.guest.PipPayload.CODEC);
        net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking.registerGlobalReceiver(
                dev.kindredspirit.guest.PipPayload.TYPE, (payload, context) -> {
                    String json = payload.json();
                    context.client().execute(() -> {
                        if (json.contains("\"id\":\"touch\"")) touchedThere(json); // (someone touched your visiting Pip)
                        else if (json.contains("\"type\":\"done\"")) visitDone(json); // (an action your visiting Pip asked for)
                        else if (json.contains("\"type\":\"standin\"")) standInHere(json); // (her stand-in there: not drawn)
                        else shared.receive(json);
                    });
                });
        // a visiting Pip: you joined a friend's LAN world whose game has Kindred, your brain is here
        net.fabricmc.fabric.api.networking.v1.PayloadTypeRegistry.serverboundPlay().register(
                dev.kindredspirit.guest.VisitPayload.TYPE, dev.kindredspirit.guest.VisitPayload.CODEC);
        net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking.registerGlobalReceiver(
                dev.kindredspirit.guest.VisitPayload.TYPE, (payload, context) -> {
                    String json = payload.json();
                    context.server().execute(() -> GuestBridge.visit(context.server(), context.player(), json));
                });
        GuestBridge.acceptVisitors = () -> cfg.lanVisitors;
        net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents.CHAT.register((message, signed, sender, params, time) -> {
            // their chat to her reaches your game: when you host, your world's server already passes it on
            if (!visitingWorld || sender == null || signed == null) return;
            Minecraft m = Minecraft.getInstance();
            //? if >=26.1 {
            java.util.UUID senderId = sender.id();
            String senderName = sender.name();
            //?} else {
            /*java.util.UUID senderId = sender.getId();
            String senderName = sender.getName();
            *///?}
            if (m.player == null || senderId.equals(m.player.getUUID())) return;
            String text = signed.signedContent();
            if (ChatRoute.forCompanion("name", false, displayName, text)) {
                m.execute(() -> fromGuest(new GuestBridge.Heard(senderName, text)));
            }
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
                GuestBridge.chat(Mc.server(sender), sender, message.signedContent()));
        //? if >=26.1 {
        LevelRenderEvents.START_MAIN.register(ctx -> {
            if (devScript != null) devScript.frame(Minecraft.getInstance());
        });
        LevelRenderEvents.COLLECT_SUBMITS.register(ctx -> {
            Minecraft mc = Minecraft.getInstance();
            if (mc.player == null || mc.player.isSpectator()) return;
            if (!sharing && !brainHere) return; // (a friend's game with only the mod: no Pip of its own to show)
            var cam = mc.gameRenderer.mainCamera();
            Vec3 camPos = cam.position();
        //?} else {
        /*WorldRenderEvents.START.register(ctx -> {
            if (devScript != null) devScript.frame(Minecraft.getInstance());
        });
        WorldRenderEvents.AFTER_ENTITIES.register(ctx -> {
            Minecraft mc = Minecraft.getInstance();
            if (mc.player == null || mc.player.isSpectator()) return;
            if (!sharing && !brainHere) return; // (a friend's game with only the mod: no Pip of its own to show)
            var cam = ctx.camera();
            Vec3 camPos = cam.getPosition();
        *///?}
            float partial = Mc.partialTick(mc);
            if (companion.activity == Behavior.Activity.SPEAKING && !voice.isPlaying()
                    && System.currentTimeMillis() > speakingGrace) {
                companion.activity = Behavior.Activity.IDLE;
            }
            companion.frame(companion.anchor(mc), partial,
                    voice.isPlaying() ? voice.level() : companion.silentMouth(System.currentTimeMillis()));
            //? if >=26.1 {
            renderer.render(ctx.poseStack(), ctx.submitNodeCollector(), camPos, cam.rotation(), companion,
                    skins.texture(companion.skin), cfg, quality.level(), System.currentTimeMillis());
            //?} else {
            /*renderer.render(ctx.matrixStack(), ctx.consumers(), camPos, cam.rotation(), companion,
                    skins.texture(companion.skin), cfg, quality.level(), System.currentTimeMillis());
            *///?}
        });
        //? if >=26.1 {
        HudElementRegistry.addLast(Identifier.fromNamespaceAndPath("kindredspirit", "hud"), (g, delta) -> hud(g));
        //?} else {
        /*HudRenderCallback.EVENT.register((g, delta) -> hud(g));
        *///?}
        // plain chat to her (chatMode): the message goes to her instead of the game's chat
        net.fabricmc.fabric.api.client.message.v1.ClientSendMessageEvents.ALLOW_CHAT.register(message -> {
            Minecraft mc = Minecraft.getInstance();
            if (sharing || !link.connected() || !ChatRoute.forCompanion(cfg.chatMode, alone(mc),
                    displayName, message)) return true;
            talk(message.trim());
            return false;
        });
        ClientCommandRegistrationCallback.EVENT.register((dispatcher, registry) -> {
            LiteralCommandNode<FabricClientCommandSource> root = dispatcher.register(ClientCommands.literal("kindred")
                    .then(ClientCommands.literal("hint") // #92: the "Pip needs her brain" message
                            .then(ClientCommands.literal("off").executes(c -> {
                                cfg.noBrainHint = false;
                                cfg.save();
                                c.getSource().sendFeedback(Component.literal("It won't be shown again (/kindred hint on to bring it back)."));
                                return 1;
                            }))
                            .then(ClientCommands.literal("on").executes(c -> {
                                cfg.noBrainHint = true;
                                hintShown = false;
                                ticksInWorld = 0;
                                cfg.save();
                                c.getSource().sendFeedback(Component.literal("The \"Pip needs her brain\" message is back on."));
                                return 1;
                            })))
                    .then(ClientCommands.literal("reconnect").executes(c -> {
                        link.reconnectNow();
                        c.getSource().sendFeedback(Component.literal("Reconnecting to the Kindred brain..."));
                        return 1;
                    }))
                    .then(ClientCommands.literal("status").executes(c -> {
                        c.getSource().sendFeedback(Component.literal("Brain: " + (link.connected() ? "connected" : "not connected")
                                + " | skin: " + companion.skin.id() + " | mode: " + companion.life.mode.name().toLowerCase()
                                + (bond >= 0 ? " | bond: " + bond + " (" + bondLevel + ")" : "")
                                + " | quality: " + quality.level().name().toLowerCase() + (quality.isAuto() ? " (auto)" : "")
                                + " | mood: " + companion.mood.name().toLowerCase()));
                        return 1;
                    }))
                    .then(ClientCommands.literal("skin")
                            .executes(c -> {
                                c.getSource().sendFeedback(Component.literal("Skin: " + companion.skin.name()
                                        + " (" + companion.skin.id() + "). Others: " + String.join(", ", skins.ids())));
                                return 1;
                            })
                            .then(ClientCommands.argument("id", StringArgumentType.word())
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
                    .then(ClientCommands.literal("skins")
                            .executes(c -> {
                                c.getSource().sendFeedback(Component.literal("Skins: " + String.join(", ", skins.ids())
                                        + ". Add your own in " + SkinRegistry.userDir()));
                                return 1;
                            })
                            .then(ClientCommands.literal("reload").executes(c -> {
                                Minecraft.getInstance().execute(() -> {
                                    skins.reload(Minecraft.getInstance().getResourceManager());
                                    companion.skin = skins.get(cfg.skin);
                                });
                                c.getSource().sendFeedback(Component.literal("Skins reloaded"));
                                return 1;
                            })))
                    .then(ClientCommands.literal("life")
                            .executes(c -> {
                                c.getSource().sendFeedback(Component.literal("Liveliness: " + LifeSwitches.describe(cfg.life)
                                        + ". Change one with /kindred life <name> <value>, or /kindred life reset."));
                                return 1;
                            })
                            .then(ClientCommands.literal("reset").executes(c -> {
                                LifeSwitches.reset(cfg.life);
                                cfg.save();
                                c.getSource().sendFeedback(Component.literal("Liveliness back to the defaults"));
                                return 1;
                            }))
                            .then(ClientCommands.argument("name", StringArgumentType.word())
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
                                    .then(ClientCommands.argument("value", StringArgumentType.word())
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
                    .then(ClientCommands.literal("follow")
                            .then(ClientCommands.argument("who", StringArgumentType.greedyString())
                                    .suggests((c, b) -> SharedSuggestionProvider.suggest(followable(), b))
                                    .executes(c -> {
                                        JsonObject r = follow(StringArgumentType.getString(c, "who"));
                                        if (r.get("ok").getAsBoolean()) c.getSource().sendFeedback(Component.literal(r.get("now").getAsString()));
                                        else c.getSource().sendError(Component.literal(r.get("error").getAsString()));
                                        return 1;
                                    })))
                    .then(ClientCommands.literal("power")
                            .executes(c -> {
                                c.getSource().sendFeedback(Component.literal("Power: " + cfg.power + ", style: " + cfg.style
                                        + ". It may: " + String.join(", ", Abilities.allowedIds(Abilities.power(cfg.power), Abilities.style(cfg.style)))));
                                return 1;
                            })
                            .then(ClientCommands.argument("level", StringArgumentType.word())
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
                    .then(ClientCommands.literal("style")
                            .then(ClientCommands.argument("style", StringArgumentType.word())
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
                    .then(ClientCommands.literal("emote")
                            .then(ClientCommands.argument("name", StringArgumentType.word())
                                    .suggests((c, b) -> SharedSuggestionProvider.suggest(
                                            java.util.Arrays.stream(Emote.values()).map(e -> e.name().toLowerCase()), b))
                                    .executes(c -> act("emote", StringArgumentType.getString(c, "name")))))
                    .then(ClientCommands.literal("mode")
                            .then(ClientCommands.argument("mode", StringArgumentType.word())
                                    .suggests((c, b) -> SharedSuggestionProvider.suggest(new String[]{"follow", "stay", "come"}, b))
                                    .executes(c -> act("move", StringArgumentType.getString(c, "mode")))))
                    .then(ClientCommands.literal("side")
                            .then(ClientCommands.argument("side", StringArgumentType.word())
                                    .suggests((c, b) -> SharedSuggestionProvider.suggest(new String[]{"right", "left", "above", "auto"}, b))
                                    .executes(c -> act("side", StringArgumentType.getString(c, "side")))))
                    .then(ClientCommands.literal("look")
                            .then(ClientCommands.argument("at", StringArgumentType.word())
                                    .suggests((c, b) -> SharedSuggestionProvider.suggest(new String[]{"me", "there", "ahead", "up", "down", "around"}, b))
                                    .executes(c -> act("look", StringArgumentType.getString(c, "at")))))
                    // her memory, per world: what she knows, other worlds, bring memories over, forget, start over
                    .then(ClientCommands.literal("memory").executes(c -> admin("memory", ""))
                            .then(ClientCommands.literal("worlds").executes(c -> admin("worlds", "")))
                            .then(ClientCommands.literal("import")
                                    .executes(c -> admin("import", ""))
                                    .then(ClientCommands.argument("world", StringArgumentType.greedyString())
                                            .executes(c -> admin("import", StringArgumentType.getString(c, "world")))))
                            .then(ClientCommands.literal("forget")
                                    .then(ClientCommands.argument("what", StringArgumentType.greedyString())
                                            .executes(c -> admin("forget", StringArgumentType.getString(c, "what"))))))
                    // how she feels about you (five feelings, open hurts), or a fresh start for her heart here
                    .then(ClientCommands.literal("heart").executes(c -> admin("heart", ""))
                            .then(ClientCommands.literal("fresh").executes(c -> admin("heart", "fresh"))))
                    .then(ClientCommands.literal("reset").executes(c -> admin("reset", ""))
                            .then(ClientCommands.literal("confirm").executes(c -> admin("reset", "confirm"))))
                    // the gateway's special instructions ("clear" removes them)
                    .then(adminText("persona")).then(adminText("fact")).then(adminText("hint")).then(adminText("model"))
                    .then(ClientCommands.literal("instructions").executes(c -> admin("instructions", "")))
                    .then(ClientCommands.literal("pause").executes(c -> admin("pause", "")))
                    .then(ClientCommands.literal("resume").executes(c -> admin("resume", "")))
                    .then(ClientCommands.argument("message", StringArgumentType.greedyString()).executes(c -> {
                        talk(StringArgumentType.getString(c, "message"));
                        return 1;
                    })));
            dispatcher.register(ClientCommands.literal("ks").redirect(root));
        });
        net.fabricmc.fabric.api.event.player.AttackEntityCallback.EVENT.register((player, world, hand, entity, hit) -> {
            if (Mc.clientSide(world) && (entity instanceof net.minecraft.world.entity.animal.Animal
                    || entity instanceof net.minecraft.world.entity.npc.villager.AbstractVillager
                    || entity instanceof net.minecraft.world.entity.monster.Enemy)) {
                attacked.put(entity.getId(), System.currentTimeMillis());
            }
            if (Mc.clientSide(world) && entity instanceof net.minecraft.world.entity.LivingEntity) {
                youDid.add(System.currentTimeMillis(), "hit",
                        words(net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).toString()));
            }
            return net.minecraft.world.InteractionResult.PASS;
        });
        net.fabricmc.fabric.api.event.player.UseBlockCallback.EVENT.register((player, world, hand, hit) -> {
            if (Mc.clientSide(world) && player.getItemInHand(hand).getItem() instanceof net.minecraft.world.item.BlockItem bi) {
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
            ticksInWorld = 0;
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
            visitingWorld = false;
            Actions.remote = null;
            visitPending.clear();
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
    private boolean wasLinked;    // her brain was connected last frame (it stopping mid-game gets a sign, #28)
    private long offlineSince, offlineNoticed; // (offlineNoticed: when it was first said)
    private long nextTaskCheck;   // her task on the HUD, looked up 4 times a second (not every frame)
    private String taskLine;
    private int taskDone, taskTotal;
    private long talkPressedAt;   // when the talk key went down
    private boolean talkCutHer;   // and whether she was speaking then (a quick tap hushes her)

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
        for (GuestBridge.Heard t; (t = GuestBridge.nextTouch()) != null; ) eventBy(t.text(), t.who()); // friends' touches

        if (now >= nextQualityCheck) {
            nextQualityCheck = now + 1000;
            //? if >=26.1 {
            quality.update(mc.getFps(), mc.options.graphicsPreset().get() == net.minecraft.client.GraphicsPreset.FAST);
            //?} else {
            /*quality.update(mc.getFps(), mc.options.graphicsMode().get() == net.minecraft.client.GraphicsStatus.FAST);
            *///?}
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
        // (hosting with no brain of your own: a friend's visiting Pip, relayed by your own world, is the one you see)
        boolean share = "host".equalsIgnoreCase(cfg.sharedPip) && shared.active(now)
                && (mc.getSingleplayerServer() == null || !link.connected());
        if (share != sharing) {
            sharing = share;
            LOG.info(share ? "Showing {}, who lives in another player's game" : "No longer showing {}", shared.name());
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
        boolean visit = !sharing && link.connected() && inWorld && mc.getSingleplayerServer() == null
                && mc.getConnection() != null
                && net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking.canSend(dev.kindredspirit.guest.VisitPayload.TYPE);
        if (visit != visitingWorld) {
            visitingWorld = visit;
            LOG.info(visit ? "{} visits this world (its game has Kindred)" : "{} no longer visiting", displayName);
            Actions.remote = visit ? this::visitAct : null;
            dev.kindredspirit.act.Glow.remote = visit ? (at, level) -> { // her glow, placed by the friend's game
                JsonObject g = new JsonObject();
                g.addProperty("kind", "glow");
                if (at != null) {
                    g.addProperty("x", at.getX());
                    g.addProperty("y", at.getY());
                    g.addProperty("z", at.getZ());
                    g.addProperty("level", level);
                }
                sendVisit(g);
            } : null;
            if (visit) notice(displayName + " comes along into this world: everyone here can see her and talk to her.", 6000);
            sendAbilities(); // (her powers work here now, through this world's game)
        }
        if (visitingWorld && ++visitTicks % 2 == 0) {
            JsonObject o = new JsonObject();
            o.addProperty("kind", "state");
            o.add("state", dev.kindredspirit.guest.SharedPip.describe(companion, displayName, companion.anchor(mc).getUUID(),
                    null, now));
            sendVisit(o);
        }
        if (sharing) {
            shared.apply(companion, now);
            String sk = shared.skin();
            if (skins.has(sk) && !sk.equals(companion.skin.id())) companion.skin = skins.get(sk);
            caption = companion.subtitle;
            captionUntil = companion.subtitleUntil;
        }
        Companion.Touch touch = companion.tick(mc);
        if (touch != null && touch != Companion.Touch.NONE) {
            String what = touch == Companion.Touch.HIT ? "hit" : touch == Companion.Touch.PETTED ? "petted" : "";
            if (sharing && !what.isEmpty() && mc.getConnection() != null
                    && net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking.canSend(dev.kindredspirit.guest.VisitPayload.TYPE)) {
                JsonObject t = new JsonObject(); // the Pip you see lives in another game: tell the world's game who touched her
                t.addProperty("kind", "touch");
                t.addProperty("what", what);
                sendVisit(t);
            } else if (!what.isEmpty()) {
                event(what);
            }
        }
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
        if (companion.life.leadGivenUp) { // (#24) you kept going elsewhere: she stopped leading
            companion.life.leadGivenUp = false;
            guideEntity = -1;
            event("lead_given_up");
        }
        tickGuide(mc);
        if (mc.level.getGameTime() % 4 == 0) { // her glow follows her (a light block, singleplayer)
            Behavior life = companion.life;
            dev.kindredspirit.act.Glow.tick(mc, cfg.glow && !life.hidden() && companion.life.presence > 0.5,
                    life.x, life.y, life.z);
        }

        while (dashboardKey.consumeClick()) openDashboard();
        if (!hintShown && inWorld && dev.kindredspirit.util.NoBrainHint.due(brainHere, cfg.noBrainHint,
                mc.getSingleplayerServer() != null, hintShown, ++ticksInWorld)) {
            hintShown = true;
            Mc.chat(mc, noBrainHint());
        }

        // push-to-talk: hold the key, speak, release
        boolean held = talkKey.isDown() && Mc.screen(mc) == null;
        if (held && sharing && !link.connected()) { // no speech-to-text here: type to her instead
            //? if >=26.1 {
            Mc.setScreen(mc, new net.minecraft.client.gui.screens.ChatScreen(shared.name() + ", ", false));
            //?} else {
            /*Mc.setScreen(mc, new net.minecraft.client.gui.screens.ChatScreen(shared.name() + ", "));
            *///?}
        } else if (held && !recorder.isRecording() && companion.activity != Behavior.Activity.LISTENING) {
            if (!link.connected()) {
                if (brainHere) notice("The Kindred brain is not running. Start it with scripts/start.sh", 5000);
            } else {
                talkPressedAt = now;
                talkCutHer = companion.activity == Behavior.Activity.SPEAKING || voice.isPlaying();
                voice.stop();
                companion.activity = Behavior.Activity.LISTENING;
                recorder.start(cfg.maxRecordSeconds, this::onRecorded);
                event("listening"); // she stops, and holds back what she'd say while you talk
            }
        } else if (!held && companion.activity == Behavior.Activity.LISTENING) {
            recorder.stop();
            if (talkCutHer && now - talkPressedAt < 400) { // a quick tap while she spoke: hush, nothing to hear
                hush();
                event("hush");
            } else {
                companion.activity = Behavior.Activity.THINKING;
                speakingGrace = now + 15000; // give up "thinking" if nothing comes back
            }
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
            if (beside != mc.player) {
                snap.addProperty("following", beside.getGameProfile().name());
                // the one she's with: how far from you, their health, and danger around THEM (her attention is there)
                JsonObject with = new JsonObject();
                with.addProperty("name", beside.getGameProfile().name());
                with.addProperty("distance", Math.round(beside.distanceTo(mc.player)));
                with.addProperty("health", beside.getHealth());
                with.addProperty("maxHealth", beside.getMaxHealth());
                com.google.gson.JsonArray danger = new com.google.gson.JsonArray();
                for (net.minecraft.world.entity.Mob m : mc.level.getEntitiesOfClass(net.minecraft.world.entity.Mob.class,
                        beside.getBoundingBox().inflate(10), m -> m instanceof net.minecraft.world.entity.monster.Enemy && m.isAlive())) {
                    JsonObject mo = new JsonObject();
                    mo.addProperty("type", net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getKey(m.getType()).toString());
                    mo.addProperty("distance", Math.round(m.distanceTo(beside) * 10) / 10.0);
                    danger.add(mo);
                }
                with.add("hostiles", danger);
                snap.add("with", with);
            }
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
        return ClientCommands.literal(name).executes(c -> admin(name, ""))
                .then(ClientCommands.argument("text", StringArgumentType.greedyString())
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
                mc.player == null ? "me" : mc.player.getGameProfile().name()))) {
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
                    + String.join(", ", others.stream().map(o -> o.getGameProfile().name()).toList()) + ").");
            return r;
        }
        companion.follow = them.getUUID();
        remember(them.getGameProfile().name());
        r.addProperty("ok", true);
        r.addProperty("now", displayName + " floats beside " + them.getGameProfile().name() + " now (/kindred follow me to call her back).");
        r.addProperty("following", them.getGameProfile().name());
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
        if (mc.level != null) for (var o : mc.level.players()) if (o != mc.player) names.add(o.getGameProfile().name());
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
        o.addProperty("releasedAt", System.currentTimeMillis()); // (the brain logs how long the trip took)
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
                    sayVisiting(text);
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
            case "hush" -> mc.execute(this::hush); // "shh", "stop talking": cut off at once, the rest dropped
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
                    sayVisiting(more);
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
            case "chat_line" -> mc.execute(() -> { // her answer to a friend, in chat only (it never waits for her voice)
                String text = str(msg, "text"), to = str(msg, "to");
                logChat(herLine(to.isEmpty() ? text : "(to " + to + ") " + text));
                GuestBridge.say(mc.getSingleplayerServer(), text);
                sayVisiting(text);
                LOG.info("Pip, in chat to {}: {}", to, text);
            });
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
                Mc.chat(mc, Component.literal("[" + displayName + "] ")
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
        brainHere = true;
        LOG.info("Connected to the Kindred brain");
        JsonObject hello = new JsonObject();
        hello.addProperty("type", "hello");
        hello.addProperty("mod", dev.kindredspirit.util.ModVersion.get()); // (#114: it said 0.1.0 whatever it was)
        hello.addProperty("minecraft", Mc.gameVersion());
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

    /** She stops talking at once: voice, subtitle and the rest of the line (later sentences of it are dropped). */
    private void hush() {
        voice.stop();
        currentLine++;
        long now = System.currentTimeMillis();
        companion.subtitleUntil = Math.min(companion.subtitleUntil, now);
        captionUntil = now;
        caption = "";
        companion.activity = Behavior.Activity.IDLE;
        companion.life.play(Emote.SHY, companion.now());
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
        // (no port: a LAN world gets a new port every time it's opened, and each was a new world with no memories)
        return mc.getCurrentServer() != null ? "mp:" + mc.getCurrentServer().ip.replaceFirst(":\\d+$", "") : "unknown";
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
                net.minecraft.world.item.Item item = Mc.item(
                        net.minecraft.resources.Identifier.parse(e.getKey()));
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
    /** The player she's leading you to (by name): asked of the world's game when they're too far for yours. */
    private String guidePlayer;
    private boolean guideAsking;

    /** While leading: follow a walking animal, and leave a faint trail of sparkles you can follow. */
    private void tickGuide(Minecraft mc) {
        Behavior life = companion.life;
        if (life.mode != Behavior.Mode.GUIDE) {
            guideEntity = -1;
            guidePlayer = null;
            Snapshot.headingX = Snapshot.headingZ = 0; // (hazards: look where the player looks)
            return;
        }
        double[] gt = life.guideTarget(); // hazards: look along the way she leads
        Snapshot.headingX = gt[0] - mc.player.getX();
        Snapshot.headingZ = gt[2] - mc.player.getZ();
        net.minecraft.world.entity.Entity e = guideEntity >= 0 ? mc.level.getEntity(guideEntity) : null;
        if (e != null && e.isAlive()) {
            life.retarget(e.getX(), e.getY(), e.getZ());
        } else if (guidePlayer != null && !guideAsking && mc.level.getGameTime() % 30 == 0) {
            // a friend too far for your game to see: where they are now, from the world's game
            guideAsking = true;
            String who = guidePlayer;
            Actions.whereIs(mc, who).whenComplete((r, err) -> mc.execute(() -> {
                guideAsking = false;
                if (r != null && r.has("x") && who.equals(guidePlayer) && companion.life.mode == Behavior.Mode.GUIDE) {
                    companion.life.retarget(r.get("x").getAsDouble(), r.get("y").getAsDouble(), r.get("z").getAsDouble());
                }
            }));
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
                    o.addProperty("villager", e instanceof net.minecraft.world.entity.npc.villager.AbstractVillager);
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
        for (net.minecraft.world.item.ItemStack s : Mc.items(mc.player)) {
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
        o.addProperty("singleplayer", Minecraft.getInstance().getSingleplayerServer() != null || visitingWorld);
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
            String r = res.toString(); // (Pip's actions in the game log too, briefly)
            LOG.info("{}action {} {} -> {}", id.equals("dev") ? "dev " : "", action, args, r.length() > 300 ? r.substring(0, 300) + "..." : r);
            res.addProperty("type", "done");
            res.addProperty("id", id);
            link.send(res);
        };
        Behavior life = companion.life;
        if (action.equals("follow_player")) {
            reply.accept(follow(str(args, "name")));
            return;
        }
        if (action.equals("guide") && args.has("spawn")) { // their bed (the last slept in), else the world spawn
            Minecraft m = Minecraft.getInstance();
            net.minecraft.client.server.IntegratedServer server = m.getSingleplayerServer();
            java.util.UUID me = m.player.getUUID();
            java.util.function.Consumer<double[]> lead = spot -> { // then led there like any place
                JsonObject g = new JsonObject();
                g.addProperty("x", (int) Math.floor(spot[0]));
                g.addProperty("y", (int) Math.floor(spot[1]));
                g.addProperty("z", (int) Math.floor(spot[2]));
                g.addProperty("place", spot[3] > 0 ? "your bed (where you come back to life)"
                        : "the world's spawn (no bed slept in here, or it's gone)");
                JsonObject again = new JsonObject();
                again.addProperty("id", id);
                again.addProperty("action", "guide");
                again.add("args", g);
                runAction(again);
            };
            if (server == null) { // a friend's world: only the world spawn is known here
                net.minecraft.core.BlockPos w = Mc.worldSpawn(m.level);
                lead.accept(new double[]{w.getX(), w.getY(), w.getZ(), 0});
                return;
            }
            server.execute(() -> {
                net.minecraft.server.level.ServerPlayer sp = server.getPlayerList().getPlayer(me);
                net.minecraft.core.BlockPos bed = sp == null ? null : Mc.bed(sp);
                boolean here = bed != null;
                net.minecraft.core.BlockPos p = here ? bed : Mc.worldSpawn(server.overworld());
                double[] spot = {p.getX(), p.getY(), p.getZ(), here ? 1 : 0};
                m.execute(() -> lead.accept(spot));
            });
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
                guidePlayer = follow >= 0 && follow == Actions.lastTargetEntity && animal == null ? Actions.lastTargetPlayer : null;
                res.addProperty("ok", true);
                res.addProperty("guiding", true);
                double dx = t[0] - Minecraft.getInstance().player.getX(), dz = t[2] - Minecraft.getInstance().player.getZ();
                res.addProperty("distance", Math.round(Math.sqrt(dx * dx + dz * dz)));
                res.addProperty("direction", Direction8.relative(Minecraft.getInstance().player.getYRot(), dx, dz));
                res.addProperty("following", follow >= 0 ? "someone moving (you follow them as they walk)" : "a fixed place");
                if (args.has("place")) res.addProperty("place", args.get("place").getAsString());
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
        if (msg.has("glow")) { // "light the way" (brighter, for a while), "stop glowing"
            String g = str(msg, "glow");
            long ms = (long) ((msg.has("seconds") ? msg.get("seconds").getAsDouble() : 180) * 1000);
            if (g.equals("off")) {
                dev.kindredspirit.act.Glow.offUntil = System.currentTimeMillis() + ms;
                dev.kindredspirit.act.Glow.brightUntil = 0;
            } else {
                dev.kindredspirit.act.Glow.brightUntil = System.currentTimeMillis() + ms;
                dev.kindredspirit.act.Glow.offUntil = 0;
            }
        }
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

    /** The dashboard key: her dashboard in the browser, where her brain runs (a friend with only the mod: on the host's). */
    private void openDashboard() {
        String url = dev.kindredspirit.util.Dashboard.url(cfg.brainHost, cfg.dashboardPort);
        if (!brainHere || url == null) {
            notice("Her dashboard is on the computer where her brain runs", 5000);
            return;
        }
        Mc.openInBrowser(url);
        notice(link.connected() ? "Opening her dashboard in your browser\u2026"
                : "Opening her dashboard\u2026 If it doesn't load, open Kindred Spirit Setup to wake her brain", 6000);
    }

    /** #92, in plain words: what Pip needs on this computer, where to get it, or play with a friend who hosts her. */
    private Component noBrainHint() {
        var link = (java.util.function.BiFunction<String, String, Component>) (text, url) -> Component.literal(text)
                .withStyle(st -> st.withColor(ChatFormatting.AQUA).withUnderlined(true).withClickEvent(Mc.openUrlClick(url)));
        return Component.empty()
                .append(Component.literal("Kindred Spirit: ").withStyle(ChatFormatting.LIGHT_PURPLE, ChatFormatting.BOLD))
                .append(Component.literal("Pip needs her brain on this computer to come alive. ").withStyle(ChatFormatting.WHITE))
                .append(link.apply("Get Kindred Spirit Setup", dev.kindredspirit.util.NoBrainHint.SETUP_GUIDE))
                .append(Component.literal(" (macOS for now), or ").withStyle(ChatFormatting.GRAY))
                .append(link.apply("play with a friend who hosts her", dev.kindredspirit.util.NoBrainHint.FRIENDS_GUIDE))
                .append(Component.literal(" on a LAN world. ").withStyle(ChatFormatting.GRAY))
                .append(Component.literal("[Don't show again]").withStyle(st -> st.withColor(ChatFormatting.DARK_GRAY)
                        .withClickEvent(Mc.runCommandClick("/kindred hint off"))));
    }

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
        if (cfg.chatLog) Mc.chat(mc, c);
    }

    private int bond = -1;
    private String bondLevel = "";
    private double bondChange;
    private long bondShownUntil;

    /** A soft dark panel like vanilla's subtitles, with a thin accent on the left in her color. */
    private static void panel(GuiGraphicsExtractor g, int x0, int y0, int x1, int y1, int alpha, int accent) {
        g.fill(x0, y0, x1, y1, (Math.round(alpha * 0.62f) << 24));
        if (accent != 0) g.fill(x0, y0, x0 + 2, y1, (alpha << 24) | (accent & 0xFFFFFF));
    }

    private int herColor() {
        return Mood.blend(companion.mood == Mood.OFFLINE ? 0x9FD8E6 : companion.mood.rgb, 0xFFFFFF, 0.2f);
    }

    private void hud(GuiGraphicsExtractor g) {
        Minecraft mc = Minecraft.getInstance();
        if (Mc.hudHidden(mc) || mc.player == null) return;
        long now = System.currentTimeMillis();
        int w = g.guiWidth(), h = g.guiHeight();
        var font = mc.font;
        if (companion.activity == Behavior.Activity.LISTENING) { // a pulsing red dot while the microphone is open
            String s = "Listening\u2026 release " + talkKey.getTranslatedKeyMessage().getString() + " to send";
            int tw = font.width(s) + 12, x = (w - tw) / 2, y = h - 80;
            panel(g, x - 4, y - 3, x + tw + 4, y + 10, 230, 0);
            int pulse = (int) (150 + 105 * Math.sin(now / 160.0));
            g.fill(x + 1, y + 1, x + 7, y + 7, (pulse << 24) | 0xFF5C6B);
            g.text(font, s, x + 12, y, 0xFFFFFFFF);
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
            g.text(font, displayName, x, y, (a << 24) | herColor());
            for (var line : lines) {
                g.text(font, line, x + nameW, y, (a << 24) | 0xFFFFFF);
                y += 10;
            }
        }
        boolean linked = link.connected();
        if (brainHere && !sharing && inWorld) { // her brain stopped while you play: say so, and when it's back
            if (wasLinked && !linked) {
                offlineSince = offlineNoticed = now;
                notice(displayName + "'s brain stopped. Start it again with scripts/start.sh: she'll come back by herself.", 9000);
                companion.say("zzz... (" + displayName + "'s brain isn't running)", 0, now);
                caption = companion.subtitle;
                captionUntil = companion.subtitleUntil;
            } else if (!linked && offlineSince > 0) { // (kept on screen while she's without it)
                notice = displayName + "'s brain isn't running: start it with scripts/start.sh (she'll come back by herself).";
                noticeUntil = Math.max(noticeUntil, now + 1000);
            } else if (linked && offlineSince > 0) {
                offlineSince = 0;
                notice(displayName + "'s brain is back.", 3000);
            }
        }
        wasLinked = linked;
        if (brainHere && !sharing && !link.connected() && inWorld && now - joinedAt > 3000 && now - joinedAt < 15000) {
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
            g.text(font, title, x, y, a | 0xFFFFFF);
            g.text(font, d, x + bw - font.width(d), y, a | heart);
            g.fill(x, y + 12, x + bw, y + 15, a | 0x3A3550);
            g.fill(x, y + 12, x + Math.max(1, (int) (bw * Math.min(100, bond) / 100.0)), y + 15, a | heart);
            for (int t : new int[]{15, 35, 65, 85}) g.fill(x + bw * t / 100, y + 12, x + bw * t / 100 + 1, y + 15, a | 0x15121D); // the levels
        }
        if (now >= nextTaskCheck) {
            nextTaskCheck = now + 250;
            JsonObject t = cfg.showTask && !sharing ? Snapshot.task() : null;
            taskLine = t == null ? null : t.get("what").getAsString();
            taskDone = t == null ? 0 : t.get("done").getAsInt();
            taskTotal = t == null ? 0 : t.get("total").getAsInt();
        }
        if (taskLine != null) { // what her hands are busy with, under the heart meter
            String title = displayName + ": " + taskLine;
            String count = taskDone + " / " + taskTotal;
            int tw = Math.max(98, font.width(title) + font.width(count) + 10);
            int x = w - tw - 8, y = rightY + (cfg.showBond && bond >= 0 && now < bondShownUntil ? 30 : 3);
            panel(g, x - 5, y - 4, x + tw + 5, y + 21, 230, herColor());
            g.text(font, title, x, y, 0xFFFFFFFF);
            g.text(font, count, x + tw - font.width(count), y, 0xFF000000 | herColor());
            g.fill(x, y + 12, x + tw, y + 15, 0xFF3A3550);
            g.fill(x, y + 12, x + Math.max(1, (int) (tw * (double) taskDone / Math.max(1, taskTotal))), y + 15, 0xFF000000 | herColor());
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
                g.text(font, line, 10, y, (a << 24) | 0xFFE9B8);
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
            g.text(font, arrow, x, 7, 0xFF000000 | herColor());
            g.text(font, rest, x + aw, 7, 0xFFFFE9A8);
        }
    }

    private static String str(JsonObject o, String key) {
        return o.has(key) && !o.get(key).isJsonNull() ? o.get(key).getAsString() : "";
    }
}
