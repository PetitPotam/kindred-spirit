"""How her build or job really ended, in her words (#139).

The game reports each build, blueprint and job's real outcome when it ends (the snapshot's "ended": what it was, how
much was done of how much, how much couldn't be, and why it stopped early, if it did; mod/.../act/Outcome.java). She
says it as it is: "All done!" only when it's really done; "most of it, 12 wouldn't fit" when it half-failed; why it
stopped when something stopped it. Stopped by you ("stop", the stop key): nothing to say. A small thing that went
fine (a few blocks) isn't worth a word either.
"""
import re

WORTH_A_WORD = 20  # blocks or steps: smaller things that went fine end quietly


def thing(e):
    """'building a wall' -> 'the wall'; 'village plains small house 1' -> 'the village plains small house'."""
    what = re.sub(r"^(building|clearing)\s+(an?\s+|the\s+)?", "", str(e.get("what") or "").strip())
    what = re.sub(r"\s+\d+$", "", what)
    return "the " + what if what else "that"


def line(e):
    """(text, mood) for how it ended, or None to stay quiet."""
    if not isinstance(e, dict):
        return None
    kind, stopped = e.get("kind"), e.get("stopped")
    done, skipped, total = int(e.get("done") or 0), int(e.get("skipped") or 0), int(e.get("total") or 0)
    if stopped == "asked":
        return None
    name = thing(e)
    if stopped:
        if kind == "job":
            return "I had to stop: %s. I did %d of %d." % (stopped, done, total), "sad"
        return "I had to stop %s: I %s. %d of %d blocks are in; say \"undo that\" if you'd rather not keep it." % (
            name, stopped, done, total), "sad"
    if skipped and (skipped >= 3 or skipped * 10 >= total):
        if kind == "job":
            return "Done with %s! %d went fine, %d I couldn't get." % (name, done, skipped), "calm"
        return "%s is done, mostly: %d of %d blocks went in, %d wouldn't fit (something in the way, or too far from " \
               "me)." % (name[0].upper() + name[1:], done, total, skipped), "calm"
    if total < WORTH_A_WORD:
        return None
    if kind == "job":
        return "All done with %s!" % name, "happy"
    return "All done: %s is finished!" % name, "happy"
