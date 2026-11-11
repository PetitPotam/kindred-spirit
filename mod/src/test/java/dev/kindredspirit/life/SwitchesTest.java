package dev.kindredspirit.life;

import dev.kindredspirit.LifeSwitches;
import org.junit.jupiter.api.Test;

import static dev.kindredspirit.life.BehaviorTest.*;
import static org.junit.jupiter.api.Assertions.*;

/** Every liveliness switch, turned off, really turns its behavior off. */
class SwitchesTest {
    static Behavior with(Behavior.Settings s) {
        return new Behavior(0.85, -0.3, 1.9, 0.2, 42, s);
    }

    @Test
    void noWanderAndNoDriftMeansItStaysPut() {
        Behavior.Settings set = new Behavior.Settings();
        set.wander = false;
        set.drift = 0;
        set.switchSides = false;
        Behavior b = with(set);
        Behavior.Senses s = player();
        run(b, s, 3, Behavior.Activity.IDLE);
        double x0 = b.x, z0 = b.z;
        run(b, s, 40, Behavior.Activity.IDLE);
        assertEquals(x0, b.x, 0.05, "no wandering while you stand still");
        assertEquals(z0, b.z, 0.05);
    }

    @Test
    void dozeCanBeTurnedOffAndTurningItOffWakesIt() {
        Behavior.Settings set = new Behavior.Settings();
        set.dozeAfterSeconds = 0;
        Behavior b = with(set);
        Behavior.Senses s = player();
        run(b, s, 150, Behavior.Activity.IDLE);
        assertFalse(b.dozing());

        Behavior.Settings quick = new Behavior.Settings();
        quick.dozeAfterSeconds = 20;
        Behavior b2 = with(quick);
        Behavior.Senses s2 = player();
        run(b2, s2, 25, Behavior.Activity.IDLE);
        assertTrue(b2.dozing(), "dozes after the chosen time");
        quick.dozeAfterSeconds = 0;
        run(b2, s2, 0.2, Behavior.Activity.IDLE);
        assertFalse(b2.dozing(), "wakes when you switch dozing off");
    }

    @Test
    void lookBackOffMeansNoEyeContact() {
        Behavior.Settings set = new Behavior.Settings();
        set.lookBack = false;
        set.glances = false;
        Behavior b = with(set);
        Behavior.Senses s = player();
        run(b, s, 3, Behavior.Activity.IDLE);
        for (int i = 0; i < 40; i++) {
            lookAtCompanion(s, b);
            run(b, s, TICK, Behavior.Activity.IDLE);
        }
        assertNotEquals(Behavior.GazeKind.PLAYER, b.gaze());
        assertNull(b.emote, "no happy/shy reaction either");
    }

    @Test
    void noGlancesMeansItSharesYourView() {
        Behavior.Settings set = new Behavior.Settings();
        set.glances = false;
        set.wander = false; // (wandering across your view would make it glance back at you)
        Behavior b = with(set);
        Behavior.Senses s = player();
        s.interests.add(new double[]{3, 0, 3});
        for (int i = 0; i < 30; i++) {
            run(b, s, 1, Behavior.Activity.IDLE);
            assertEquals(Behavior.GazeKind.SHARED, b.gaze());
        }
    }

    @Test
    void pettingAndThreatWatchingCanBeOff() {
        Behavior.Settings set = new Behavior.Settings();
        set.petting = false;
        set.watchThreats = false;
        set.glances = false;
        Behavior b = with(set);
        Behavior.Senses s = player();
        run(b, s, 3, Behavior.Activity.IDLE);
        lookAtCompanion(s, b);
        run(b, s, 0.2, Behavior.Activity.IDLE);
        s.sneaking = true;
        run(b, s, TICK, Behavior.Activity.IDLE);
        assertFalse(b.petted);
        s.sneaking = false;
        s.lx = 0; s.ly = 0; s.lz = 1;
        s.threats.add(new double[]{0, 0, -5, 1});
        run(b, s, 2, Behavior.Activity.IDLE);
        assertNotEquals(Behavior.GazeKind.POINT, b.gaze());
    }

    @Test
    void zeroTurnSlackKeepsItRightAtYourSide() {
        Behavior.Settings set = new Behavior.Settings();
        set.turnSlack = 0;
        set.drift = 0;
        set.wander = false;
        Behavior b = with(set);
        Behavior.Senses s = player();
        run(b, s, 3, Behavior.Activity.IDLE);
        s.yawDeg = 20; // a small turn already moves it
        s.lx = -Math.sin(Math.toRadians(20)); s.lz = Math.cos(Math.toRadians(20));
        double x0 = b.x;
        run(b, s, 2, Behavior.Activity.IDLE);
        assertTrue(Math.abs(b.x - x0) > 0.5, "followed the small turn");
    }

    @Test
    void switchesByName() {
        Behavior.Settings set = new Behavior.Settings();
        assertTrue(LifeSwitches.names().contains("wander"));
        assertNull(LifeSwitches.set(set, "wander", "off"));
        assertFalse(set.wander);
        assertNull(LifeSwitches.set(set, "dozeAfterSeconds", "300"));
        assertEquals(300, set.dozeAfterSeconds);
        assertNull(LifeSwitches.set(set, "drift", "0.5"));
        assertEquals("0.5", LifeSwitches.get(set, "drift"));
        assertNotNull(LifeSwitches.set(set, "drift", "9"), "out of range");
        assertNotNull(LifeSwitches.set(set, "petting", "maybe"));
        assertNotNull(LifeSwitches.set(set, "nope", "on"));
        LifeSwitches.reset(set);
        assertTrue(set.wander);
        assertEquals(90, set.dozeAfterSeconds);
    }
}
