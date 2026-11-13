package dev.kindredspirit.craft;

import dev.kindredspirit.util.Mc;
import net.minecraft.core.RegistryAccess;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.crafting.RecipeHolder;
import net.minecraft.world.item.crafting.RecipeManager;
import net.minecraft.world.item.crafting.RecipeType;
//? if >=26.1 {
import net.minecraft.util.context.ContextMap;
import net.minecraft.world.item.crafting.display.FurnaceRecipeDisplay;
import net.minecraft.world.item.crafting.display.RecipeDisplay;
import net.minecraft.world.item.crafting.display.ShapedCraftingRecipeDisplay;
import net.minecraft.world.item.crafting.display.ShapelessCraftingRecipeDisplay;
import net.minecraft.world.item.crafting.display.SlotDisplay;
import net.minecraft.world.item.crafting.display.SlotDisplayContext;
//?} else {
/*import net.minecraft.world.item.crafting.AbstractCookingRecipe;
import net.minecraft.world.item.crafting.CraftingRecipe;
import net.minecraft.world.item.crafting.Ingredient;
import net.minecraft.world.item.crafting.ShapedRecipe;
*///?}

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
        //? if >=26.1 {
        // Since 1.21.2 a recipe's items are read through its displays, the way the recipe book shows them.
        ContextMap ctx = ContextMap.builder().set(SlotDisplayContext.REGISTRIES, registries).buildAndValidate(SlotDisplayContext.CONTEXT);
        for (RecipeHolder<?> h : manager.getRecipes()) {
            var r = h.value();
            if (r.isSpecial()) continue;
            boolean crafting = r.getType() == RecipeType.CRAFTING, smelting = r.getType() == RecipeType.SMELTING;
            if (!crafting && !smelting) continue;
            for (RecipeDisplay d : r.display()) {
                if (crafting && d instanceof ShapedCraftingRecipeDisplay s) {
                    add(out, s.result().resolveForFirstStack(ctx), slots(s.ingredients(), ctx),
                            s.width() > 2 || s.height() > 2 ? Recipe.Station.CRAFTING_TABLE : Recipe.Station.HAND);
                } else if (crafting && d instanceof ShapelessCraftingRecipeDisplay s) {
                    List<Set<String>> slots = slots(s.ingredients(), ctx);
                    add(out, s.result().resolveForFirstStack(ctx), slots, slots.size() > 4 ? Recipe.Station.CRAFTING_TABLE : Recipe.Station.HAND);
                } else if (smelting && d instanceof FurnaceRecipeDisplay f) {
                    List<Set<String>> slots = slots(List.of(f.ingredient()), ctx);
                    if (slots.size() == 1) add(out, f.result().resolveForFirstStack(ctx), slots, Recipe.Station.FURNACE);
                }
            }
        }
        //?} else {
        /*for (RecipeHolder<CraftingRecipe> h : manager.getAllRecipesFor(RecipeType.CRAFTING)) {
            CraftingRecipe r = h.value();
            if (r.isSpecial()) continue;
            List<Set<String>> slots = slots(r.getIngredients());
            boolean big = r instanceof ShapedRecipe s ? s.getWidth() > 2 || s.getHeight() > 2 : slots.size() > 4;
            add(out, r.getResultItem(registries), slots, big ? Recipe.Station.CRAFTING_TABLE : Recipe.Station.HAND);
        }
        for (RecipeHolder<?> h : manager.getAllRecipesFor(RecipeType.SMELTING)) {
            if (!(h.value() instanceof AbstractCookingRecipe r)) continue;
            List<Set<String>> slots = slots(r.getIngredients());
            if (slots.size() == 1) add(out, r.getResultItem(registries), slots, Recipe.Station.FURNACE);
        }
        *///?}
        return out;
    }

    private static void add(List<Recipe> out, ItemStack result, List<Set<String>> slots, Recipe.Station station) {
        if (result.isEmpty() || slots.isEmpty()) return;
        out.add(new Recipe(id(result.getItem()), result.getCount(), slots, station));
    }

    //? if >=26.1 {
    private static List<Set<String>> slots(List<SlotDisplay> ingredients, ContextMap ctx) {
        List<Set<String>> slots = new ArrayList<>();
        for (SlotDisplay ing : ingredients) {
            Set<String> alts = new LinkedHashSet<>();
            for (ItemStack s : ing.resolveForStacks(ctx)) if (!s.isEmpty()) alts.add(id(s.getItem()));
            if (!alts.isEmpty()) slots.add(alts); // (an empty one is a gap in a shaped grid)
        }
        return slots;
    }
    //?} else {
    /*private static List<Set<String>> slots(List<Ingredient> ingredients) {
        List<Set<String>> slots = new ArrayList<>();
        for (Ingredient ing : ingredients) {
            if (ing.isEmpty()) continue; // a gap in a shaped grid
            Set<String> alts = new LinkedHashSet<>();
            for (ItemStack s : ing.getItems()) alts.add(id(s.getItem()));
            if (!alts.isEmpty()) slots.add(alts);
        }
        return slots;
    }
    *///?}

    /** What's in the player's main inventory, offhand and armor slots excluded: item id → count. */
    public static Map<String, Integer> pockets(ServerPlayer sp) {
        Map<String, Integer> n = new HashMap<>();
        for (ItemStack s : Mc.items(sp)) {
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
        for (ItemStack s : Mc.items(sp)) {
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
            Mc.give(sp, stack);
            n -= t;
        }
    }

    static String id(Item it) {
        return BuiltInRegistries.ITEM.getKey(it).toString();
    }

    static Item item(String id) {
        return Mc.item(Identifier.parse(id));
    }
}
