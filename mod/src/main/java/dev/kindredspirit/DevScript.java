package dev.kindredspirit;

import net.minecraft.client.CameraType;
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
 *   look YAW PITCH      turn the player
 *   camera first|back|front   switch the view (F5)
 *   screenshot NAME     save screenshots/NAME.png in the dev game folder
 *   quit                close the game
 * </pre>
 */
public final class DevScript {
    private final Deque<String> lines = new ArrayDeque<>();
    private int waitTicks;

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

    public void tick(Minecraft mc) {
        if (waitTicks > 0) {
            waitTicks--;
            return;
        }
        String line = lines.peek();
        if (line == null) return;
        String[] parts = line.split(" ", 2);
        String cmd = parts[0], arg = parts.length > 1 ? parts[1] : "";
        // everything except "world" needs to be in a world
        if (!cmd.equals("world") && !cmd.equals("quit") && (mc.player == null || mc.level == null)) return;
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
            case "cmd" -> mc.player.connection.sendCommand(arg.startsWith("/") ? arg.substring(1) : arg);
            case "chat" -> KindredSpiritClient.get().talk(arg);
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
            case "screenshot" -> Screenshot.grab(mc.gameDirectory, arg + ".png", mc.getMainRenderTarget(),
                    msg -> KindredSpiritClient.LOG.info("dev script: {}", msg.getString()));
            case "quit" -> mc.stop();
            default -> KindredSpiritClient.LOG.warn("dev script: unknown step {}", line);
        }
    }
}
