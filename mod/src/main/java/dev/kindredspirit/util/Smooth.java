package dev.kindredspirit.util;

/**
 * The math that keeps the companion from feeling robotic: nothing it does jumps or stops dead.
 * <ul>
 *   <li>{@link #damp} is a critically damped spring (the "SmoothDamp" game developers use): it
 *       eases toward a target that may itself be moving, never overshoots, and keeps its velocity
 *       when the target changes mid-way, so a change of mind curves instead of snapping.</li>
 *   <li>{@link #noise} is smooth random wandering (value noise), for drifting and fidgeting that
 *       never repeats in an obvious loop.</li>
 *   <li>{@link #smoothstep}, {@link #bump}: easing curves for gestures.</li>
 * </ul>
 */
public final class Smooth {
    private Smooth() {}

    /**
     * One step of a critically damped spring toward {@code target}.
     *
     * @param state      {value, velocity}; updated in place
     * @param smoothTime roughly the time (seconds) to get most of the way there
     * @param maxSpeed   speed limit (units per second)
     * @return the new value
     */
    public static double damp(double[] state, double target, double smoothTime, double dt, double maxSpeed) {
        if (dt <= 0) return state[0];
        smoothTime = Math.max(1e-4, smoothTime);
        double omega = 2.0 / smoothTime;
        double x = omega * dt;
        double exp = 1.0 / (1.0 + x + 0.48 * x * x + 0.235 * x * x * x);
        double current = state[0], velocity = state[1];
        double change = current - target;
        double originalTo = target;
        double maxChange = maxSpeed * smoothTime;
        change = Math.max(-maxChange, Math.min(maxChange, change));
        target = current - change;
        double temp = (velocity + omega * change) * dt;
        velocity = (velocity - omega * temp) * exp;
        double out = target + (change + temp) * exp;
        if ((originalTo - current > 0) == (out > originalTo)) { // would overshoot: land exactly
            out = originalTo;
            velocity = (out - originalTo) / dt;
        }
        state[0] = out;
        state[1] = velocity;
        return out;
    }

    /** Same as {@link #damp} for an angle in radians: always turns the short way round. */
    public static double dampAngle(double[] state, double target, double smoothTime, double dt, double maxSpeed) {
        double t = state[0] + wrap(target - state[0]);
        return damp(state, t, smoothTime, dt, maxSpeed);
    }

    /** Wraps an angle to -PI..PI. */
    public static double wrap(double a) {
        a = (a + Math.PI) % (2 * Math.PI);
        if (a < 0) a += 2 * Math.PI;
        return a - Math.PI;
    }

    /** Smooth random value in -1..1 that changes gently with {@code x}; each seed is its own stream. */
    public static double noise(double x, int seed) {
        double base = value(x, seed) * 0.65 + value(x * 2.13 + 17.3, seed + 101) * 0.35;
        return base;
    }

    private static double value(double x, int seed) {
        long i = (long) Math.floor(x);
        double f = x - i;
        double u = f * f * (3 - 2 * f);
        return lerp(hash(i, seed), hash(i + 1, seed), u) * 2 - 1;
    }

    private static double hash(long i, int seed) {
        long h = i * 374761393L + seed * 668265263L;
        h = (h ^ (h >>> 13)) * 1274126177L;
        h ^= (h >>> 16);
        return (h & 0xFFFFFF) / (double) 0xFFFFFF;
    }

    public static double lerp(double a, double b, double t) {
        return a + (b - a) * t;
    }

    public static double clamp(double v, double lo, double hi) {
        return Math.max(lo, Math.min(hi, v));
    }

    public static double smoothstep(double edge0, double edge1, double x) {
        double t = clamp((x - edge0) / (edge1 - edge0), 0, 1);
        return t * t * (3 - 2 * t);
    }

    /** 0 -> eases up to 1 over the first 20%, holds, eases back to 0 over the last 20%. */
    public static double bump(double u) {
        return smoothstep(0, 0.2, u) * (1 - smoothstep(0.8, 1, u));
    }
}
