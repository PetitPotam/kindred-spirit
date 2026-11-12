package dev.kindredspirit.craft;

import net.minecraft.core.RegistryAccess;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.crafting.AbstractCookingRecipe;
import net.minecraft.world.item.crafting.CraftingRecipe;
import net.minecraft.world.item.crafting.Ingredient;
import net.minecraft.world.item.crafting.RecipeHolder;
import net.minecraft.world.item.crafting.RecipeManager;
import net.minecraft.world.item.crafting.RecipeType;
import net.minecraft.world.item.crafting.ShapedRecipe;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * The game's own recipes (vanilla, data packs, mods) as {@link Recipe}s, the player's pockets as counts,
 * and carrying out a plan with real items. Built once per world from the server's RecipeManager (a few
 * thousand recipes, milliseconds) and rebuilt when data packs reload.
 *
 * <p>Special recipes (fireworks, map copying, banner patterns, armor dyeing) have no fixed ingredients
 * and are left out; she can still talk about them from the knowledge base.
 */
public final class GameRecipes {
    private GameRecipes() {}

    public static List<Recipe> from(RecipeManager manager, RegistryAccess registries) {
        List<Recipe> out = new ArrayList<>();
        for (RecipeHolder<CraftingRecipe> h : manager.getAllRecipesFor(RecipeType.CRAFTING)) {
            CraftingRecipe r = h.value();
            if (r.isSpecial()) continue;
            ItemStack result = r.getResultItem(registries);
            if (result.isEmpty()) continue;
            List<Set<String>> slots = slots(r.getIngredients());
            if (slots.isEmpty()) continue;
            boolean big = r instanceof ShapedRecipe s ? s.getWidth() > 2 || s.getHeight() > 2 : slots.size() > 4;
            out.add(new Recipe(id(result.getItem()), result.getCount(), slots,
                    big ? Recipe.Station.CRAFTING_TABLE : Recipe.Station.HAND));
        }
        for (RecipeHolder<?> h : manager.getAllRecipesFor(RecipeType.SMELTING)) {
            if (!(h.value() instanceof AbstractCookingRecipe r)) continue;
            ItemStack result = r.getResultItem(registries);
            List<Set<String>> slots = slots(r.getIngredients());
            if (result.isEmpty() || slots.size() != 1) continue;
            out.add(new Recipe(id(result.getItem()), result.getCount(), slots, Recipe.Station.FURNACE));
        }
        return out;
    }

    private static List<Set<String>> slots(List<Ingredient> ingredients) {
        List<Set<String>> slots = new ArrayList<>();
        for (Ingredient ing : ingredients) {
            if (ing.isEmpty()) continue; // a gap in a shaped grid
            Set<String> alts = new LinkedHashSet<>();
            for (ItemStack s : ing.getItems()) alts.add(id(s.getItem()));
            if (!alts.isEmpty()) slots.add(alts);
        }
        return slots;
    }

    /** What's in the player's main inventory, offhand and armor slots excluded: item id → count. */
    public static Map<String, Integer> pockets(ServerPlayer sp) {
        Map<String, Integer> n = new HashMap<>();
        for (ItemStack s : sp.getInventory().items) {
            if (!s.isEmpty() && !s.isDamaged() && !s.isEnchanted()) n.merge(id(s.getItem()), s.getCount(), Integer::sum);
        }
        return n;
    }

    /**
     * Grounded crafting: takes what the plan uses out of the player's pockets and puts what it makes in
     * (what doesn't fit drops at their feet). Re-plans from the pockets as they are now, so a plan made
     * a moment ago can't take what's gone. Damaged or enchanted items are never used up.
     *
     * @return the plan carried out, or the fresh plan with what's missing (nothing changed)
     */
    public static CraftPlanner.Plan carryOut(ServerPlayer sp, CraftPlanner planner, String item, int count) {
        Map<String, Integer> before = pockets(sp);
        CraftPlanner.Plan plan = planner.plan(item, count, before);
        if (!plan.canMakeNow()) return plan;
        Map<String, Integer> delta = new HashMap<>();
        before.forEach((k, v) -> delta.merge(k, -v, Integer::sum));
        plan.after().forEach((k, v) -> delta.merge(k, v, Integer::sum));
        for (Map.Entry<String, Integer> e : delta.entrySet()) {
            if (e.getValue() < 0) remove(sp, item(e.getKey()), -e.getValue());
        }
        for (Map.Entry<String, Integer> e : delta.entrySet()) {
            if (e.getValue() > 0) give(sp, item(e.getKey()), e.getValue());
        }
        return plan;
    }

    private static void remove(ServerPlayer sp, Item it, int n) {
        for (ItemStack s : sp.getInventory().items) {
            if (n <= 0) return;
            if (s.is(it) && !s.isDamaged() && !s.isEnchanted()) {
                int t = Math.min(n, s.getCount());
                s.shrink(t);
                n -= t;
            }
        }
    }

    private static void give(ServerPlayer sp, Item it, int n) {
        while (n > 0) {
            int t = Math.min(n, it.getDefaultMaxStackSize());
            ItemStack stack = new ItemStack(it, t);
            if (!sp.getInventory().add(stack)) sp.drop(stack, false);
            n -= t;
        }
    }

    static String id(Item it) {
        return BuiltInRegistries.ITEM.getKey(it).toString();
    }

    static Item item(String id) {
        return BuiltInRegistries.ITEM.get(ResourceLocation.parse(id));
    }
}
