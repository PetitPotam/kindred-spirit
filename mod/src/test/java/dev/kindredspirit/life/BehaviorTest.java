package dev.kindredspirit.life;

import dev.kindredspirit.util.Mood;
import dev.kindredspirit.util.Smooth;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

/** The companion's "life", simulated without the game: 20 decisions and 60 frames per second. */
public class BehaviorTest {
    static final double TICK = 0.05, FRAME = 1 / 60.0;

    /** Player standing at the origin, eyes at y=1.6, facing south (+Z). */
    static Behavior.Senses player() {
        Behavior.Senses s = new Behavior.Senses();
        s.ey = 1.6;
        s.lx = 0; s.ly = 0; s.lz = 1;
        return s;
    }

    /** Runs the companion for some seconds; returns the largest single-frame jump in position. */
    static double run(Behavior b, Behavior.Senses s, double seconds, Behavior.Activity act) {
        double maxStep = 0;
        double end = s.now + seconds;
        while (s.now < end) {
            b.tick(s, act, Mood.HAPPY, null);
            for (int i = 0; i < 3; i++) {
                double ox = b.x, oy = b.y, oz = b.z;
                b.frame(s.ex, s.ey, s.ez, s.yawDeg, s.lx, s.ly, s.lz, s.now + i * FRAME, FRAME, act, Mood.HAPPY, 0, false);
                if (s.now > 0.5) maxStep = Math.max(maxStep, Math.sqrt((b.x - ox) * (b.x - ox) + (b.y - oy) * (b.y - oy) + (b.z - oz) * (b.z - oz)));
            }
            s.now += TICK;
        }
        return maxStep;
    }

    static Behavior companion() {
        return new Behavior(0.85, -0.3, 1.9, 0.2, 42);
    }

    /** Points the player's look straight at the companion. */
    static void lookAtCompanion(Behavior.Senses s, Behavior b) {
        double dx = b.x - s.ex, dy = b.y - s.ey, dz = b.z - s.ez, n = Math.sqrt(dx * dx + dy * dy + dz * dz);
        s.lx = dx / n; s.ly = dy / n; s.lz = dz / n;
    }

    @Test
    void springEasesInWithoutOvershoot() {
        double[] st = {0, 0};
        double last = 0;
        for (int i = 0; i < 120; i++) {
            double v = Smooth.damp(st, 1, 0.3, FRAME, 100);
            assertTrue(v >= last - 1e-12 && v <= 1 + 1e-9, "monotonic, never past the target");
            last = v;
        }
        assertEquals(1, last, 0.01);
    }

    @Test
    void anglesTurnTheShortWay() {
        double[] st = {Math.toRadians(170), 0};
        Smooth.dampAngle(st, Math.toRadians(-170), 0.2, FRAME, 50);
        assertTrue(st[0] > Math.toRadians(170), "goes through 180, not back through 0");
    }

    @Test
    void noiseIsSmoothAndBounded() {
        double prev = Smooth.noise(0, 1);
        for (double x = 0.01; x < 50; x += 0.01) {
            double v = Smooth.noise(x, 1);
            assertTrue(v >= -1 && v <= 1);
            assertTrue(Math.abs(v - prev) < 0.05, "no jumps");
            prev = v;
        }
    }

    @Test
    void floatsBesideYouAndNeverJumps() {
        Behavior b = companion();
        Behavior.Senses s = player();
        double maxStep = run(b, s, 4, Behavior.Activity.IDLE);
        assertTrue(maxStep < 0.08, "moves at most a few cm per frame, was " + maxStep);
        assertTrue(b.z > 1.2 && b.z < 2.6, "in front of you: " + b.z);
        assertTrue(Math.abs(b.x) > 0.3, "off to one side, not in your face: " + b.x);
        // you walk 3 blocks forward: it follows, smoothly
        s.ez = 3;
        maxStep = run(b, s, 3, Behavior.Activity.IDLE);
        assertTrue(maxStep < 0.12, "glides after you, was " + maxStep);
        assertTrue(b.z > 4.2, "caught up: " + b.z);
    }

