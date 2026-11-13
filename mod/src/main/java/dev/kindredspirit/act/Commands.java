package dev.kindredspirit.act;

import dev.kindredspirit.util.Mc;
import com.google.gson.JsonObject;
import net.minecraft.ChatFormatting;
import net.minecraft.commands.CommandSource;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Minecraft's own commands as her powers (magic style): the world's game runs them for her, as the
 * player who asked, from where they stand, and she gets the game's exact answer back. Instant
 * building (/fill, /setblock, /clone), gifts (/give, /enchant), effects, mobs, the time, the weather,
 * particles and sounds.
 *
 * <p>Only an allowlist, by power: helper gets the harmless ones and building; all-powerful gets the
 * world-changing ones. Never @e, @a or @r; nothing more than 96 blocks from the player; no lethal or
 * harmful effects unless the player asked for that very effect (and then short); no dangerous mobs;
 * at most a few mobs at a time. Every command is written to the game log.
 */
public final class Commands {
    private Commands() {}

    private static final org.slf4j.Logger LOG = org.slf4j.LoggerFactory.getLogger("kindredspirit");

    /** Harmless: anyone with magic (helper or all-powerful). */
    static final Set<String> HELPER = Set.of("particle", "playsound", "locate", "fill", "setblock", "clone", "give",
            "enchant", "effect", "item");
    /** World-changing: all-powerful only. */
    static final Set<String> ALL = Set.of("summon", "tp", "teleport", "time", "weather", "spawnpoint", "xp", "experience");
    static final Set<String> HARMFUL = Set.of("poison", "wither", "blindness", "nausea", "hunger", "weakness",
            "darkness", "mining_fatigue", "slowness", "levitation", "bad_omen", "unluck", "instant_damage");
    static final Set<String> NEVER_EFFECTS = Set.of("instant_damage");
    static final Set<String> NEVER_MOBS = Set.of("wither", "ender_dragon", "warden", "elder_guardian", "tnt",
            "tnt_minecart", "end_crystal", "lightning_bolt", "ravager", "evoker");
    static final int MAX_DISTANCE = 96;
    private static final List<Long> summoned = new ArrayList<>();

