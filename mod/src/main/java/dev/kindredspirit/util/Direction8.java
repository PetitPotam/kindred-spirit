package dev.kindredspirit.util;

/** Turns "where is that mob compared to where I'm looking" into words the brain can say. */
public final class Direction8 {
    private Direction8() {}

    /**
     * @param yawDeg the player's yaw in Minecraft degrees (0 = facing south/+Z, 90 = facing west/-X)
     * @param dx     target x minus player x
     * @param dz     target z minus player z
     * @return "ahead", "ahead-right", "right", "behind-right", "behind", "behind-left", "left" or "ahead-left"
     */
    public static String relative(float yawDeg, double dx, double dz) {
        if (dx * dx + dz * dz < 1e-6) return "here";
        double yaw = Math.toRadians(yawDeg);
        double fx = -Math.sin(yaw), fz = Math.cos(yaw);   // forward
        double rx = -Math.cos(yaw), rz = -Math.sin(yaw);  // right-hand side
        double ahead = dx * fx + dz * fz, right = dx * rx + dz * rz;
        double angle = Math.toDegrees(Math.atan2(right, ahead)); // 0 ahead, +90 right, ±180 behind
        String[] names = {"ahead", "ahead-right", "right", "behind-right", "behind", "behind-left", "left", "ahead-left"};
        int idx = Math.floorMod(Math.round(angle / 45.0), 8);
        return names[idx];
    }

    /** The same direction as an arrow on screen: ↑ ahead, → right, ↓ behind... */
    public static String arrow(float yawDeg, double dx, double dz) {
        return switch (relative(yawDeg, dx, dz)) {
            case "ahead-right" -> "\u2197";
            case "right" -> "\u2192";
            case "behind-right" -> "\u2198";
            case "behind" -> "\u2193";
            case "behind-left" -> "\u2199";
            case "left" -> "\u2190";
            case "ahead-left" -> "\u2196";
            default -> "\u2191";
        };
    }
}
