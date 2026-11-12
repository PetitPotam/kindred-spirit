package dev.kindredspirit.act;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * What the companion may do, decided by two settings the player chooses (see docs/DESIGN.md):
 * <ul>
 *   <li><b>power</b>: advisor (talks, finds, guides; never touches the world), helper (also acts
 *       when you ask: protects you, places a torch), allpowerful (also time and weather)</li>
 *   <li><b>style</b>: grounded (uses only what really exists: a torch from your inventory) or
 *       magic (can make things appear: give you items, a torch out of thin air)</li>
 * </ul>
 * The mod enforces this, not the AI: an action the settings don't allow is refused here even if
 * the AI asks for it. Pure Java, unit-tested.
 */
public final class Abilities {
    private Abilities() {}

    public enum Power { ADVISOR, HELPER, ALLPOWERFUL }

    public enum Style { GROUNDED, MAGIC }

    public enum Ability {
        // advice: reads the world, changes nothing
        FIND_ORE(false), FIND_ANIMAL(false), FIND_BLOCK(false), FIND_PLAYER(false), LOCATE(false), GUIDE(false), STOP_GUIDE(false), FOLLOW_PLAYER(false),
        // acts in the world when you ask
        PROTECT(true), PLACE_TORCH(true), HARVEST(true), BUILD(true),
        // makes things appear
        GIVE_ITEM(true), GIVE_EFFECT(true),
        // changes the whole world
        SET_TIME(true), SET_WEATHER(true);

        /** Changes the world (so: only in singleplayer, or when you host LAN). */
        public final boolean changesWorld;

        Ability(boolean changesWorld) {
            this.changesWorld = changesWorld;
        }

        public String id() {
            return name().toLowerCase(Locale.ROOT);
        }
    }

    public static boolean allowed(Ability a, Power p, Style s) {
        return switch (a) {
            case FIND_ORE, FIND_ANIMAL, FIND_BLOCK, FIND_PLAYER, LOCATE, GUIDE, STOP_GUIDE, FOLLOW_PLAYER -> true;
            case PROTECT, PLACE_TORCH, HARVEST, BUILD -> p != Power.ADVISOR;
            case GIVE_ITEM, GIVE_EFFECT -> p != Power.ADVISOR && s == Style.MAGIC;
            case SET_TIME, SET_WEATHER -> p == Power.ALLPOWERFUL;
        };
    }

    public static List<String> allowedIds(Power p, Style s) {
        List<String> out = new ArrayList<>();
        for (Ability a : Ability.values()) if (allowed(a, p, s)) out.add(a.id());
        return out;
    }

    /** Why it can't, in words the AI can pass on kindly. */
    public static String refusal(Ability a, Power p, Style s) {
        if ((a == Ability.GIVE_ITEM || a == Ability.GIVE_EFFECT) && s == Style.GROUNDED && p != Power.ADVISOR) {
            return "In grounded style I can't make things appear; I can only use what really exists. "
                    + "(The player can switch with /kindred style magic.)";
        }
        if (p == Power.ADVISOR) return "I'm set to advisor: I can talk, find and guide, but not touch the world. (/kindred power helper)";
        return "That needs more power than I have right now. (/kindred power allpowerful)";
    }

    public static Power power(String s) {
        try {
            return Power.valueOf(s.trim().toUpperCase(Locale.ROOT));
        } catch (Exception e) {
            return Power.HELPER;
        }
    }

    public static Style style(String s) {
        try {
            return Style.valueOf(s.trim().toUpperCase(Locale.ROOT));
        } catch (Exception e) {
            return Style.GROUNDED;
        }
    }

    public static Ability ability(String id) {
        try {
            return Ability.valueOf(id.trim().toUpperCase(Locale.ROOT));
        } catch (Exception e) {
            return null;
        }
    }
}