    /** Why this command isn't allowed, or null. harmfulAsked: the player named a harmful effect themselves. */
    public static String check(String command, Abilities.Power power, double px, double py, double pz, boolean harmfulAsked) {
        String c = command.trim();
        if (c.startsWith("/")) c = c.substring(1);
        String[] w = c.split("\\s+");
        String name = w.length == 0 ? "" : w[0].toLowerCase(Locale.ROOT).replace("minecraft:", "");
        boolean all = power == Abilities.Power.ALLPOWERFUL;
        if (!HELPER.contains(name) && !(all && ALL.contains(name))) {
            return ALL.contains(name) ? "/" + name + " needs her all-powerful setting."
                    : "/" + name + " isn't one of her commands (she can: " + String.join(", ", all ? union() : HELPER) + ").";
        }
        if (c.contains("@e") || c.contains("@a") || c.contains("@r") || c.contains("@n")) {
            return "Never @e, @a, @r or @n: name the player, or @s.";
        }
        if (c.contains("run ") || c.contains("execute")) return "No nested commands.";
        // coordinates: three in a row; relative (~, ^) offsets and absolute ones must stay near the player
        double[] p = {px, py, pz};
        int axis = 0;
        for (String t : w) {
            if (!t.matches("[~^]?-?\\d*(\\.\\d+)?") || t.isEmpty() || t.equals("-")) {
                axis = 0;
                continue;
            }
            boolean rel = t.startsWith("~") || t.startsWith("^");
            String n = rel ? t.substring(1) : t;
            double v = n.isEmpty() || n.equals("-") ? 0 : Double.parseDouble(n);
            double off = rel ? Math.abs(v) : Math.abs(v - p[axis % 3]);
            if (off > MAX_DISTANCE && !(name.equals("time") || name.equals("weather") || name.equals("give")
                    || name.equals("enchant") || name.equals("effect") || name.equals("particle") || name.equals("playsound"))) {
                return "That's too far from the player (" + Math.round(off) + " blocks): she only works within " + MAX_DISTANCE + ".";
            }
            axis++;
        }
        if (name.equals("effect") && w.length > 3 && w[1].equals("give")) {
            String effect = w[3].toLowerCase(Locale.ROOT).replace("minecraft:", "");
            if (NEVER_EFFECTS.contains(effect)) return "Never that one: it would hurt them for real.";
            if (HARMFUL.contains(effect) && !harmfulAsked) return "Only if they asked for " + effect.replace('_', ' ') + " themselves.";
            if (HARMFUL.contains(effect)) {
                int secs = w.length > 4 && w[4].matches("\\d+") ? Integer.parseInt(w[4]) : 30;
                int amp = w.length > 5 && w[5].matches("\\d+") ? Integer.parseInt(w[5]) : 0;
                // for themselves, as they asked ("levitation for five minutes"): up to 5 minutes; on others, a prank
                boolean self = w[2].equals("@s") || w[2].equals("@p");
                if (self && (secs > 300 || amp > 1)) return "At most 5 minutes, level 1 (" + effect + " " + secs + " " + amp + ").";
                if (!self && (secs > 10 || amp > 0)) return "A playful one only: at most 10 seconds, level 0 (" + effect + " " + secs + " " + amp + ").";
            }
        }
        if (name.equals("summon") && w.length > 1) {
            String mob = w[1].toLowerCase(Locale.ROOT).replace("minecraft:", "");
            if (NEVER_MOBS.contains(mob)) return "Not a " + mob.replace('_', ' ') + ": too dangerous.";
            long now = System.currentTimeMillis();
            summoned.removeIf(t -> now - t > 60000);
            if (summoned.size() >= 5) return "Enough mobs for now (5 a minute).";
            summoned.add(now);
        }
        if ((name.equals("tp") || name.equals("teleport")) && w.length > 4) {
            return "Teleport someone to a place near here, or to a player: /tp <who> <x y z> or /tp <who> <player>.";
        }
        return null;
    }

    private static List<String> union() {
        List<String> u = new ArrayList<>(HELPER);
        u.addAll(ALL);
        return u;
    }

    /** Runs it as the player (permission 2, from where they stand) and returns what the game answered. */
    public static JsonObject run(MinecraftServer server, ServerPlayer sp, String command, Abilities.Power power, boolean harmfulAsked) {
        String c = command.trim().startsWith("/") ? command.trim().substring(1) : command.trim();
        String why = check(c, power, sp.getX(), sp.getY(), sp.getZ(), harmfulAsked);
        if (why != null) {
            LOG.info("command refused for {}: /{} ({})", sp.getGameProfile().name(), c, why);
            return Actions.error(why);
        }
        List<String> said = new ArrayList<>();
        boolean[] failed = {false};
        CommandSource out = new CommandSource() {
            @Override
            public void sendSystemMessage(Component message) {
                said.add(message.getString());
                if (message.getStyle().getColor() != null
                        && message.getStyle().getColor().equals(net.minecraft.network.chat.TextColor.fromLegacyFormat(ChatFormatting.RED))) {
                    failed[0] = true;
                }
            }

            @Override
            public boolean acceptsSuccess() {
                return true;
            }

            @Override
            public boolean acceptsFailure() {
                return true;
            }

            @Override
            public boolean shouldInformAdmins() {
                return false;
            }
        };
        CommandSourceStack src = Mc.commandSource(sp, out);
        server.getCommands().performPrefixedCommand(src, c);
        String answer = String.join(" | ", said);
        LOG.info("command for {}: /{} -> {}", sp.getGameProfile().name(), c, answer.isEmpty() ? "(no answer)" : answer);
        JsonObject r = failed[0] || answer.isEmpty() && !c.startsWith("particle") && !c.startsWith("playsound")
                ? Actions.error(answer.isEmpty() ? "The game didn't answer (it may not have worked)." : answer)
                : Actions.ok();
        r.addProperty("command", "/" + c);
        if (!answer.isEmpty()) r.addProperty("game", answer);
        return r;
    }
}
