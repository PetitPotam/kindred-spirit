package dev.kindredspirit;

import com.google.gson.JsonParser;
import dev.kindredspirit.record.FrameRecorder;
import dev.kindredspirit.life.Behavior;
import net.minecraft.client.CameraType;
import net.minecraft.world.phys.Vec3;
import net.minecraft.client.Minecraft;
import net.minecraft.client.Screenshot;
import net.minecraft.client.gui.screens.AccessibilityOnboardingScreen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.client.tutorial.TutorialSteps;
import net.minecraft.world.Difficulty;
import net.minecraft.world.level.GameRules;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.LevelSettings;
import net.minecraft.world.level.WorldDataConfiguration;
import net.minecraft.world.level.levelgen.WorldOptions;
import net.minecraft.world.level.levelgen.presets.WorldPresets;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.Deque;

/**
 * A tiny test script for the sandbox game ({@code ./gradlew runClient}), so a change can be tried
 * without touching your real Minecraft. Only active when the JVM is started with
 * {@code -Dkindredspirit.devScript=<file>} and that file exists, which
 * {@code ./gradlew runClient -PdevScript=devscripts/smoke-test.txt} does. One command per line:
 * <pre>
 *   world NAME          open this test world, creating it (survival, cheats on) if needed
 *   wait TICKS          wait (20 ticks = 1 second)
 *   cmd COMMAND         run a game command, e.g. "cmd summon creeper ~ ~ ~-5 {NoAI:1b}"
 *   chat TEXT           type TEXT to the companion, as with /kindred TEXT
 *   type TEXT           type TEXT in the game's chat (plain chat goes through chatMode; /... is a command)
 *   waitsay N           wait until she says something new (at most N ticks)
 *   leave               save and quit to the title screen (then: world NAME)
 *   caption TEXT        a note shown at the bottom of the edited video from here (until the next caption or chapter end)
 *   look YAW PITCH      turn the player
 *   camera first|back|front   switch the view (F5)
 *   skin ID             wear this skin
 *   emote NAME          play a gesture (nod, spin, hop, shy...)
 *   act JSON            as if the brain sent {"move": "stay"} and the like
 *   brain JSON          as if the brain sent this message, e.g. {"type": "say", "text": "Hi!", "mood": "happy"},
 *                       {"type": "mood", "mood": "sad"}, {"type": "bond", "value": 40, "level": "friend", "change": 0.6}
 *                       (to film or check her looks with no brain running)
 *   lookat companion    turn the player to look straight at the companion
 *   sneak on|off        hold or release sneak (sneaking while looking at it pets it)
 *   press attack|use    press the attack (left click) or use (right click) key for a moment
 *   do ACTION [JSON]    run one of her actions directly (find_ore, prank_sound, steal_block...)
 *
 * For demo videos:
 *   video               HUD hidden (subtitles stay), chat log off, FOV 75, Fancy, no view bobbing
 *   record start NAME   record the screen to mod/run/recordings/NAME (needs ffmpeg); record stop
 *   mark NAME           a named moment in the recording (the editing script cuts on them)
 *   turn YAW PITCH SEC  turn the camera smoothly (eased), instead of "look" which snaps
 *   turnto companion SEC  turn smoothly to look at the companion
 *   track companion SEC   keep the camera on the companion for a while, smoothly (like a player would)
 *   walk SEC            walk forward for a while
 *   voice FILE.wav      as if the player held the talk key and said this (16 kHz WAV); a file
 *                       NAME_hq.wav next to it, if present, is the one the video uses
 *   screenshot NAME     save screenshots/NAME.png in the dev game folder
 *   quit                close the game
 * </pre>
 */
public final class DevScript {
    private final Deque<String> lines = new ArrayDeque<>();
    private int waitTicks;
    private int waitSayFrom = -1; // "waitsay": waiting until she says something new
    // smooth camera turn
    private float fromYaw, fromPitch, toYaw, toPitch;
    private long turnStart, turnNanos;
    private boolean turning;
    private int walkTicks, voiceTicks, pressTicks;
    private net.minecraft.client.KeyMapping pressed;
    private long trackUntil, lastTrackFrame;
    private byte[] pendingVoice;

