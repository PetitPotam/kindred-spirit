package dev.kindredspirit.job;

import com.google.gson.JsonObject;
import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import dev.kindredspirit.craft.CraftPlanner;
import dev.kindredspirit.craft.GameRecipes;
import dev.kindredspirit.trade.TradeAdvice;
import dev.kindredspirit.trade.VillagerTrades;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.npc.AbstractVillager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Sandbox only: a {@code /pipjob} command to try the Phase 5 jobs, the crafting planner and trading
 * help in the dev client before they're wired into her actions (that wiring lands with the
 * playtest-fixes branch). Registered only when the game runs with {@code -Dkindredspirit.devScript},
 * as {@code ./gradlew runClient -PdevScript=...} does, so players never see it. Every answer is also
 * logged ("[pipjob] ...") for the scripts to check.
 *
 * <pre>
 *   /pipjob mine WHAT COUNT [magic]    /pipjob collect [magic]    /pipjob craft ITEM COUNT [magic]
 *   /pipjob plan ITEM COUNT            /pipjob trades             /pipjob status | stop
 * </pre>
 */
public final class JobsDev implements ClientModInitializer {
    private static final Logger LOG = LoggerFactory.getLogger("kindredspirit");

    @Override
    public void onInitializeClient() {
        if (System.getProperty("kindredspirit.devScript") == null) return;
        ServerTickEvents.END_SERVER_TICK.register(Jobs::tick);
        ServerTickEvents.END_SERVER_TICK.register(s -> {
            JsonObject done = Jobs.lastResult();
            if (done != null && done != reported) {
                reported = done;
                LOG.info("[pipjob] finished {}", done);
            }
        });
        CommandRegistrationCallback.EVENT.register((d, registries, env) -> d.register(Commands.literal("pipjob")
                .then(Commands.literal("mine").then(Commands.argument("what", StringArgumentType.word())
                        .then(Commands.argument("count", IntegerArgumentType.integer(1, 256))
                                .executes(c -> say(c, Jobs.mine(player(c), StringArgumentType.getString(c, "what"),
                                        IntegerArgumentType.getInteger(c, "count"), false)))
                                .then(Commands.literal("magic").executes(c -> say(c, Jobs.mine(player(c),
                                        StringArgumentType.getString(c, "what"), IntegerArgumentType.getInteger(c, "count"), true)))))))
                .then(Commands.literal("collect").executes(c -> say(c, Jobs.collect(player(c), false)))
                        .then(Commands.literal("magic").executes(c -> say(c, Jobs.collect(player(c), true)))))
                .then(Commands.literal("craft").then(Commands.argument("item", StringArgumentType.word())
                        .then(Commands.argument("count", IntegerArgumentType.integer(1, 576))
                                .executes(c -> say(c, Jobs.craft(player(c), StringArgumentType.getString(c, "item"),
                                        IntegerArgumentType.getInteger(c, "count"), false)))
                                .then(Commands.literal("magic").executes(c -> say(c, Jobs.craft(player(c),
                                        StringArgumentType.getString(c, "item"), IntegerArgumentType.getInteger(c, "count"), true)))))))
                .then(Commands.literal("plan").then(Commands.argument("item", StringArgumentType.word())
                        .then(Commands.argument("count", IntegerArgumentType.integer(1, 576)).executes(JobsDev::plan))))
                .then(Commands.literal("trades").executes(JobsDev::trades))
                .then(Commands.literal("status").executes(c -> say(c, Jobs.status())))
                .then(Commands.literal("stop").executes(c -> say(c, Jobs.stop())))));
    }

    private static JsonObject reported;

    private static ServerPlayer player(CommandContext<CommandSourceStack> c) throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        return c.getSource().getPlayerOrException();
    }

    private static int say(CommandContext<CommandSourceStack> c, JsonObject r) {
        LOG.info("[pipjob] {}", r);
        c.getSource().sendSuccess(() -> Component.literal(r.toString()), false);
        return 1;
    }

    private static int plan(CommandContext<CommandSourceStack> c) throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        ServerPlayer sp = player(c);
        String item = StringArgumentType.getString(c, "item");
        String id = item.contains(":") ? item : "minecraft:" + item;
        CraftPlanner planner = new CraftPlanner(GameRecipes.from(sp.getServer().getRecipeManager(), sp.getServer().registryAccess()));
        CraftPlanner.Plan p = planner.plan(id, IntegerArgumentType.getInteger(c, "count"), GameRecipes.pockets(sp));
        JsonObject r = new JsonObject();
        r.addProperty("canMakeNow", p.canMakeNow());
        r.addProperty("steps", p.steps().stream().map(s -> s.makes() + " " + s.recipe().result().replace("minecraft:", ""))
                .reduce((a, b) -> a + ", " + b).orElse(""));
        r.addProperty("missing", p.missing().toString());
        r.addProperty("stations", p.stations().toString());
        return say(c, r);
    }

    private static int trades(CommandContext<CommandSourceStack> c) throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        ServerPlayer sp = player(c);
        AbstractVillager v = VillagerTrades.nearest(sp, 8);
        JsonObject r = new JsonObject();
        if (v == null) {
            r.addProperty("error", "no villager within 8 blocks");
            return say(c, r);
        }
        int i = 0;
        for (TradeAdvice.Advice a : TradeAdvice.advise(VillagerTrades.who(v), VillagerTrades.offers(v), VillagerTrades.pockets(sp))) {
            r.addProperty("t" + i++, a.line());
        }
        return say(c, r);
    }
}