    @Test
    void whenYouFightSheStepsBehindYourShoulderAndComesBackAfter() {
        Behavior b = companion();
        Behavior.Senses s = player();
        run(b, s, 3, Behavior.Activity.IDLE);
        assertTrue(b.z > 1.2, "normally a little in front of you: " + b.z);
        // you swing your sword over and over at something in front of you
        double end = s.now + 2;
        while (s.now < end) {
            b.playerSwings(s.now);
            run(b, s, 0.25, Behavior.Activity.IDLE);
        }
        assertTrue(b.z < 0.2, "out of your swing, beside or behind your shoulder: " + b.z);
        assertTrue(Math.abs(b.x) > 0.9, "and to the side: " + b.x);
        assertTrue(b.keepingClear());
        run(b, s, 10, Behavior.Activity.IDLE);
        assertTrue(b.z > 1.0 && !b.keepingClear(), "back at her usual spot when it's over: " + b.z);
    }

    /** Runs with the world's blocks (a Solid) passed to every tick. */
    static void runIn(Behavior b, Behavior.Senses s, double seconds, Behavior.Solid solid) {
        double end = s.now + seconds;
        while (s.now < end) {
            b.tick(s, Behavior.Activity.IDLE, Mood.HAPPY, solid);
            for (int i = 0; i < 3; i++) {
                b.frame(s.ex, s.ey, s.ez, s.yawDeg, s.lx, s.ly, s.lz, s.now + i * FRAME, FRAME, Behavior.Activity.IDLE, Mood.HAPPY, 0, false);
            }
            s.now += TICK;
        }
    }

    @Test
    void herBodyNeverSinksIntoAWall() {
        Behavior b = companion();
        Behavior.Senses s = player();
        // a thick wall right where she likes to float (in front of you), from the ground to the sky
        Behavior.Solid wall = (x, y, z) -> z >= 1.0 && z < 3.0;
        runIn(b, s, 3, wall);
        assertFalse(b.blocked(b.x, b.y, b.z), "outside the wall: z " + b.z);
        // a block appears right where she is (you, or she, built it): she steps out of it
        double bx = Math.floor(b.x), by = Math.floor(b.y), bz = Math.floor(b.z);
        Behavior.Solid placed = (x, y, z) -> wall.at(x, y, z)
                || (Math.floor(x) == bx && Math.floor(y) == by && Math.floor(z) == bz);
        runIn(b, s, 0.2, placed);
        assertFalse(b.blocked(b.x, b.y, b.z), "stepped out of the new block");
    }

    @Test
    void neverParksInTheMiddleOfYourView() {
        Behavior b = new Behavior(0, 0, 1.9, 0.2, 1); // asked to sit dead centre
        for (double now = 0; now < 60; now += 0.37) { // whatever the wander noise is doing
            double[] t = b.target(0, 1.6, 0, 0, 0, 0, 1, now);
            double dx = t[0], dy = t[1] - 1.6, dz = t[2];
            double angle = Math.toDegrees(Math.acos(dz / Math.sqrt(dx * dx + dy * dy + dz * dz)));
            assertTrue(angle >= 13.9, "pushed out of the 14° cone: " + angle + " at " + now);
        }
    }

    @Test
    void youCanLookItInTheEyes_itHoldsStillInsteadOfSlidingAway() {
        Behavior b = companion();
        Behavior.Senses s = player();
        run(b, s, 3, Behavior.Activity.IDLE);
        // turn your head toward it, like a player would with the mouse
        double yaw = Math.toDegrees(Math.atan2(-b.x, b.z));
        s.yawDeg = yaw;
        lookAtCompanion(s, b);
        for (int i = 0; i < 40; i++) { // two seconds of looking at it
            lookAtCompanion(s, b);
            run(b, s, TICK, Behavior.Activity.IDLE);
        }
        double dx = b.x - s.ex, dz = b.z - s.ez;
        double off = Math.abs(Math.toDegrees(Math.atan2(-dx, dz)) - yaw);
        assertTrue(off < 8, "still in front of you: " + off + "°");
        assertEquals(Behavior.GazeKind.PLAYER, b.gaze());
    }

