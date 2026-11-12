package dev.kindredspirit.life;

import dev.kindredspirit.util.Mood;
import dev.kindredspirit.util.Smooth;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * What makes the companion feel alive: where it floats and what it looks at.
 *
 * <p>Two speeds, like a real creature: {@link #tick} (20 times a second) <em>decides</em>
 * (follow you or wander, what catches its eye, when to react), and {@link #frame} (every drawn
 * frame) <em>moves</em> toward those decisions with springs, so nothing ever snaps.
 *
 * <p>Rules of thumb that keep it from feeling robotic:
 * <ul>
 *   <li>Reactions come after a short, slightly random delay (0.1–0.35 s), like a person noticing.</li>
 *   <li>Eyes move first and fast, the head follows more slowly.</li>
 *   <li>Its idle drift is smooth noise, not a loop; it switches sides now and then.</li>
 *   <li>When you look at it, it looks back; hold its gaze and it gets happy (or shy).</li>
 *   <li>When you stand still it wanders around you and looks at things; after a long while it dozes.</li>
 *   <li>It doesn't swing around with every small turn of your head: it keeps its spot until you
 *       have turned clearly away (with some slack, so it doesn't twitch at the edge), and it holds
 *       still while you look at it, so you can look it in the eyes.</li>
 *   <li>It never parks in the middle of your view, unless you are looking at it on purpose.</li>
 * </ul>
 * No Minecraft classes here: the game fills in {@link Senses}, and tests can too.
 */
public final class Behavior {
    public enum Activity { IDLE, LISTENING, THINKING, SPEAKING }

    public enum Mode { FOLLOW, STAY, COME, GUIDE, HIDE, VISIT }

    public enum Side { RIGHT, LEFT, ABOVE }

    /** What the gaze is on. SHARED = whatever you are looking at ("joint attention"). */
    public enum GazeKind { PLAYER, SHARED, POINT, DIRECTION }

    public interface Solid {
        boolean at(double x, double y, double z);
    }

    /**
     * Switches for each part of its liveliness, so every player can find the companion they want:
     * from a calm one that just floats beside you to a curious one that wanders and plays.
     * Saved in kindredspirit.json under "life"; change them in game with /kindred life.
     */
    public static final class Settings {
        /** Wanders around you when you stand still. */
        public boolean wander = true;
        /** Gentle drifting beside you: 0 = perfectly still, 1 = normal, 2 = very lively. */
        public double drift = 1.0;
        /** Switches shoulders now and then. */
        public boolean switchSides = true;
        /** Glances at animals, items and around; off = looks where you look. */
        public boolean glances = true;
        /** Looks back at you when you look at it. */
        public boolean lookBack = true;
        /** Gets happy or shy when you hold its gaze. */
        public boolean eyeContactReactions = true;
        /** Sneaking while looking at it pets it. */
        public boolean petting = true;
        /** Turns to watch nearby monsters. */
        public boolean watchThreats = true;
        /** Hops when excited, looks up while thinking. */
        public boolean moodGestures = true;
        /** Plays the gestures the AI adds to its replies. */
        public boolean aiGestures = true;
        /** Dozes off after this many quiet seconds; 0 = never. */
        public int dozeAfterSeconds = 90;
        /** Degrees you can turn before it floats back to your side; 0 = always right at your side. */
        public double turnSlack = 32;
        /** Never parks in the middle of your view. */
        public boolean keepOutOfView = true;
    }

    /** What the companion knows this tick. Filled by the game (or a test). */
    public static final class Senses {
        public double now;                      // seconds
        public double ex, ey, ez;               // player's eyes
        public double lx, ly = 0, lz = 1;       // player's look direction (unit)
        public double yawDeg;                   // player's yaw (Minecraft degrees)
        public double speed;                    // player's speed, blocks per second
        public boolean sneaking;
        public boolean hasLookHit;              // where the player is looking, if it hits something
        public double hx, hy, hz;
        /** Hostile mobs, closest first: {x, y, z, 1 if creeper else 0}. */
        public final List<double[]> threats = new ArrayList<>();
        /** Things worth a glance (animals, villagers, dropped items): {x, y, z}. */
        public final List<double[]> interests = new ArrayList<>();
    }

    // ------------------------------------------------------------------ settings
    private final double baseRight, baseUp, baseForward;
    private final double radius;
    private final Random rng;

    // ------------------------------------------------------------------ outputs, read by the renderer
    public double x, y, z;
    public double headYaw, headPitch;          // radians; yaw = atan2(dx, dz), pitch up = positive
    public double pupilX, pupilY;              // -1..1 within the eye
    public double leanAngle, leanAxisX, leanAxisZ;
    public double lift, squish, blink, shiver;
    /** How far the wings are swung back from fully spread (radians), for skins with wings. */
    public double wingAngle = 0.55;
    private final double[] wingBase = {0.55, 0}, wingAmp = {0.45, 0};
    private double wingPhase;
    public final Emote.Pose pose = new Emote.Pose();
    public Mode mode = Mode.FOLLOW;
    public Side sidePreference;                // null = it picks
    public Emote emote;
    /** Set when the player pets it (sneak while looking at it); the game clears it after reacting. */
    public boolean petted;

    // ------------------------------------------------------------------ inner state
    private boolean placed;
    private final double[] px = new double[2], py = new double[2], pz = new double[2];
    private final double[] hyaw = new double[2], hpitch = new double[2];
    private final double[] pupX = new double[2], pupY = new double[2];
    private final double[] wanderAmp = {0.22, 0};
    private final double[] avoid = new double[2];
    private double emoteStart;
    private Side side = Side.RIGHT;
    private double nextSideSwitch = 30;
    private double stayX, stayY, stayZ, comeUntil;
    private double guideX, guideY, guideZ;
    /** While guiding: how far the target still is (horizontal) and how much higher (blocks). */
    public double guideDistance, guideRise;
    /** Set when you walk away from where she's leading; the game clears it after telling the brain. */
    public boolean wrongWay;
    private double wrongFor, nextWrongWay, closest = Double.MAX_VALUE;
    /** Your walking speed, measured from your eyes (blocks per second): she leads ahead of it. */
    private double pvx, pvz, lastEx = Double.NaN, lastEz;
    /** Set when a guided trip ends at the target; the game clears it after telling the brain. */
    public boolean arrived;
    static final double ARRIVE = 5;
    static final double GUIDE_AHEAD = 5.5;   // blocks ahead of you while leading
    static final double GUIDE_SMOOTH = 0.3;  // her spring while leading (snappier than following)
    static final double DT_GUESS = 1 / 20.0; // the guide check runs once per game tick
    /** How close she feels to you (0 = keeps far away, 1 = snuggles up); set from her bond. */
    public double closeness = 0.5;
    private final double[] distScale = {1, 0};
    /** 1 = here, 0 = gone (she vanished for a while); eased, so she puffs away and back. */
    public double presence = 1;
    private final double[] presenceState = {1, 0};
    private double hideUntil;
    private double visitX, visitY, visitZ, visitUntil;

    private GazeKind gaze = GazeKind.SHARED, pendingGaze;
    private double gx, gy, gz, pgx, pgy, pgz;  // POINT target, or DIRECTION as a unit vector
    private double switchAt = -1, glanceUntil, lookOverrideUntil = -1;
    private GazeKind lookOverride;
    private double sharedX, sharedY, sharedZ;

    private double lastActive, lastLookX, lastLookY, lastLookZ = 1;
    private double lookedAtSince = -1, notLookedSince, lastContactReaction = -100;
    private boolean contactReacted, wasSneaking, exploring, glancing, contactChosen;
    private double lastTurn = -100;
    private double exploreYaw;
    private double avoidLift;
    private final double[] slotYaw = {Double.NaN, 0};
    private boolean catchingUp;
    static final double TURN_SETTLED = 4;
    private Activity lastActivity = Activity.IDLE;
    private double hopPhase, nextBlink = 3, blinkLeft, nextSaccade, saccadeX, saccadeY;
    private double clock;

    public final Settings settings;

    public Behavior(double right, double up, double forward, double radius, long seed) {
        this(right, up, forward, radius, seed, new Settings());
    }

    public Behavior(double right, double up, double forward, double radius, long seed, Settings settings) {
        this.settings = settings;
        this.baseRight = right;
        this.baseUp = up;
        this.baseForward = forward;
        this.radius = radius;
        this.rng = new Random(seed);
    }

    // ================================================================== commands

    public void setMode(Mode m, double now) {
        setMode(m, now, 6);
    }

    /** @param seconds how long "come" lasts before it goes back to following */
    public void setMode(Mode m, double now, double seconds) {
        mode = m;
        if (m == Mode.STAY) {
            stayX = x;
            stayY = y;
            stayZ = z;
        } else if (m == Mode.COME) {
            comeUntil = now + seconds;
        }
        wake(now);
    }

    /**
     * How far she floats compared with normal, from how close she feels: 1 at a neutral 0.5,
     * down to 0.75 (snuggled up) when she adores you, up to 2.2 (keeping her distance) when hurt.
     */
    public static double distanceScale(double closeness) {
        double c = Smooth.clamp(closeness, 0, 1);
        return c >= 0.5 ? 1.0 - (c - 0.5) * 0.5 : 1.0 + (0.5 - c) * 2.4;
    }

    /** She leaves for a while (she was mistreated) and comes back by herself. */
    public void hide(double seconds, double now) {
        mode = Mode.HIDE;
        hideUntil = now + seconds;
    }

    /** Float over to something (an animal, a pet) for a few seconds and look at it. */
    public void visit(double x, double y, double z, double seconds, double now) {
        if (mode == Mode.HIDE) return;
        mode = Mode.VISIT;
        visitUntil = now + seconds;
        updateVisit(x, y, z);
    }

    /** The thing she's visiting moved. */
    public void updateVisit(double x, double y, double z) {
        visitX = x;
        visitY = y;
        visitZ = z;
        gx = x;
        gy = y + 0.6;
        gz = z;
    }

    public boolean hidden() {
        return mode == Mode.HIDE;
    }

    /** Lead the player to a place: it floats ahead, looks back, and celebrates on arrival. */
    public void guide(double x, double y, double z, double now) {
        guideX = x;
        guideY = y;
        guideZ = z;
        guideDistance = Double.MAX_VALUE;
        closest = Double.MAX_VALUE;
        mode = Mode.GUIDE;
        wake(now);
    }

    public double[] guideTarget() {
        return new double[]{guideX, guideY, guideZ};
    }

    /** The place she leads to moved (an animal walking): follow it without restarting the trip. */
    public void retarget(double x, double y, double z) {
        guideX = x;
        guideY = y;
        guideZ = z;
    }

    public void setSide(Side s) {
        sidePreference = s;
        if (s != null) side = s;
    }

    /** Look at the player, at what the player looks at, or in a direction, for a while. */
    public void lookAt(GazeKind kind, double dirX, double dirY, double dirZ, double seconds, double now) {
        lookOverride = kind;
        lookOverrideUntil = now + seconds;
        if (kind == GazeKind.DIRECTION) {
            double n = Math.sqrt(dirX * dirX + dirY * dirY + dirZ * dirZ);
            pgx = dirX / n;
            pgy = dirY / n;
            pgz = dirZ / n;
        }
        wake(now);
    }

    public void play(Emote e, double now) {
        if (emote == Emote.DOZE && e != Emote.DOZE) emote = null;
        emote = e;
        emoteStart = now;
    }

    public boolean dozing() {
        return emote == Emote.DOZE;
    }

    public GazeKind gaze() {
        return gaze;
    }

    private void wake(double now) {
        lastActive = now;
        if (emote == Emote.DOZE) play(Emote.STARTLE, now);
    }

    // ================================================================== decisions, 20 per second

    public void tick(Senses s, Activity act, Mood mood, Solid solid) {
        double now = s.now;

        // Are you active? Moving, or turning to look somewhere else.
        double lookDot = s.lx * lastLookX + s.ly * lastLookY + s.lz * lastLookZ;
        if (s.speed > 0.6 || lookDot < 0.985 || act != Activity.IDLE) lastActive = now;
        if (lookDot < 0.9995) lastTurn = now; // the player moved the view (more than ~2°)
        lastLookX = s.lx;
        lastLookY = s.ly;
        lastLookZ = s.lz;
        double idleFor = now - lastActive;
        boolean threatNear = nearestThreat(s) != null;

        // dozing off, and waking up softly
        if (emote == Emote.DOZE) {
            if (idleFor < 0.5 || threatNear || petted || settings.dozeAfterSeconds <= 0) play(Emote.STARTLE, now);
        } else if (settings.dozeAfterSeconds > 0 && idleFor > settings.dozeAfterSeconds && !threatNear
                && act == Activity.IDLE && mode != Mode.COME) {
            play(Emote.DOZE, now);
        }

        if (mode == Mode.COME && now > comeUntil) mode = Mode.FOLLOW;
        if (mode == Mode.VISIT && now > visitUntil) mode = Mode.FOLLOW;
        if (mode == Mode.HIDE && now > hideUntil) {
            mode = Mode.FOLLOW;
            play(Emote.SHY, now); // back, a little shy
        }
        if (mode == Mode.GUIDE) {
            double dx = guideX - s.ex, dz = guideZ - s.ez;
            guideDistance = Math.sqrt(dx * dx + dz * dz);
            guideRise = guideY - (s.ey - 1.62);
            if (guideDistance < ARRIVE) {
                mode = Mode.FOLLOW;
                arrived = true;
                wrongFor = 0;
                play(Emote.HAPPY, now);
            } else {
                // walking away from where she leads, for a couple of seconds: "this way!"
                double sp = Math.hypot(pvx, pvz);
                double along = sp > 1e-3 ? (pvx * dx + pvz * dz) / (sp * guideDistance) : 1;
                wrongFor = sp > 1.5 && along < -0.2 ? wrongFor + DT_GUESS : 0;
                closest = Math.min(closest, guideDistance);
                // walking away for a moment, or simply ended up well off the way (a wall stopped you)
                if ((wrongFor > 1.2 || guideDistance > closest + 5) && now > nextWrongWay) {
                    wrongWay = true;
                    nextWrongWay = now + 12;
                    closest = guideDistance;
                    play(Emote.HOP, now);
                }
            }
        }
        if (mode == Mode.STAY && dist2(stayX, stayY, stayZ, s.ex, s.ey, s.ez) > 64 * 64) mode = Mode.FOLLOW;

        // switch shoulders now and then, when nothing is going on
        if (settings.switchSides && sidePreference == null && now > nextSideSwitch && act == Activity.IDLE && !threatNear) {
            if (rng.nextDouble() < 0.5) side = side == Side.RIGHT ? Side.LEFT : Side.RIGHT;
            nextSideSwitch = now + 25 + rng.nextDouble() * 35;
        }
        boolean nowExploring = settings.wander && mode == Mode.FOLLOW && idleFor > 8 && act == Activity.IDLE && !threatNear;
        if (nowExploring && !exploring) exploreYaw = s.yawDeg;
        exploring = nowExploring;

        // gestures that come from feelings
        if (settings.moodGestures && act == Activity.THINKING && lastActivity != Activity.THINKING) play(Emote.THINK, now);
        if (settings.moodGestures && mood == Mood.EXCITED && emote == null && rng.nextDouble() < 0.012) play(Emote.HOP, now);
        lastActivity = act;

        // eye contact and petting
        boolean lookedAt = playerLooksAtMe(s);
        if (lookedAt) {
            if (lookedAtSince < 0) {
                lookedAtSince = now;
                // You turned toward it: that's eye contact you chose. If it drifted into your view
                // while you held still, it may glance back but must still get out of the way.
                contactChosen = now - lastTurn < 1.5;
            }
            notLookedSince = now;
        } else {
            lookedAtSince = -1;
            if (now - notLookedSince > 1.5) contactReacted = false;
        }
        double contact = lookedAtSince < 0 || !settings.lookBack ? 0 : now - lookedAtSince;
        if (settings.eyeContactReactions && contact > 1.3 && !contactReacted && now - lastContactReaction > 10 && emote == null && act == Activity.IDLE) {
            play(rng.nextDouble() < 0.6 ? Emote.HAPPY : Emote.SHY, now);
            contactReacted = true;
            lastContactReaction = now;
        }
        if (settings.petting && lookedAt && s.sneaking && !wasSneaking && dist2(x, y, z, s.ex, s.ey, s.ez) < 25) {
            petted = true;
            play(Emote.WIGGLE, now);
        }
        wasSneaking = s.sneaking;

        decideGaze(s, act, contact, now);
        avoidWalls(s, solid);
    }

    private void decideGaze(Senses s, Activity act, double contact, double now) {
        sharedX = s.hasLookHit ? s.hx : s.ex + s.lx * 8;
        sharedY = s.hasLookHit ? s.hy : s.ey + s.ly * 8;
        sharedZ = s.hasLookHit ? s.hz : s.ez + s.lz * 8;

        GazeKind want;
        double wx = 0, wy = 0, wz = 0;
        double delay = 0.12 + rng.nextDouble() * 0.23;
        double[] threat = settings.watchThreats ? nearestThreat(s) : null;
        if (mode == Mode.VISIT && threat == null) { // looking at what she's visiting
            gaze = GazeKind.POINT;
            gx = visitX;
            gy = visitY + 0.6;
            gz = visitZ;
            pendingGaze = null;
            return;
        }
        boolean urgent = now < lookOverrideUntil || threat != null || contact > 0.25
                || act != Activity.IDLE || mode == Mode.COME || mode == Mode.GUIDE;
        if (!urgent && glancing && now < glanceUntil) {
            commitPending(now); // keep looking at what caught its eye
            return;
        }
        glancing = !urgent;
        if (now < lookOverrideUntil) {
            want = lookOverride;
            wx = pgx;
            wy = pgy;
            wz = pgz;
            delay = 0.08;
        } else if (threat != null) {
            want = GazeKind.POINT;
            wx = threat[0];
            wy = threat[1] + 1.2;
            wz = threat[2];
            delay = 0.08 + rng.nextDouble() * 0.1;
        } else if (contact > 0.25 || act != Activity.IDLE || mode == Mode.COME || mode == Mode.GUIDE) {
            want = GazeKind.PLAYER;
        } else {
            double r = settings.glances ? rng.nextDouble() : 0; // no glances: shares your view
            double explore = exploring ? 0.25 : 0;
            if (r < 0.45 - explore) {
                want = GazeKind.SHARED;
                glanceUntil = now + 3 + rng.nextDouble() * 4;
            } else if (r < 0.62 - explore) {
                want = GazeKind.PLAYER;
                glanceUntil = now + 1.2 + rng.nextDouble() * 1.3;
            } else if (r < 0.85 && !s.interests.isEmpty()) {
                double[] it = s.interests.get(rng.nextInt(s.interests.size()));
                want = GazeKind.POINT;
                wx = it[0];
                wy = it[1] + 0.5;
                wz = it[2];
                glanceUntil = now + 1.5 + rng.nextDouble() * 2.5;
            } else {
                double yaw = -Math.toRadians(s.yawDeg) + (rng.nextDouble() - 0.5) * Math.PI;
                double pitch = -0.3 + rng.nextDouble() * 0.6;
                want = GazeKind.DIRECTION;
                wx = Math.sin(yaw) * Math.cos(pitch);
                wy = Math.sin(pitch);
                wz = Math.cos(yaw) * Math.cos(pitch);
                glanceUntil = now + 1.5 + rng.nextDouble() * 2;
            }
        }

        boolean same = want == gaze && (want == GazeKind.PLAYER || want == GazeKind.SHARED
                || dist2(wx, wy, wz, gx, gy, gz) < (want == GazeKind.POINT ? 1.5 * 1.5 : 0.04));
        if (same) {
            pendingGaze = null;
            if (want == GazeKind.POINT) { gx = wx; gy = wy; gz = wz; } // follow a moving mob smoothly
            return;
        }
        if (pendingGaze != want || dist2(wx, wy, wz, pgx, pgy, pgz) > 1) {
            pendingGaze = want;
            pgx = wx;
            pgy = wy;
            pgz = wz;
            switchAt = now + delay;
        }
        commitPending(now);
    }

    /** A decided change of gaze happens only after its reaction delay. */
    private void commitPending(double now) {
        if (now >= switchAt && pendingGaze != null) {
            gaze = pendingGaze;
            gx = pgx;
            gy = pgy;
            gz = pgz;
            pendingGaze = null;
        }
    }

    private double[] nearestThreat(Senses s) {
        for (double[] t : s.threats) {
            double d = Math.sqrt(dist2(t[0], t[1], t[2], s.ex, s.ey, s.ez));
            if (d < (t[3] > 0 ? 10 : 6)) return t;
        }
        return null;
    }

    /** Is the player's crosshair on the companion? A ray against a slightly generous sphere. */
    public boolean playerLooksAtMe(Senses s) {
        double dx = x - s.ex, dy = y - s.ey, dz = z - s.ez;
        double along = dx * s.lx + dy * s.ly + dz * s.lz;
        if (along <= 0.3 || along > 16) return false;
        double perp2 = dx * dx + dy * dy + dz * dz - along * along;
        double r = radius * 1.8 + 0.04 * along;
        return perp2 < r * r;
    }

    /**
     * A hit really aimed at her: the crosshair on her body (not the wide cone used for eye contact),
     * within arm's reach, and nothing nearer in the way (a mob, an animal or a block at distance
     * {@code inTheWay}; pass Double.MAX_VALUE when nothing is targeted).
     */
    public boolean aimedAt(Senses s, double inTheWay) {
        double dx = x - s.ex, dy = y - s.ey, dz = z - s.ez;
        double along = dx * s.lx + dy * s.ly + dz * s.lz;
        if (along <= 0.3 || along > 4.5 || inTheWay < along) return false;
        double perp2 = dx * dx + dy * dy + dz * dz - along * along;
        double r = radius * 1.15;
        return perp2 < r * r;
    }

    /** If its spot is inside a block, float up until it is free (and come back down later). */
    private void avoidWalls(Senses s, Solid solid) {
        if (solid == null || !placed) return;
        double yaw = Double.isNaN(slotYaw[0]) ? s.yawDeg : slotYaw[0];
        double[] t = target(s.ex, s.ey, s.ez, yaw, s.lx, s.ly, s.lz, s.now);
        if (solid.at(t[0], t[1] + avoidLift, t[2])) {
            avoidLift = Math.min(2.0, avoidLift + 0.5);
        } else if (avoidLift > 0 && !solid.at(t[0], t[1] + avoidLift - 0.5, t[2])) {
            avoidLift = Math.max(0, avoidLift - 0.25);
        }
    }

    // ================================================================== movement, every frame

    /** Where it wants to be right now (before springs), in world coordinates; yawDeg = the yaw its spot follows. */
    double[] target(double ex, double ey, double ez, double yawDeg, double lx, double ly, double lz, double now) {
        double tx, ty, tz;
        if (mode == Mode.STAY) {
            tx = stayX + Smooth.noise(now * 0.2, 7) * 0.08;
            ty = stayY + Smooth.noise(now * 0.25, 8) * 0.06;
            tz = stayZ + Smooth.noise(now * 0.2, 9) * 0.08;
            return new double[]{tx, ty, tz};
        }
        if (mode == Mode.VISIT) { // just above what she's visiting, on your side of it
            double dx = ex - visitX, dz = ez - visitZ, d = Math.max(0.01, Math.sqrt(dx * dx + dz * dz));
            return new double[]{visitX + dx / d * 0.7, visitY + 1.2 + Smooth.noise(now * 0.4, 14) * 0.08,
                    visitZ + dz / d * 0.7};
        }
        if (mode == Mode.HIDE) { // far behind you and up, while she's gone
            double yaw = Math.toRadians(yawDeg);
            return new double[]{ex + Math.sin(yaw) * 14, ey + 4, ez - Math.cos(yaw) * 14};
        }
        if (mode == Mode.GUIDE) {
            // well ahead on the way to the target, above head height so you see her over the grass,
            // and ahead of where you'll be: if you sprint, she goes faster, she never falls behind
            double dx = guideX - ex, dz = guideZ - ez, d = Math.sqrt(dx * dx + dz * dz);
            double ahead = Math.min(GUIDE_AHEAD, Math.max(0.8, d - 1));
            double ux = d > 1e-3 ? dx / d : 0, uz = d > 1e-3 ? dz / d : 1;
            double toward = Math.max(0, pvx * ux + pvz * uz); // your speed toward the target
            double lead = toward * GUIDE_SMOOTH * 1.3;
            return new double[]{ex + ux * (ahead + lead) + Smooth.noise(now * 0.3, 11) * 0.12,
                    ey + 0.7 + Smooth.noise(now * 0.35, 12) * 0.08,
                    ez + uz * (ahead + lead) + Smooth.noise(now * 0.3, 13) * 0.12};
        }
        double r, u, f;
        if (mode == Mode.COME) {
            r = 0;
            u = -0.25;
            f = 1.1;
        } else {
            switch (side) {
                case LEFT -> { r = -baseRight; u = baseUp; f = baseForward; }
                case ABOVE -> { r = 0.45; u = 0.4; f = 1.5; }
                default -> { r = baseRight; u = baseUp; f = baseForward; }
            }
            double amp = wanderAmp[0];
            amp *= Math.max(0, settings.drift);
            r *= distScale[0]; // closer when she feels close to you, further when she's hurt
            f *= Math.max(1, distScale[0] * 0.85);
            r += Smooth.noise(now * 0.13, 1) * amp;
            u += Smooth.noise(now * 0.17, 2) * amp * 0.45;
            f += Smooth.noise(now * 0.11, 3) * amp * 0.6;
        }
        double yaw = Math.toRadians(exploring ? exploreYaw : yawDeg);
        double fx = -Math.sin(yaw), fz = Math.cos(yaw), rx = -Math.cos(yaw), rz = -Math.sin(yaw);
        tx = ex + rx * r + fx * f;
        ty = ey + u;
        tz = ez + rz * r + fz * f;

        // never park in the middle of the view: slide sideways out of a 14° cone
        // (unless you are looking at it on purpose: then it stays for the eye contact)
        if (settings.keepOutOfView && mode == Mode.FOLLOW && !(lookedAtSince >= 0 && contactChosen)) {
            double dx = tx - ex, dy = ty - ey, dz = tz - ez;
            double along = dx * lx + dy * ly + dz * lz;
            if (along > 0 && along < 5) {
                double cx = dx - lx * along, cy = dy - ly * along, cz = dz - lz * along;
                double perp = Math.sqrt(cx * cx + cy * cy + cz * cz);
                double need = Math.tan(Math.toRadians(14)) * along;
                if (perp < need) {
                    double push = need - perp;
                    if (perp > 1e-3) { // outward, the way it already leans
                        tx += cx / perp * push;
                        ty += cy / perp * push;
                        tz += cz / perp * push;
                    } else {           // dead centre: toward its usual side
                        double sign = side == Side.LEFT ? -1 : 1;
                        tx += rx * sign * push;
                        tz += rz * sign * push;
                    }
                }
            }
        }
        return new double[]{tx, ty, tz};
    }

    public void frame(double ex, double ey, double ez, double yawDeg, double lx, double ly, double lz,
                      double now, double dt, Activity act, Mood mood, double voiceLevel, boolean floaty) {
        clock = now;
        if (dt > 0 && !Double.isNaN(lastEx)) { // your speed, smoothed (a teleport doesn't count)
            double ivx = (ex - lastEx) / dt, ivz = (ez - lastEz) / dt;
            if (ivx * ivx + ivz * ivz < 30 * 30) {
                double k = Math.min(1, dt / 0.25);
                pvx += (ivx - pvx) * k;
                pvz += (ivz - pvz) * k;
            }
        }
        lastEx = ex;
        lastEz = ez;
        // wander wider while you stand still, come close again when you move
        Smooth.damp(wanderAmp, exploring ? 1.6 : 0.22, exploring ? 3.0 : 0.8, dt, 2);
        Smooth.damp(distScale, distanceScale(closeness), 1.5, dt, 1);
        presence = Smooth.clamp(Smooth.damp(presenceState, mode == Mode.HIDE ? 0 : 1, 0.25, dt, 6), 0, 1);
        double[] t = target(ex, ey, ez, followYaw(yawDeg, dt), lx, ly, lz, now);
        t[1] += Smooth.damp(avoid, avoidLift, 0.4, dt, 4);

        if (!placed || dist2(t[0], t[1], t[2], x, y, z) > 14 * 14) {
            px[0] = t[0]; py[0] = t[1]; pz[0] = t[2];
            px[1] = py[1] = pz[1] = 0;
            placed = true;
        }
        double smooth = mode == Mode.GUIDE ? GUIDE_SMOOTH : mode == Mode.COME ? 0.35
                : (emote == Emote.DOZE || mood == Mood.SLEEPY) ? 0.9 : 0.5;
        x = Smooth.damp(px, t[0], smooth, dt, 14);
        y = Smooth.damp(py, t[1], smooth * 0.8, dt, 14);
        z = Smooth.damp(pz, t[2], smooth, dt, 14);

        // lean into the direction it moves, like something with weight
        double vx = px[1], vz = pz[1];
        double sp = Math.sqrt(vx * vx + vz * vz);
        leanAngle = Smooth.clamp(sp * 0.07, 0, 0.35);
        leanAxisX = sp > 1e-4 ? vz / sp : 0;
        leanAxisZ = sp > 1e-4 ? -vx / sp : 0;

        // head toward the gaze target; eyes get there first
        double[] g = gazePoint(ex, ey, ez);
        double dx = g[0] - x, dy = g[1] - y, dz = g[2] - z;
        double wantYaw = Math.atan2(dx, dz);
        double wantPitch = Smooth.clamp(Math.atan2(dy, Math.sqrt(dx * dx + dz * dz)), -0.6, 0.6);
        if (!Double.isFinite(wantYaw)) { wantYaw = headYaw; wantPitch = headPitch; }
        double headTime = emote == Emote.DOZE ? 0.8 : gaze == GazeKind.POINT && nearestIsThreat ? 0.15 : 0.28;
        headYaw = Smooth.dampAngle(hyaw, wantYaw, headTime, dt, 9);
        headPitch = Smooth.damp(hpitch, wantPitch, headTime, dt, 6);

        if (now > nextSaccade) { // tiny eye flicks: living eyes are never perfectly still
            saccadeX = (rng.nextDouble() - 0.5) * 0.24;
            saccadeY = (rng.nextDouble() - 0.5) * 0.16;
            nextSaccade = now + 0.5 + rng.nextDouble() * 0.9;
        }
        pose.reset();
        if (emote != null) {
            double et = now - emoteStart;
            emote.apply(et, pose);
            if (emote.seconds > 0 && et > emote.seconds) emote = null;
        }
        double wantPupX = Smooth.clamp(Math.sin(Smooth.wrap(wantYaw - headYaw)) / 0.55, -1, 1) + saccadeX + pose.pupilX;
        double wantPupY = Smooth.clamp((wantPitch - headPitch) / 0.45, -1, 1) + saccadeY + pose.pupilY;
        pupilX = Smooth.clamp(Smooth.damp(pupX, wantPupX, 0.06, dt, 30), -1, 1);
        pupilY = Smooth.clamp(Smooth.damp(pupY, wantPupY, 0.06, dt, 30), -1, 1);

        // its own little rhythm: hops when it is a slime, a slow float when it is a wisp
        double moveBoost = 1 + Smooth.clamp(sp / 4, 0, 1.5);
        double speed = mood.speed * (act == Activity.LISTENING ? 0.4 : 1) * moveBoost;
        hopPhase += dt * 1.1 * speed;
        double phase = hopPhase - Math.floor(hopPhase);
        double arc = Math.sin(Math.PI * phase);
        if (floaty) {
            lift = 0.06 * mood.height * Math.sin(hopPhase * Math.PI);
            squish = 0;
        } else {
            lift = 0.07 * mood.height * arc;
            squish = 0.16 * mood.height * Math.pow(1 - arc, 6);
        }
        if (act == Activity.LISTENING) squish -= 0.05; // stretches up, all ears

        // wings: flutter faster when it moves or is excited, slow when calm, folded when dozing
        boolean asleep = emote == Emote.DOZE;
        double beat = 2.4 * (1 + Smooth.clamp(sp / 3, 0, 1.5))
                * (mood == Mood.EXCITED || mood == Mood.SCARED ? 1.4 : mood == Mood.CALM || mood == Mood.SLEEPY ? 0.7 : 1);
        wingPhase += dt * beat * 2 * Math.PI;
        Smooth.damp(wingBase, asleep ? 1.25 : 0.45, 0.6, dt, 3);
        Smooth.damp(wingAmp, asleep ? 0.03 : 0.45, 0.6, dt, 3);
        wingAngle = wingBase[0] + wingAmp[0] * Math.sin(wingPhase);
        if (floaty && !asleep) lift += 0.012 * Math.sin(wingPhase); // rises a little on each beat
        shiver = mood == Mood.SCARED ? Math.sin(now * 55) * 0.012 : 0;

        if (now >= nextBlink) {
            blinkLeft = 0.12;
            nextBlink = now + 2.5 + rng.nextDouble() * 3.5;
        }
        blinkLeft = Math.max(0, blinkLeft - dt);
        double sleepy = mood == Mood.SLEEPY || mood == Mood.OFFLINE ? 0.55 : 0;
        blink = Smooth.clamp(Math.max(Math.max(sleepy, blinkLeft > 0 ? 1 : 0), pose.eyesClosed), 0, 1);
    }

    private boolean nearestIsThreat;

    /**
     * The direction its spot beside you follows. It stays put through small turns and while you
     * look at it; once you have turned more than {@link Settings#turnSlack} degrees away it glides
     * around to your side again, and settles before it will move again.
     */
    private double followYaw(double playerYaw, double dt) {
        if (exploring) return exploreYaw;
        double slack = settings.turnSlack;
        if (slack <= 0) { // glued to your side: its spot turns with you (the springs still smooth it)
            slotYaw[0] = playerYaw;
            slotYaw[1] = 0;
            return playerYaw;
        }
        if (Double.isNaN(slotYaw[0])) slotYaw[0] = playerYaw;
        double diff = Math.toDegrees(Smooth.wrap(Math.toRadians(playerYaw - slotYaw[0])));
        boolean watched = lookedAtSince >= 0 && contactChosen;
        if (!catchingUp && Math.abs(diff) > (watched ? Math.max(75, slack) : slack)) catchingUp = true;
        if (catchingUp && Math.abs(diff) < TURN_SETTLED) catchingUp = false;
        if (catchingUp) {
            double[] st = {Math.toRadians(slotYaw[0]), Math.toRadians(slotYaw[1])};
            Smooth.dampAngle(st, Math.toRadians(playerYaw), 0.45, dt, 8);
            slotYaw[0] = Math.toDegrees(st[0]);
            slotYaw[1] = Math.toDegrees(st[1]);
        } else {
            slotYaw[1] = 0;
        }
        return slotYaw[0];
    }

    private double[] gazePoint(double ex, double ey, double ez) {
        nearestIsThreat = false;
        return switch (gaze) {
            case PLAYER -> new double[]{ex, ey, ez};
            case SHARED -> new double[]{sharedX, sharedY, sharedZ};
            case POINT -> {
                nearestIsThreat = true;
                yield new double[]{gx, gy, gz};
            }
            case DIRECTION -> new double[]{x + gx * 6, y + gy * 6, z + gz * 6};
        };
    }

    private static double dist2(double ax, double ay, double az, double bx, double by, double bz) {
        double dx = ax - bx, dy = ay - by, dz = az - bz;
        return dx * dx + dy * dy + dz * dz;
    }
}
