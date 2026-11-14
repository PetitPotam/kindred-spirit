package dev.kindredspirit.act;

import java.util.ArrayList;
import java.util.List;

/**
 * The stop key (#138): everything she's doing in the world stops at once, without waiting for her brain: a build
 * halfway (what's built stays, and "undo that" puts it back), a blueprint, a job (chopping, mining, farming...).
 * An undo already running is left to finish: it's quick, and stopped halfway the rest couldn't be put back.
 * Runs on the world's server thread (the client hands it over).
 */
public final class StopAll {
    private StopAll() {}

    /** Stops what runs; returns what was stopped, in plain words (empty when nothing was). */
    public static List<String> run() {
        List<String> stopped = new ArrayList<>();
        if (Builder.busy()) {
            Builder.stop();
            stopped.add("a build");
        }
        if (BlueprintBuild.busy()) {
            BlueprintBuild.stop();
            stopped.add("a blueprint");
        }
        if (dev.kindredspirit.job.Jobs.busy()) {
            dev.kindredspirit.job.Jobs.stop();
            stopped.add("a job");
        }
        return stopped;
    }
}