    @Test
    void driftingIntoYourViewDoesntMakeItStayThere() {
        Behavior b = companion();
        Behavior.Senses s = player(); // stands perfectly still for a minute while it wanders
        run(b, s, 2, Behavior.Activity.IDLE);
        double inCentre = 0, longest = 0;
        for (int i = 0; i < 60 * 20; i++) {
            run(b, s, TICK, Behavior.Activity.IDLE);
            double dx = b.x - s.ex, dy = b.y - s.ey, dz = b.z - s.ez;
            double angle = Math.toDegrees(Math.acos(dz / Math.sqrt(dx * dx + dy * dy + dz * dz)));
            inCentre = angle < 10 && Math.sqrt(dx * dx + dy * dy + dz * dz) < 5 ? inCentre + TICK : 0;
            longest = Math.max(longest, inCentre);
        }
        assertTrue(longest < 1.5, "never lingers in the middle of your view: " + longest + " s");
    }

    @Test
    void smallTurnsDontMoveItBigTurnsDo() {
        Behavior b = companion();
        Behavior.Senses s = player();
        run(b, s, 3, Behavior.Activity.IDLE);
        double x0 = b.x, z0 = b.z;
        s.yawDeg = 20; // a glance to the side
        s.lx = -Math.sin(Math.toRadians(20)); s.lz = Math.cos(Math.toRadians(20));
        run(b, s, 2, Behavior.Activity.IDLE);
        assertTrue(Math.hypot(b.x - x0, b.z - z0) < 0.5, "stayed roughly where it was");
        s.yawDeg = 90; // turned to face west
        s.lx = -1; s.lz = 0;
        run(b, s, 3, Behavior.Activity.IDLE);
        assertTrue(b.x < -1.2, "came around to your new front: x=" + b.x);
    }

    @Test
    void looksBackWhenYouLookAtIt_afterAHumanDelay() {
        Behavior b = companion();
        Behavior.Senses s = player();
        run(b, s, 3, Behavior.Activity.IDLE);
        lookAtCompanion(s, b);
        b.tick(s, Behavior.Activity.IDLE, Mood.HAPPY, null);
        assertNotEquals(Behavior.GazeKind.PLAYER, b.gaze(), "not instant");
        run(b, s, 0.8, Behavior.Activity.IDLE);
        assertEquals(Behavior.GazeKind.PLAYER, b.gaze(), "eye contact within a moment");
    }

    @Test
    void holdingItsGazeMakesItReact() {
        Behavior b = companion();
        Behavior.Senses s = player();
        run(b, s, 3, Behavior.Activity.IDLE);
        b.emote = null;
        for (int i = 0; i < 50 && b.emote == null; i++) {
            lookAtCompanion(s, b);
            run(b, s, TICK, Behavior.Activity.IDLE);
        }
        assertTrue(b.emote == Emote.HAPPY || b.emote == Emote.SHY || b.emote == Emote.TEASE, "got happy, shy or a wink: " + b.emote);
    }

    @Test
    void sneakingWhileLookingAtItPetsIt() {
        Behavior b = companion();
        Behavior.Senses s = player();
        run(b, s, 3, Behavior.Activity.IDLE);
        lookAtCompanion(s, b);
        run(b, s, 0.2, Behavior.Activity.IDLE);
        s.sneaking = true;
        run(b, s, TICK, Behavior.Activity.IDLE);
        assertTrue(b.petted);
        assertEquals(Emote.WIGGLE, b.emote);
    }

    @Test
    void watchesACreeperQuickly() {
        Behavior b = companion();
        Behavior.Senses s = player();
        run(b, s, 3, Behavior.Activity.IDLE);
        s.threats.add(new double[]{0, 0, -5, 1});
        run(b, s, 0.3, Behavior.Activity.IDLE);
        assertEquals(Behavior.GazeKind.POINT, b.gaze());
        run(b, s, 1.0, Behavior.Activity.IDLE);
        assertTrue(Math.cos(b.headYaw) < -0.5, "head turned toward the creeper behind (yaw " + b.headYaw + ")");
    }

