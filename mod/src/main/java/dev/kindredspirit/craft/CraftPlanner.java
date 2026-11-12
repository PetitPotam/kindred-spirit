package dev.kindredspirit.craft;

import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

/**
 * "Can I make a piston? What am I missing?": the whole tree from what you have. Given the recipes, a
 * target and your inventory, it works out what to craft in which order (planks before sticks before
 * the pickaxe), what comes out of your pockets, and what you still need to gather, choosing among
 * alternatives the way that leaves the least to gather (birch planks when you have birch logs, not
 * oak). Leftovers are used: a stick recipe makes 4, a second need for sticks takes the spares.
 *
 * <p>That's the expertise half (Phase 4: exact answers with your own inventory, for the AI to say in
 * her words) and the job half (Phase 5: a grounded craft job carries the plan out with your items).
 * Plain Java; {@link GameRecipes} feeds it the game's own recipes, so modded ones work too.
 *
 * <p>Bounded: at most {@link #MAX_DEPTH} levels of ingredients, and a budget of tries, so odd recipe
 * loops (ingots and blocks, nuggets and ingots) and huge mod packs can't hang the game.
 */
public final class CraftPlanner {

    public static final int MAX_DEPTH = 8;
    static final int BUDGET = 50_000;

    /** One crafting step: use this recipe this many times, with these exact items. */
    public record Step(Recipe recipe, int times, Map<String, Integer> uses) {
        public int makes() {
            return times * recipe.count();
        }
    }

    /**
     * The answer. {@code missing} empty means you can make it now (given the stations); {@code after}
     * is your inventory once everything is crafted, so a job can carry it out as a difference.
     */
    public record Plan(String item, int count, List<Step> steps, Map<String, Integer> fromInventory,
                       Map<String, Integer> missing, Set<Recipe.Station> stations, Map<String, Integer> after) {
        public boolean canMakeNow() {
            return missing.isEmpty();
        }

        /** Smelting steps need fuel: one coal (or 8 items' worth of any fuel) per 8 items smelted. */
        public int smeltedItems() {
            return steps.stream().filter(s -> s.recipe().station() == Recipe.Station.FURNACE).mapToInt(Step::times).sum();
        }
    }

    private final Map<String, List<Recipe>> byResult = new HashMap<>();

    public CraftPlanner(Collection<Recipe> recipes) {
        for (Recipe r : recipes) byResult.computeIfAbsent(r.result(), k -> new ArrayList<>()).add(r);
    }

    public boolean knows(String item) {
        return byResult.containsKey(item);
    }

    public List<Recipe> recipesFor(String item) {
        return byResult.getOrDefault(item, List.of());
    }

    /** Plans {@code count} of {@code item} from {@code inventory} (item id → how many). Smelting allowed. */
    public Plan plan(String item, int count, Map<String, Integer> inventory) {
        return plan(item, count, inventory, true);
    }

    public Plan plan(String item, int count, Map<String, Integer> inventory, boolean smelting) {
        State s = new State(inventory);
        int[] budget = {BUDGET};
        // the target itself is crafted, not taken from your pockets ("make me a pickaxe" while holding one)
        craft(item, Math.max(1, count), s, 0, new HashSet<>(), smelting, budget);
        if (s.steps.stream().anyMatch(st -> st.recipe().result().equals(item))) s.inv.merge(item, Math.max(1, count), Integer::sum);
        Map<String, Integer> taken = new TreeMap<>();
        for (Map.Entry<String, Integer> e : s.taken.entrySet()) if (e.getValue() > 0) taken.put(e.getKey(), e.getValue());
        Set<Recipe.Station> stations = new HashSet<>();
        for (Step st : s.steps) stations.add(st.recipe().station());
        stations.remove(Recipe.Station.HAND);
        Map<String, Integer> after = new TreeMap<>();
        s.inv.forEach((k, v) -> { if (v > 0) after.put(k, v); });
        return new Plan(item, Math.max(1, count), merge(s.steps), taken, new TreeMap<>(s.missing), stations, after);
    }

    // --- the search --------------------------------------------------------------------------------

    private static final class State {
        Map<String, Integer> inv;
        Map<String, Integer> taken = new HashMap<>(); // out of the player's original pockets
        Map<String, Integer> missing = new HashMap<>();
        List<Step> steps = new ArrayList<>();
        /** this way needs the thing being made (iron ingots from an iron block, to make the block) */
        boolean loop;
        private final Map<String, Integer> original;

        State(Map<String, Integer> inventory) {
            this.original = inventory;
            this.inv = new HashMap<>(inventory);
        }

        State copy() {
            State c = new State(original);
            c.inv = new HashMap<>(inv);
            c.taken = new HashMap<>(taken);
            c.missing = new HashMap<>(missing);
            c.steps = new ArrayList<>(steps);
            c.loop = loop;
            return c;
        }

        void restore(State from) {
            inv = from.inv;
            taken = from.taken;
            missing = from.missing;
            steps = from.steps;
            loop = from.loop;
        }

        int missingTotal() {
            return missing.values().stream().mapToInt(Integer::intValue).sum();
        }

