package dev.kindredspirit.trade;

import net.minecraft.core.Holder;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.npc.AbstractVillager;
import net.minecraft.world.entity.npc.Villager;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.enchantment.Enchantment;
import net.minecraft.world.item.enchantment.ItemEnchantments;
import net.minecraft.world.item.trading.MerchantOffer;
import net.minecraft.world.phys.AABB;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Reads real villager trades on the world's game (server side: a client only sees offers while the
 * trading screen is open) for {@link TradeAdvice}. Prices are the villager's current ones for this
 * player ({@code getCostA} includes demand and discounts once the player's price was updated).
 */
public final class VillagerTrades {
    private VillagerTrades() {}

    /** The nearest villager or wandering trader within {@code range} blocks, or null. */
    public static AbstractVillager nearest(ServerPlayer sp, double range) {
        return sp.serverLevel().getEntitiesOfClass(AbstractVillager.class, new AABB(sp.blockPosition()).inflate(range),
                        v -> v.isAlive() && !v.isBaby())
                .stream().min(Comparator.comparingDouble(v -> v.distanceToSqr(sp))).orElse(null);
    }

    public static List<TradeAdvice.Offer> offers(AbstractVillager v) {
        List<TradeAdvice.Offer> out = new ArrayList<>();
        for (MerchantOffer o : v.getOffers()) {
            ItemStack a = o.getCostA(), b = o.getCostB(), r = o.getResult();
            out.add(new TradeAdvice.Offer(id(a), a.getCount(), b.isEmpty() ? "" : id(b), b.isEmpty() ? 0 : b.getCount(),
                    id(r), r.getCount(), o.getUses(), o.getMaxUses(), enchantments(r)));
        }
        return out;
    }

    /** "Librarian (expert)", "Wandering trader". */
    public static String who(AbstractVillager v) {
        if (v instanceof Villager villager) {
            String job = BuiltInRegistries.VILLAGER_PROFESSION.getKey(villager.getVillagerData().getProfession()).getPath();
            String[] levels = {"novice", "apprentice", "journeyman", "expert", "master"};
            int lvl = Math.max(1, Math.min(5, villager.getVillagerData().getLevel()));
            return (job.equals("none") ? "Villager" : cap(job.replace('_', ' '))) + " (" + levels[lvl - 1] + ")";
        }
        return "Wandering trader";
    }

    public static Map<String, Integer> pockets(ServerPlayer sp) {
        Map<String, Integer> n = new HashMap<>();
        for (ItemStack s : sp.getInventory().items) if (!s.isEmpty()) n.merge(id(s), s.getCount(), Integer::sum);
        return n;
    }

    private static String enchantments(ItemStack s) {
        ItemEnchantments e = s.getOrDefault(DataComponents.STORED_ENCHANTMENTS, ItemEnchantments.EMPTY);
        if (e.isEmpty()) e = s.getOrDefault(DataComponents.ENCHANTMENTS, ItemEnchantments.EMPTY);
        List<String> names = new ArrayList<>();
        for (var entry : e.entrySet()) {
            Holder<Enchantment> h = entry.getKey();
            String key = h.unwrapKey().map(k -> k.location().getPath()).orElse("?");
            names.add(key.replace('_', ' ') + " " + entry.getIntValue());
        }
        return String.join(", ", names);
    }

    private static String id(ItemStack s) {
        return BuiltInRegistries.ITEM.getKey(s.getItem()).toString();
    }

    private static String cap(String s) {
        return s.isEmpty() ? s : Character.toUpperCase(s.charAt(0)) + s.substring(1);
    }
}