    @Test
    void looksAtYouWhileTalking() {
        Behavior b = companion();
        Behavior.Senses s = player();
        run(b, s, 2, Behavior.Activity.IDLE);
        run(b, s, 1, Behavior.Activity.SPEAKING);
        assertEquals(Behavior.GazeKind.PLAYER, b.gaze());
    }

    @Test
    void wandersWhenYouStandStillThenDozesAndWakesSoftly() {
        Behavior b = companion();
        Behavior.Senses s = player();
        run(b, s, 2, Behavior.Activity.IDLE);
        double minX = 9, maxX = -9;
        for (int i = 0; i < 40; i++) {
            run(b, s, 1, Behavior.Activity.IDLE);
            minX = Math.min(minX, b.x);
            maxX = Math.max(maxX, b.x);
        }
        assertTrue(maxX - minX > 0.6, "explores around you: range " + (maxX - minX));
        run(b, s, 60, Behavior.Activity.IDLE);
        assertTrue(b.dozing(), "falls asleep after a long quiet time");
        s.speed = 4;
        run(b, s, TICK * 2, Behavior.Activity.IDLE);
        assertFalse(b.dozing());
        assertEquals(Emote.STARTLE, b.emote, "wakes with a little start");
    }

    @Test
    void stayAndComeCommands() {
        Behavior b = companion();
        Behavior.Senses s = player();
        run(b, s, 3, Behavior.Activity.IDLE);
        b.setMode(Behavior.Mode.STAY, s.now);
        double sx = b.x, sz = b.z;
        s.ez = 10;
        run(b, s, 3, Behavior.Activity.IDLE);
        assertEquals(sx, b.x, 0.2);
        assertEquals(sz, b.z, 0.2);
        b.setMode(Behavior.Mode.COME, s.now);
        run(b, s, 2, Behavior.Activity.IDLE);
        assertEquals(11.1, b.z, 0.35);
        assertEquals(0, b.x, 0.35);
        run(b, s, 6, Behavior.Activity.IDLE);
        assertEquals(Behavior.Mode.FOLLOW, b.mode, "comes close for a moment, then back to following");
    }

    @Test
    void aWallInFrontKeepsHerOnYourSideInSight() {
        Behavior b = companion();
        Behavior.Senses s = player();
        run(b, s, 2, Behavior.Activity.IDLE);
        Behavior.Solid wall = (x, y, z) -> z > 1.0 && y < 2.5;
        runIn(b, s, 2, wall);
        assertFalse(b.blocked(b.x, b.y, b.z), "not inside the wall");
        assertTrue(b.clear(s.ex, s.ey, s.ez, b.x, b.y, b.z), "where you can see her: " + b.x + " " + b.y + " " + b.z);
    }

    /** A small house around you: walls at x = +-3 and z = +-3, floor at y < 0, ceiling at y >= 3. */
    static final Behavior.Solid HOUSE = (x, y, z) -> y < 0 || (y >= 3 && y < 4)
            || ((Math.abs(x) >= 3 && Math.abs(x) < 4 || Math.abs(z) >= 3 && Math.abs(z) < 4) && y < 4
                && !(z <= -3 && z > -4 && Math.abs(x) < 1 && y < 2)); // a door in the wall behind you

    @Test
    void indoorsSheStaysInTheRoomNotOnTheRoof() {
        Behavior b = companion();
        Behavior.Senses s = player();
        runIn(b, s, 4, HOUSE);
        assertTrue(b.y < 3, "under the ceiling, in the room: y " + b.y);
        assertTrue(Math.abs(b.x) < 3 && Math.abs(b.z) < 3, "inside the walls: " + b.x + " " + b.z);
    }

    @Test
    void fromOutsideSheComesInThroughTheDoor() {
        Behavior b = companion();
        Behavior.Senses s = player();
        runIn(b, s, 1, (x, y, z) -> y < 0);
        // she's outside, past the back wall, when you walk in (the house appears around you)
        b.x = 0.5; b.y = 1.5; b.z = -7;
        b.placeAt(b.x, b.y, b.z);
        double highest = -9;
        boolean wentIn = false;
        double end = s.now + 8;
        while (s.now < end) {
            runIn(b, s, 0.1, HOUSE);
            highest = Math.max(highest, b.y);
            assertFalse(b.blocked(b.x, b.y, b.z), "never inside the walls: " + b.x + " " + b.y + " " + b.z);
            if (Math.abs(b.x) < 3 && Math.abs(b.z) < 3 && b.y < 3) wentIn = true;
        }
        assertTrue(wentIn, "came in: " + b.x + " " + b.y + " " + b.z);
        assertTrue(highest < 3.5, "through the door, not over the roof: highest " + highest);
    }