        /** Takes what's there of an item; what's taken counts as the player's own until their stock runs out. */
        int take(String item, int n) {
            int have = inv.getOrDefault(item, 0);
            int t = Math.min(have, n);
            if (t > 0) {
                inv.put(item, have - t);
                int ownLeft = original.getOrDefault(item, 0) - taken.getOrDefault(item, 0);
                int fromOwn = Math.min(t, Math.max(0, ownLeft));
                if (fromOwn > 0) taken.merge(item, fromOwn, Integer::sum);
            }
            return t;
        }
    }

    /** Gets {@code n} of an item: from what's there, else by crafting, else it's missing. */
    private void need(String item, int n, State s, int depth, Set<String> making, boolean smelting, int[] budget) {
        int got = s.take(item, n);
        int rest = n - got;
        if (rest > 0) craft(item, rest, s, depth, making, smelting, budget);
    }

    private void craft(String item, int n, State s, int depth, Set<String> making, boolean smelting, int[] budget) {
        List<Recipe> options = new ArrayList<>();
        for (Recipe r : byResult.getOrDefault(item, List.of())) {
            if (r.station() == Recipe.Station.FURNACE && !smelting) continue;
            options.add(r);
        }
        if (making.contains(item)) {
            s.loop = true;
            s.missing.merge(item, n, Integer::sum);
            return;
        }
        if (options.isEmpty() || depth >= MAX_DEPTH || --budget[0] < 0) {
            s.missing.merge(item, n, Integer::sum);
            return;
        }
        making.add(item);
        State best = null;
        for (Recipe r : options) {
            State trial = s.copy();
            apply(r, n, trial, depth, making, smelting, budget);
            if (best == null || better(trial, best)) best = trial;
            if (!best.loop && best.missingTotal() == s.missingTotal()) break; // nothing more to gather: good enough
        }
        making.remove(item);
        s.restore(best);
    }

    private static boolean better(State a, State b) {
        if (a.loop != b.loop) return !a.loop;
        if (a.missingTotal() != b.missingTotal()) return a.missingTotal() < b.missingTotal();
        return a.steps.size() < b.steps.size();
    }

    private void apply(Recipe r, int n, State s, int depth, Set<String> making, boolean smelting, int[] budget) {
        int times = (n + r.count() - 1) / r.count();
        // identical slots ("any planks" three times) are one need of 3 per craft
        Map<Set<String>, Integer> groups = new LinkedHashMap<>();
        for (Set<String> slot : r.slots()) groups.merge(slot, 1, Integer::sum);
        Map<String, Integer> uses = new TreeMap<>();
        for (Map.Entry<Set<String>, Integer> g : groups.entrySet()) {
            int amount = g.getValue() * times;
            if (g.getKey().size() > 1) { // mixing is fine: 1 oak and 2 birch planks make a pickaxe
                List<String> byStock = new ArrayList<>(g.getKey());
                byStock.sort((a, b) -> Integer.compare(s.inv.getOrDefault(b, 0), s.inv.getOrDefault(a, 0)));
                for (String alt : byStock) {
                    if (amount == 0) break;
                    int t = s.take(alt, amount);
                    if (t > 0) uses.merge(alt, t, Integer::sum);
                    amount -= t;
                }
            }
            if (amount > 0) {
                String choice = choose(g.getKey(), amount, s, depth, making, smelting, budget);
                need(choice, amount, s, depth + 1, making, smelting, budget);
                uses.merge(choice, amount, Integer::sum);
            }
        }
        s.steps.add(new Step(r, times, uses));
        s.inv.merge(r.result(), times * r.count() - n, Integer::sum); // spares
    }

    /** Of the items a slot accepts, the one that leaves the least to gather (what you have first). */
    private String choose(Set<String> alternatives, int amount, State s, int depth, Set<String> making,
                          boolean smelting, int[] budget) {
        List<String> sorted = new ArrayList<>(alternatives);
        sorted.sort((a, b) -> {
            int c = Integer.compare(s.inv.getOrDefault(b, 0), s.inv.getOrDefault(a, 0));
            return c != 0 ? c : a.compareTo(b);
        });
        if (sorted.size() == 1 || s.inv.getOrDefault(sorted.get(0), 0) >= amount) return sorted.get(0);
        String best = sorted.get(0);
        int bestMissing = Integer.MAX_VALUE;
        for (String alt : sorted) {
            State trial = s.copy();
            need(alt, amount, trial, depth + 1, making, smelting, budget);
            int m = trial.loop ? Integer.MAX_VALUE - 1 : trial.missingTotal();
            if (m < bestMissing) {
                bestMissing = m;
                best = alt;
                if (m == s.missingTotal()) break;
            }
        }
        return best;
    }

    /** The same recipe used in several places becomes one step (in the order first needed). */
    private static List<Step> merge(List<Step> steps) {
        Map<Recipe, Step> merged = new LinkedHashMap<>();
        for (Step st : steps) {
            merged.merge(st.recipe(), st, (a, b) -> {
                Map<String, Integer> u = new TreeMap<>(a.uses());
                b.uses().forEach((k, v) -> u.merge(k, v, Integer::sum));
                return new Step(a.recipe(), a.times() + b.times(), u);
            });
        }
        return List.copyOf(merged.values());
    }
}
