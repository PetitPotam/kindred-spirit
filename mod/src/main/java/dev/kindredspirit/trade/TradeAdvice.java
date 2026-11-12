package dev.kindredspirit.trade;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * Trading help: what a villager offers, read against the player's pockets, as a few plain lines for
 * the AI to say in her words ("the farmer gives an emerald for 20 wheat; you could do that three
 * times"). Plain Java; {@link VillagerTrades} reads the real offers (prices already include the
 * villager's discounts for cured zombies, Hero of the Village and demand).
 *
 * <p>What she points out first: trades you can make right now that turn what you have into emeralds,
 * then the treasures (Mending and other prized enchanted books, diamond gear, bottles o' enchanting)
 * and what you can afford, and she says when a trade is sold out (it restocks when the villager works
 * at its job block).
 */
public final class TradeAdvice {
    private TradeAdvice() {}

    /** One offer. {@code costB} may be empty (count 0). {@code note}: an enchantment on the result, if any. */
    public record Offer(String costA, int countA, String costB, int countB, String result, int resultCount,
                        int uses, int maxUses, String note) {
        public boolean soldOut() {
            return uses >= maxUses;
        }

        public int stockLeft() {
            return Math.max(0, maxUses - uses);
        }

        /** You give something and get emeralds. */
        public boolean sellsToVillager() {
            return result.endsWith(":emerald") || result.equals("emerald");
        }
    }

    /** An offer with how often the player could make it now and why it matters. */
    public record Advice(Offer offer, int timesNow, boolean treasure, String line) {}

    static final Set<String> TREASURE_ITEMS = Set.of(
            "minecraft:diamond_sword", "minecraft:diamond_pickaxe", "minecraft:diamond_axe", "minecraft:diamond_shovel",
            "minecraft:diamond_helmet", "minecraft:diamond_chestplate", "minecraft:diamond_leggings",
            "minecraft:diamond_boots", "minecraft:experience_bottle", "minecraft:name_tag", "minecraft:ender_pearl",
            "minecraft:golden_carrot", "minecraft:glistering_melon_slice", "minecraft:totem_of_undying");

    static final Set<String> PRIZED_ENCHANTMENTS = Set.of("mending", "unbreaking", "efficiency", "fortune",
            "silk_touch", "protection", "sharpness", "looting", "feather_falling", "frost_walker", "depth_strider");

    /** All offers ranked, best first: makeable sells, then treasures, then the rest; sold-out last. */
    public static List<Advice> advise(String villager, List<Offer> offers, Map<String, Integer> pockets) {
        List<Advice> out = new ArrayList<>();
        for (Offer o : offers) {
            int times = o.soldOut() ? 0 : Math.min(o.stockLeft(), Math.min(
                    afford(pockets, o.costA(), o.countA()), o.countB() > 0 ? afford(pockets, o.costB(), o.countB()) : Integer.MAX_VALUE));
            boolean treasure = TREASURE_ITEMS.contains(o.result()) || prized(o.note());
            out.add(new Advice(o, times, treasure, line(villager, o, times, treasure)));
        }
        out.sort(Comparator.comparingInt((Advice a) -> rank(a)).thenComparing(a -> -a.timesNow()));
        return out;
    }

    private static int rank(Advice a) {
        if (a.offer().soldOut()) return 4;
        if (a.timesNow() > 0 && a.offer().sellsToVillager()) return 0;
        if (a.treasure()) return 1;
        if (a.timesNow() > 0) return 2;
        return 3;
    }

    private static int afford(Map<String, Integer> pockets, String item, int count) {
        if (count <= 0) return Integer.MAX_VALUE;
        return pockets.getOrDefault(item, 0) / count;
    }

    static boolean prized(String note) {
        if (note == null || note.isBlank()) return false;
        String n = note.toLowerCase(Locale.ROOT).replace(' ', '_');
        for (String e : PRIZED_ENCHANTMENTS) if (n.contains(e)) return true;
        return false;
    }

    /** "Farmer: 20 wheat → 1 emerald. You could do it 3 times (12 left)." */
    static String line(String villager, Offer o, int times, boolean treasure) {
        StringBuilder b = new StringBuilder();
        if (villager != null && !villager.isBlank()) b.append(villager).append(": ");
        b.append(o.countA()).append(' ').append(name(o.costA()));
        if (o.countB() > 0) b.append(" + ").append(o.countB()).append(' ').append(name(o.costB()));
        b.append(" → ").append(o.resultCount()).append(' ').append(name(o.result()));
        if (o.note() != null && !o.note().isBlank()) b.append(" (").append(o.note()).append(')');
        b.append('.');
        if (o.soldOut()) b.append(" Sold out until it works at its job block again.");
        else if (times > 0) b.append(" You could do it ").append(times == 1 ? "once" : times + " times")
                .append(" (").append(o.stockLeft()).append(" left).");
        else b.append(" You don't have enough for it.");
        if (treasure) b.append(" A good one.");
        return b.toString();
    }

    static String name(String id) {
        return id.substring(id.indexOf(':') + 1).replace('_', ' ');
    }
}