    @Test
    void aClosedRoomAndSheBlinksToYou() {
        Behavior b = companion();
        Behavior.Senses s = player();
        Behavior.Solid closed = (x, y, z) -> HOUSE.at(x, y, z) || (z <= -3 && z > -4 && y < 4);
        runIn(b, s, 1, (x, y, z) -> y < 0);
        b.placeAt(0.5, 1.5, -7);
        runIn(b, s, 1, closed);
        assertTrue(Math.abs(b.x) < 3 && Math.abs(b.z) < 3 && b.y < 3, "beside you: " + b.x + " " + b.y + " " + b.z);
    }

    @Test
    void wingsFlutterAndFoldWhenItDozes() {
        Behavior b = companion();
        Behavior.Senses s = player();
        double min = 9, max = -9;
        for (int i = 0; i < 60; i++) {
            b.frame(0, 1.6, 0, 0, 0, 0, 1, i * FRAME, FRAME, Behavior.Activity.IDLE, Mood.HAPPY, 0, true);
            min = Math.min(min, b.wingAngle);
            max = Math.max(max, b.wingAngle);
        }
        assertTrue(max - min > 0.5, "flutters: " + min + ".." + max);
        b.play(Emote.DOZE, 1);
        for (int i = 0; i < 300; i++) {
            b.frame(0, 1.6, 0, 0, 0, 0, 1, 1 + i * FRAME, FRAME, Behavior.Activity.IDLE, Mood.HAPPY, 0, true);
        }
        assertTrue(b.wingAngle > 1.1, "folded back while asleep: " + b.wingAngle);
    }

    @Test
    void guidesYouThereLookingBackThenCelebrates() {
        Behavior b = companion();
        Behavior.Senses s = player();
        run(b, s, 2, Behavior.Activity.IDLE);
        b.guide(30, 64, 0, s.now); // 30 blocks to the west... well, +X
        run(b, s, 2, Behavior.Activity.IDLE);
        assertEquals(Behavior.Mode.GUIDE, b.mode);
        assertTrue(b.x > 1.5, "floats ahead toward the target: x=" + b.x);
        assertEquals(Behavior.GazeKind.PLAYER, b.gaze(), "looks back to check you follow");
        assertEquals(30, b.guideDistance, 0.5);
        for (int i = 0; i < 30; i++) { // you walk there
            s.ex += 1;
            run(b, s, 0.3, Behavior.Activity.IDLE);
        }
        assertEquals(Behavior.Mode.FOLLOW, b.mode, "arrived: back to following");
        assertTrue(b.arrived);
        assertEquals(Emote.HAPPY, b.emote);
    }

    @Test
    void whenYouSprintSheStaysAheadAndCallsYouBackIfYouGoTheWrongWay() {
        Behavior b = companion();
        Behavior.Senses s = player();
        run(b, s, 2, Behavior.Activity.IDLE);
        b.guide(200, 64, 0, s.now);
        double minLead = 99;
        for (int i = 0; i < 100; i++) { // sprinting toward it: 5.6 blocks a second
            s.ex += 5.6 * TICK;
            run(b, s, TICK, Behavior.Activity.IDLE);
            if (i > 20) minLead = Math.min(minLead, b.x - s.ex);
        }
        assertTrue(minLead > 3, "always well ahead of you, even sprinting: " + minLead);
        assertTrue(b.y > s.ey + 0.3, "above your head, visible over the grass");
        assertFalse(b.wrongWay);
        for (int i = 0; i < 60; i++) { // you turn around and walk away
            s.ex -= 4.3 * TICK;
            run(b, s, TICK, Behavior.Activity.IDLE);
        }
        assertTrue(b.wrongWay, "this way!");
        assertEquals(Behavior.Mode.GUIDE, b.mode, "still leading");
    }

