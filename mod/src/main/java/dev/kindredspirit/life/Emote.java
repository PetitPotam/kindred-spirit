package dev.kindredspirit.life;

import dev.kindredspirit.util.Smooth;

import java.util.Locale;

/**
 * Short gestures layered on top of the companion's idle life: a nod, a spin, a shy look away...
 * Each one is a little curve over time that adds to the pose, eased in and out, so it starts and
 * ends softly and blends with whatever the companion was doing.
 */
public enum Emote {
    NOD(1.0), SHAKE(1.1), SPIN(1.3), HOP(0.85), WIGGLE(1.2), HAPPY(1.5), SHY(2.4), THINK(2.6), STARTLE(0.7),
    /** A wink and a lopsided grin, a little sideways bob: "got you". */
    TEASE(1.7),
    /** Looping until something wakes it: eyes closed, slow breathing, sinking a little. */
    DOZE(-1);

    /** Seconds; negative = loops until stopped. */
    public final double seconds;

    Emote(double seconds) {
        this.seconds = seconds;
    }

    public static Emote parse(String s) {
        if (s == null) return null;
        try {
            return valueOf(s.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException e) {
            return null;
        }
    }

    /** What gestures add to the pose. Reset every frame, then each active gesture adds to it. */
    public static final class Pose {
        public double yaw, pitch, roll, lift, squish, scale = 1, eyesClosed, happyEyes, blush, eyeScale = 1, pupilX, pupilY;
        /** Face only: one eye shut (a wink), a lopsided grin (+ = her right corner up), eyes narrowed. */
        public double wink, smirk, squint;

        public void reset() {
            yaw = pitch = roll = lift = squish = eyesClosed = happyEyes = blush = pupilX = pupilY = wink = smirk = squint = 0;
            scale = eyeScale = 1;
        }
    }

    /** Adds this gesture at {@code t} seconds after it started. */
    public void apply(double t, Pose p) {
        double u = seconds > 0 ? Smooth.clamp(t / seconds, 0, 1) : 0;
        double fade = 1 - u;
        switch (this) {
            case NOD -> {
                double n = Math.sin(2 * Math.PI * 2 * u) * fade;
                p.pitch -= 0.35 * n;
                p.squish += 0.06 * Math.max(0, n);                                         // a little bounce on each "yes"
                p.happyEyes += 0.35 * Smooth.bump(u);
            }
            case SHAKE -> {
                p.yaw += 0.5 * Math.sin(2 * Math.PI * 2.5 * u) * fade;
                p.squint += 0.6 * Smooth.bump(u);                                          // "nope", eyes narrowed
            }
            case SPIN -> {
                // a wind-up the other way, a twirl that overshoots a hair and settles, giggling
                double wind = u < 0.18 ? Math.sin(Math.PI * u / 0.18) : 0;
                double a = Smooth.smoothstep(0.12, 0.92, u);
                p.yaw += 2 * Math.PI * a - 0.45 * wind + 0.12 * Math.sin(Math.PI * Smooth.clamp((u - 0.85) / 0.15, 0, 1));
                p.lift += 0.14 * Math.sin(Math.PI * a);
                p.squish += 0.12 * wind - 0.06 * Math.sin(Math.PI * a);
                p.happyEyes += Smooth.bump(u);
            }
            case HOP -> {
                if (u < 0.15) p.squish += 0.22 * Math.sin(Math.PI * u / 0.15);            // crouch
                else if (u < 0.9) {
                    double a = (u - 0.15) / 0.75;
                    p.lift += 0.45 * Math.sin(Math.PI * a);                                  // jump
                    p.squish -= 0.1 * Math.sin(Math.PI * a);                                 // stretch
                    p.happyEyes += Math.sin(Math.PI * a);                                    // ^ ^ in the air
                } else p.squish += 0.2 * Math.sin(Math.PI * (u - 0.9) / 0.1);              // land
            }
            case WIGGLE -> {
                p.roll += 0.3 * Math.sin(2 * Math.PI * 4 * u) * fade;
                p.squish += 0.08 * Math.sin(2 * Math.PI * 8 * u) * fade;
                p.happyEyes += 0.8 * Smooth.bump(u);
            }
            case HAPPY -> {
                double b = Smooth.bump(u);
                p.lift += 0.18 * Math.abs(Math.sin(2 * Math.PI * 1.5 * u)) * fade;
                p.roll += 0.08 * Math.sin(2 * Math.PI * 1.5 * u) * fade;                  // a little sway
                p.happyEyes += b;
                p.blush += b;
            }
            case SHY -> {
                double b = Smooth.bump(u);
                p.yaw += 0.7 * b;
                p.pitch -= 0.3 * b;
                p.blush += b;
                p.pupilX -= 0.6 * b;
                p.scale *= 1 - 0.08 * b;                                                    // makes herself small
            }
            case THINK -> {
                double b = Smooth.bump(u);
                p.pitch += 0.3 * b;
                p.roll += 0.2 * b;                                                          // the head tilt of "hmm"
                p.pupilX += 0.7 * b * Math.sin(u * 5);
                p.pupilY += 0.8 * b;
                p.smirk -= 0.5 * b;
            }
            case STARTLE -> {
                p.lift += 0.25 * Math.sin(Math.PI * Math.min(1, u / 0.5));
                p.scale *= 1 + 0.12 * Math.sin(Math.PI * u);
                p.eyeScale *= 1 + 0.35 * Math.sin(Math.PI * u);
                p.pitch -= 0.2 * Math.sin(Math.PI * u);                                     // jerks back
            }
            case TEASE -> {
                double b = Smooth.bump(u);
                p.wink += Smooth.clamp(b * 1.6, 0, 1);
                p.smirk += b;
                p.roll -= 0.22 * b;
                p.yaw += 0.25 * Math.sin(2 * Math.PI * 1.5 * u) * fade;                    // "nyeh"
                p.lift += 0.06 * Math.abs(Math.sin(2 * Math.PI * 1.5 * u)) * fade;
                p.blush += 0.4 * b;
            }
            case DOZE -> {
                double settle = Smooth.smoothstep(0, 2.5, t);  // closes its eyes slowly
                p.eyesClosed += settle;
                p.lift += (-0.12 + 0.025 * Math.sin(t * 1.3)) * settle;
                p.squish += 0.04 * Math.sin(t * 1.3) * settle;
                p.pitch -= 0.2 * settle;
            }
        }
    }
}