    private DevScript() {}

    public static DevScript load() {
        String file = System.getProperty("kindredspirit.devScript");
        if (file == null || file.isBlank()) return null;
        Path p = Path.of(file);
        if (!Files.isRegularFile(p)) return null;
        DevScript s = new DevScript();
        try {
            for (String l : Files.readAllLines(p)) {
                l = l.strip();
                if (!l.isEmpty() && !l.startsWith("#")) s.lines.add(l);
            }
        } catch (Exception e) {
            KindredSpiritClient.LOG.warn("Dev script unreadable: {}", e.toString());
            return null;
        }
        KindredSpiritClient.LOG.info("Dev script {} with {} steps", p, s.lines.size());
        return s;
    }

    /** Every drawn frame: the smooth camera turn (per frame, so it is not choppy at 20 ticks). */
    public void frame(Minecraft mc) {
        if (mc.player == null) return;
        long now = System.nanoTime();
        if (now < trackUntil) {
            double dt = lastTrackFrame == 0 ? 0 : Math.min(0.1, (now - lastTrackFrame) / 1e9);
            lastTrackFrame = now;
            Behavior life = KindredSpiritClient.get().companion().life;
            Vec3 eye = mc.player.getEyePosition();
            double dx = life.x - eye.x, dy = life.y - eye.y, dz = life.z - eye.z;
            float yaw = (float) Math.toDegrees(Math.atan2(-dx, dz));
            float pitch = (float) -Math.toDegrees(Math.atan2(dy, Math.sqrt(dx * dx + dz * dz)));
            float cy = mc.player.getYRot(), cp = mc.player.getXRot();
            float d = ((yaw - cy) % 360 + 540) % 360 - 180;
            float k = (float) (1 - Math.exp(-dt * 6)); // eases on, never snaps
            float ny = cy + d * k, np = cp + (pitch - cp) * k;
            mc.player.setYRot(ny);
            mc.player.yRotO = ny;
            mc.player.setYHeadRot(ny);
            mc.player.setXRot(np);
            mc.player.xRotO = np;
            return;
        }
        lastTrackFrame = 0;
        if (!turning) return;
        double u = Math.min(1, (System.nanoTime() - turnStart) / (double) turnNanos);
        double e = u * u * (3 - 2 * u); // ease in and out
        float yaw = (float) (fromYaw + (toYaw - fromYaw) * e), pitch = (float) (fromPitch + (toPitch - fromPitch) * e);
        mc.player.setYRot(yaw);
        mc.player.yRotO = yaw;
        mc.player.setYHeadRot(yaw);
        mc.player.setXRot(pitch);
        mc.player.xRotO = pitch;
        if (u >= 1) turning = false;
    }

    private void startTurn(Minecraft mc, float yaw, float pitch, double seconds) {
        fromYaw = mc.player.getYRot();
        fromPitch = mc.player.getXRot();
        // the short way round
        float d = ((yaw - fromYaw) % 360 + 540) % 360 - 180;
        toYaw = fromYaw + d;
        toPitch = pitch;
        turnStart = System.nanoTime();
        turnNanos = (long) (Math.max(0.05, seconds) * 1e9);
        turning = true;
    }

