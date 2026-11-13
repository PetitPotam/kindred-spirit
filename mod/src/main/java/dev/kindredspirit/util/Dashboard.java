package dev.kindredspirit.util;

import java.util.Locale;

/**
 * Her dashboard (services/dashboard.py) is a page on the computer where her brain runs, reachable from that
 * computer only (127.0.0.1). The dashboard key opens it when the brain is set up on this computer.
 */
public final class Dashboard {
    private Dashboard() {}

    /**
     * The dashboard's address, or null when her brain is set up on another computer (its dashboard only answers
     * there) or the port makes no sense.
     */
    public static String url(String brainHost, int port) {
        if (port <= 0 || port > 65535) return null;
        String h = brainHost == null ? "" : brainHost.trim().toLowerCase(Locale.ROOT);
        boolean here = h.isEmpty() || h.equals("127.0.0.1") || h.equals("localhost")
                || h.equals("::1") || h.equals("[::1]");
        return here ? "http://127.0.0.1:" + port + "/" : null;
    }
}
