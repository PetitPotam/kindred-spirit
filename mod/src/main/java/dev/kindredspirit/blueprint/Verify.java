package dev.kindredspirit.blueprint;

import java.util.ArrayList;
import java.util.List;

/**
 * How much of a placed blueprint is really there: what's right, missing, wrong, and what's left to
 * do, like Litematica's verifier. Also the score for build tasks, the way MineCollab scores
 * construction (one minus the edit distance over the blueprint's size), so her building can be
 * measured in the sandbox. Plain Java over a block lookup.
 */
public final class Verify {
    private Verify() {}

    /** The block state at a world position ("minecraft:oak_stairs[facing=east,...]" or just a name). */
    public interface World {
        String state(int x, int y, int z);
    }

    /** {@code todo}: the steps still different from the blueprint, in build order. */
    public record Result(int total, int correct, int missing, int wrong, int notCleared, List<Placement.Step> todo) {
        /** 1 when it's all there, 0 when nothing is: MineCollab's 1 - edits / size. */
        public double score() {
            return total == 0 ? 1.0 : (double) correct / total;
        }
    }

    /**
     * @param strict compare properties too (stairs facing the right way); otherwise the block kind is enough
     * @param clearAir count the template's air (what should have been cleared)
     */
    public static Result check(Placement placement, World world, boolean strict, boolean clearAir) {
        int total = 0, correct = 0, missing = 0, wrong = 0, notCleared = 0;
        List<Placement.Step> todo = new ArrayList<>();
        for (Placement.Step s : placement.steps(clearAir)) {
            total++;
            BlockSpec there = parse(world.state(s.x(), s.y(), s.z()));
            boolean ok;
            if (s.kind() == Placement.Kind.CLEAR) {
                ok = there.isAir();
                if (!ok) notCleared++;
            } else if (there.isAir()) {
                ok = false;
                missing++;
            } else {
                ok = there.name().equals(s.state().name()) && (!strict || sameProperties(there, s.state()));
                if (!ok) wrong++;
            }
            if (ok) correct++;
            else todo.add(s);
        }
        return new Result(total, correct, missing, wrong, notCleared, todo);
    }

    private static boolean sameProperties(BlockSpec there, BlockSpec wanted) {
        // the world reports every property; the blueprint may leave some out (defaults)
        for (var e : wanted.properties().entrySet()) {
            if (!e.getValue().equals(there.get(e.getKey()))) return false;
        }
        return true;
    }

    private static BlockSpec parse(String s) {
        return s == null || s.isBlank() ? BlockSpec.AIR : BlockSpec.parse(s);
    }
}