    public void tick(Minecraft mc) {
        if (walkTicks > 0 && --walkTicks == 0) mc.options.keyUp.setDown(false);
        if (pressTicks > 0 && --pressTicks == 0 && pressed != null) pressed.setDown(false);
        if (voiceTicks > 0 && --voiceTicks == 0 && pendingVoice != null) {
            KindredSpiritClient.get().sendVoice(pendingVoice);
            pendingVoice = null;
        }
        if (waitSayFrom >= 0 && FrameRecorder.pipLines() > waitSayFrom) { // she spoke: go on (a beat later)
            waitSayFrom = -1;
            waitTicks = Math.min(waitTicks, 1);
        }
        if (waitTicks > 0) {
            waitTicks--;
            if (waitTicks == 0) waitSayFrom = -1;
            return;
        }
        String line = lines.peek();
        if (line == null) return;
        String[] parts = line.split(" ", 2);
        String cmd = parts[0], arg = parts.length > 1 ? parts[1] : "";
        // everything except "world" needs to be in a world
        if (!cmd.equals("world") && !cmd.equals("quit") && !cmd.equals("wait") && !cmd.startsWith("#")
                && (mc.player == null || mc.level == null)) return;
        // a first launch shows the accessibility welcome screen before the title screen
        if (cmd.equals("world") && !(mc.screen instanceof TitleScreen || mc.screen instanceof AccessibilityOnboardingScreen)) return;
        lines.poll();
        KindredSpiritClient.LOG.info("dev script: {}", line);
        switch (cmd) {
            case "world" -> {
                mc.options.onboardAccessibility = false;
                mc.getTutorial().setStep(TutorialSteps.NONE); // no "move with WASD" popup in screenshots
                if (mc.getLevelSource().levelExists(arg)) {
                    mc.createWorldOpenFlows().openWorld(arg, () -> mc.setScreen(new TitleScreen()));
                } else {
                    LevelSettings settings = new LevelSettings(arg, GameType.SURVIVAL, false, Difficulty.EASY, true,
                            new GameRules(), WorldDataConfiguration.DEFAULT);
                    mc.createWorldOpenFlows().createFreshLevel(arg, settings, new WorldOptions(20261111L, true, false),
                            WorldPresets::createNormalWorldDimensions, new TitleScreen());
                }
            }
            case "wait" -> waitTicks = Integer.parseInt(arg.trim());
            case "waitsay" -> { // until she says something (at most N ticks)
                waitSayFrom = FrameRecorder.pipLines();
                waitTicks = Integer.parseInt(arg.trim());
            }
            case "leave" -> { // save and quit to the title screen (then "world" can open another one)
                boolean local = mc.isLocalServer();
                mc.level.disconnect();
                mc.disconnect(local ? new net.minecraft.client.gui.screens.GenericMessageScreen(
                        net.minecraft.network.chat.Component.literal("Saving...")) : new TitleScreen());
                mc.setScreen(new TitleScreen());
            }
            case "cmd" -> mc.player.connection.sendCommand(arg.startsWith("/") ? arg.substring(1) : arg);
            case "chat" -> {
                FrameRecorder.line("you", arg);
                KindredSpiritClient.get().talk(arg);
            }
            case "type" -> { // as if typed in the game's chat (plain chat, or /command)
                FrameRecorder.line("you", arg);
                if (arg.startsWith("/")) mc.player.connection.sendCommand(arg.substring(1));
                else mc.player.connection.sendChat(arg);
            }
            case "caption" -> FrameRecorder.line("caption", arg); // a note for the edit (shown at the bottom)
            case "look" -> {
                String[] yp = arg.trim().split("\\s+");
                mc.player.setYRot(Float.parseFloat(yp[0]));
                mc.player.setXRot(Float.parseFloat(yp[1]));
            }
            case "camera" -> mc.options.setCameraType(switch (arg.trim()) {
                case "back" -> CameraType.THIRD_PERSON_BACK;
                case "front" -> CameraType.THIRD_PERSON_FRONT;
                default -> CameraType.FIRST_PERSON;
            });
            case "skin" -> mc.player.connection.sendCommand("kindred skin " + arg.trim());
            case "emote" -> KindredSpiritClient.get().applyAct(JsonParser.parseString("{\"emote\":\"" + arg.trim() + "\"}").getAsJsonObject());
            case "act" -> KindredSpiritClient.get().applyAct(JsonParser.parseString(arg).getAsJsonObject());
            case "brain" -> KindredSpiritClient.get().devBrainMessage(JsonParser.parseString(arg).getAsJsonObject());
            case "lookat" -> {
                Behavior life = KindredSpiritClient.get().companion().life;
                Vec3 eye = mc.player.getEyePosition();
                double dx = life.x - eye.x, dy = life.y - eye.y, dz = life.z - eye.z;
                mc.player.setYRot((float) Math.toDegrees(Math.atan2(-dx, dz)));
                mc.player.setXRot((float) -Math.toDegrees(Math.atan2(dy, Math.sqrt(dx * dx + dz * dz))));
            }
            case "sneak" -> mc.options.keyShift.setDown(arg.trim().equals("on"));
            case "press" -> {
                pressed = arg.trim().equals("use") ? mc.options.keyUse : mc.options.keyAttack;
                pressed.setDown(true);
                net.minecraft.client.KeyMapping.click(pressed.getDefaultKey());
                pressTicks = 2;
            }
            case "do" -> {
                String[] a = arg.trim().split("\\s+", 2);
                KindredSpiritClient.get().devAction(a[0], a.length > 1 ? JsonParser.parseString(a[1]).getAsJsonObject() : new com.google.gson.JsonObject());
            }
            case "video" -> {
                mc.options.hideGui = true;
                mc.options.fov().set(75);
                mc.options.graphicsMode().set(net.minecraft.client.GraphicsStatus.FANCY);
                mc.options.cloudStatus().set(net.minecraft.client.CloudStatus.FANCY);
                mc.options.bobView().set(false);
                KindredSpiritClient.get().config().chatLog = false;
            }
            case "record" -> {
                String[] a = arg.trim().split("\\s+");
                if (a[0].equals("start")) {
                    FrameRecorder.start(mc.gameDirectory.toPath().resolve("recordings").resolve(a.length > 1 ? a[1] : "demo"));
                } else {
                    FrameRecorder.stop();
                }
            }
            case "mark" -> FrameRecorder.mark(arg.trim());
            case "turn" -> {
                String[] a = arg.trim().split("\\s+");
                startTurn(mc, Float.parseFloat(a[0]), Float.parseFloat(a[1]), a.length > 2 ? Double.parseDouble(a[2]) : 1);
            }
            case "turnto" -> {
                String[] a = arg.trim().split("\\s+");
                Behavior life = KindredSpiritClient.get().companion().life;
                Vec3 eye = mc.player.getEyePosition();
                double dx = life.x - eye.x, dy = life.y - eye.y, dz = life.z - eye.z;
                startTurn(mc, (float) Math.toDegrees(Math.atan2(-dx, dz)),
                        (float) -Math.toDegrees(Math.atan2(dy, Math.sqrt(dx * dx + dz * dz))),
                        a.length > 1 ? Double.parseDouble(a[1]) : 1);
            }
            case "track" -> {
                String[] a = arg.trim().split("\\s+");
                trackUntil = System.nanoTime() + (long) ((a.length > 1 ? Double.parseDouble(a[1]) : 2) * 1e9);
                turning = false;
            }
            case "walk" -> {
                mc.options.keyUp.setDown(true);
                walkTicks = (int) Math.round(Double.parseDouble(arg.trim()) * 20);
            }
            case "voice" -> {
                try {
                    Path wav = Path.of(arg.trim());
                    pendingVoice = Files.readAllBytes(wav);
                    String name = wav.getFileName().toString();
                    Path hq = wav.resolveSibling(name.replace(".wav", "_hq.wav"));
                    FrameRecorder.soundFile("player", Files.exists(hq) ? hq : wav);
                    // "hold the key" for as long as the words take, then let go
                    dev.kindredspirit.util.Wav.Info info = dev.kindredspirit.util.Wav.parse(pendingVoice);
                    voiceTicks = Math.max(1, (int) Math.round((info == null ? 1 : info.seconds()) * 20) + 4);
                    KindredSpiritClient.get().companion().activity = Behavior.Activity.LISTENING;
                } catch (Exception e) {
                    KindredSpiritClient.LOG.warn("dev script: cannot read {}: {}", arg, e.toString());
                }
            }
            case "screenshot" -> Screenshot.grab(mc.gameDirectory, arg + ".png", mc.getMainRenderTarget(),
                    msg -> KindredSpiritClient.LOG.info("dev script: {}", msg.getString()));
            case "quit" -> mc.stop();
            default -> KindredSpiritClient.LOG.warn("dev script: unknown step {}", line);
        }
    }
}