    @Test
    void ifAWallStopsYouOffTheWaySheStillCallsYouBack() {
        Behavior b = companion();
        Behavior.Senses s = player();
        b.guide(40, 64, 0, s.now);
        run(b, s, 1, Behavior.Activity.IDLE);
        for (int i = 0; i < 30; i++) { // 7 blocks the wrong way, then stuck against a wall
            s.ex -= 0.25;
            run(b, s, TICK, Behavior.Activity.IDLE);
        }
        run(b, s, 2, Behavior.Activity.IDLE);
        assertTrue(b.wrongWay);
    }

    @Test
    void onlyAHitRightOnHerCounts() {
        Behavior b = companion();
        Behavior.Senses s = player();
        run(b, s, 3, Behavior.Activity.IDLE);
        double dx = b.x - s.ex, dy = b.y - s.ey, dz = b.z - s.ez, d = Math.sqrt(dx * dx + dy * dy + dz * dz);
        s.lx = dx / d; s.ly = dy / d; s.lz = dz / d;  // crosshair right on her
        assertTrue(b.aimedAt(s, Double.MAX_VALUE));
        assertFalse(b.aimedAt(s, d - 0.5), "a cow (or a block) in front of her takes the hit");
        double side = Math.atan2(s.lx, s.lz) + 0.35;  // 20 degrees off: the mob next to her
        s.lx = Math.sin(side); s.ly = 0; s.lz = Math.cos(side);
        assertFalse(b.aimedAt(s, Double.MAX_VALUE), "near her is not on her");
    }

    @Test
    void sheFollowsAWalkingAnimal() {
        Behavior b = companion();
        Behavior.Senses s = player();
        b.guide(40, 64, 0, s.now);
        b.retarget(0, 64, 40);
        run(b, s, 1, Behavior.Activity.IDLE);
        assertTrue(b.z > 2 && Math.abs(b.x) < 1.5, "leads toward where the animal is now: " + b.x + "," + b.z);
    }

    @Test
    void sheFloatsCloserWhenSheFeelsCloseAndAwayWhenHurt() {
        assertEquals(1.0, Behavior.distanceScale(0.5), 1e-9);
        assertTrue(Behavior.distanceScale(1) < 0.8 && Behavior.distanceScale(0) > 2);
        Behavior near = companion(), far = companion();
        near.closeness = 1;
        far.closeness = 0;
        Behavior.Senses a = player(), b = player();
        run(near, a, 8, Behavior.Activity.IDLE);
        run(far, b, 8, Behavior.Activity.IDLE);
        double dn = Math.hypot(near.x, near.z), df = Math.hypot(far.x, far.z);
        assertTrue(df > dn * 1.6, "hurt: further away (" + df + " vs " + dn + ")");
    }

    @Test
    void sheVanishesAndComesBack() {
        Behavior b = companion();
        Behavior.Senses s = player();
        run(b, s, 2, Behavior.Activity.IDLE);
        b.hide(5, s.now);
        run(b, s, 2, Behavior.Activity.IDLE);
        assertTrue(b.hidden() && b.presence < 0.05, "gone");
        run(b, s, 4, Behavior.Activity.IDLE);
        assertFalse(b.hidden());
        assertTrue(b.presence > 0.9, "back");
        assertEquals(Emote.SHY, b.emote, "a little shy when she comes back");
    }

    @Test
    void gesturesStartAndEndSoftly() {
        for (Emote e : Emote.values()) {
            if (e.seconds <= 0) continue;
            Emote.Pose start = new Emote.Pose(), end = new Emote.Pose();
            e.apply(0, start);
            e.apply(e.seconds, end);
            double spin = e == Emote.SPIN ? 2 * Math.PI : 0;
            assertEquals(0, start.yaw + start.pitch + start.roll + start.lift + start.blush, 1e-6, e + " starts at rest");
            assertEquals(spin, end.yaw, 1e-6, e + " ends at rest");
            assertEquals(0, end.pitch + end.roll + end.lift + end.blush, 1e-3, e + " ends at rest");
        }
    }
}
