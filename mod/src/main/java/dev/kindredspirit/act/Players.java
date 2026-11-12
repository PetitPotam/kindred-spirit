package dev.kindredspirit.act;

import net.minecraft.world.entity.player.Player;

import java.util.Collection;
import java.util.Locale;

/** Players by name, even roughly said: "walid" or "water walid" finds waterwalid. */
public final class Players {
    private Players() {}

    public static <P extends Player> P match(Collection<P> players, String name) {
        String want = squash(name);
        if (want.isEmpty()) return null;
        P best = null;
        int bestScore = 0;
        for (P p : players) {
            int score = score(squash(p.getGameProfile().getName()), want);
            if (score > bestScore) {
                best = p;
                bestScore = score;
            }
        }
        return best;
    }

    /** 3 exact, 2 one contains the other, 1 shares a long piece (speech-to-text: "waleed" for walid), 0 no. */
    static int score(String have, String want) {
        if (have.isEmpty()) return 0;
        if (have.equals(want)) return 3;
        if (have.contains(want) || want.contains(have)) return 2;
        String a = vowelless(have), b = vowelless(want);
        return b.length() >= 3 && (a.contains(b) || b.contains(a)) ? 1 : 0;
    }

    static String squash(String s) {
        return s == null ? "" : s.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]", "");
    }

    static String vowelless(String s) {
        return s.replaceAll("[aeiouy]", "");
    }
}
