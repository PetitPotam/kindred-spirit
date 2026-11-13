"""A record of each play session, to look at afterwards (by you, or by whoever improves her).

Every session in a world gets two files in ~/.kindred-spirit/logs/sessions/ (in $KINDRED_HOME/logs/sessions when
KINDRED_HOME is set, or in $KINDRED_SESSION_DIR):
- <date>-<world>.jsonl: the timeline, one event per line (what you said, every line she said or
  didn't get to say and why, interruptions, tools and their results, warnings, how her heart moved,
  errors, how long her answers took);
- <date>-<world>.md, written when you leave: a readable summary with the numbers that show what
  went wrong (lines per minute, how much she talked on her own, interruptions, failed tools, slow
  answers, errors) followed by the timeline as a conversation.
"""
import json
import os
import re
import time

def default_dir():
    """KINDRED_SESSION_DIR, else logs/sessions in the brain's home folder (KINDRED_HOME, else ~/.kindred-spirit)."""
    home = os.environ.get("KINDRED_HOME") or os.path.join(os.path.expanduser("~"), ".kindred-spirit")
    return os.environ.get("KINDRED_SESSION_DIR") or os.path.join(home, "logs", "sessions")


DIR = default_dir()


ASKED_AGAIN = re.compile(r"\b(i (told|said|asked) you|again|not that|i said|no,? (i|not|that)|wrong|you didn'?t|why (are|did)n'?t "
                         r"you|still not|i meant)\b", re.I)


def extra_rows(ev):
    """What a playtest is analysed with: per person, what failed and why, what had to be asked twice or corrected, how
    much System 0 did alone, the settings at the start, and the time from releasing the talk key to her first word."""
    rows = []
    people = {}
    for e in ev:
        if e["kind"] in ("you", "guest"):
            people.setdefault("you" if e["kind"] == "you" else e.get("who", "a friend"), []).append(e)
    for who, msgs in people.items():
        rows.append("| %s | %d messages |" % (who, len(msgs)))
    failed = [e for e in ev if e["kind"] == "tool" and not e.get("ok", True)]
    if failed:
        rows.append("| failed tools | %s |" % "; ".join("%s (%s): %s" % (e.get("name"), e.get("who", "player"),
                                                                       str(e.get("result", ""))[:80]) for e in failed[:8]))
    again = [e for e in ev if e["kind"] in ("you", "guest") and ASKED_AGAIN.search(e.get("text", ""))]
    if again:
        rows.append("| asked again or corrected | %d: %s |" % (len(again), " / ".join(
            "%s \"%s\"" % (fmt_t(e["t"]), e.get("text", "")[:60]) for e in again[:6])))
    decided = [e for e in ev if e["kind"] == "decide"]
    if decided:
        alone = sum(1 for e in decided if e.get("acts") and not e.get("ai", True))
        forced = sum(1 for e in decided if e.get("force"))
        rows.append("| System 0 | acted at once on %d of %d messages, required a tool %d times |" % (
            sum(1 for e in decided if e.get("acts")), len(decided), forced) + ("" if not alone else " (%d alone)" % alone))
    timing = [e for e in ev if e["kind"] == "timing" and e.get("to_first_word") is not None]
    if timing:
        med = lambda xs: sorted(xs)[len(xs) // 2]  # noqa: E731
        rows.append("| from releasing the talk key | text after %.1fs, first word after %.1fs (median of %d; trip %.1fs, "
                    "speech-to-text %.1fs) |" % (med([e.get("to_text", 0) for e in timing]),
                                                med([e["to_first_word"] for e in timing]), len(timing),
                                                med([e.get("trip", 0) for e in timing]), med([e.get("stt", 0) for e in timing])))
    first = next((e for e in ev if e["kind"] == "settings"), None)
    if first:
        rows.append("| settings at start | %s |" % ", ".join("%s=%s" % (k, v) for k, v in (first.get("now") or {}).items()))
    return rows


def fmt_t(t):
    return "%02d:%02d" % (t // 60, t % 60)


def felt_rows(ev, words_per_second=2.6):
    """What waiting felt like, per person (you, and each friend): from the message to her first word, and to the end
    of her answer as spoken (estimated from its words). Thinking is rarely the slow part: queues and long lines are."""
    rows, by = [], {}
    asks = [e for e in ev if e["kind"] in ("you", "guest")]
    lines = [e for e in ev if e["kind"] == "pip" and e.get("source") == "reply"]
    for q in asks:
        who = "you" if q["kind"] == "you" else q.get("who", "a friend")
        to = "player" if who == "you" else who
        a = next((p for p in lines if q["t"] <= p["t"] <= q["t"] + 45 and p.get("to", "player") == to), None)
        if a:
            spoken = len((a.get("text") or "").split()) / words_per_second
            by.setdefault(who, []).append((a["t"] - q["t"], a["t"] - q["t"] + spoken))
    med = lambda xs: sorted(xs)[len(xs) // 2]  # noqa: E731
    for who, waits in sorted(by.items(), key=lambda kv: kv[0] != "you"):
        rows.append("| felt wait (%s) | first word after %.1fs, answer over after %.1fs (median of %d) |" % (
            who, med([w[0] for w in waits]), med([w[1] for w in waits]), len(waits)))
    return rows


# events that carry where things stood (who was near, health, the play mode): the ones you analyse a playtest by
CONTEXT_KINDS = {"you", "guest", "tool", "alert", "heart", "touch", "death", "hurt", "cut", "error", "answer", "decide",
                 "friend_near", "friend_gone", "arrived", "wrong_way", "vanish", "place", "settings", "where", "timing"}


class SessionLog:
    def __init__(self, directory=None, clock=time.time):
        self.dir, self.clock = directory or default_dir(), clock
        self.events, self.path, self.world, self.started = [], None, None, None
        self.context = None  # () -> {"at": [x, y, z], "dim", "biome", "hp", "food", "near", "mode"} (set by the brain)

    def start(self, world):
        self.finish()
        os.makedirs(self.dir, exist_ok=True)
        self.world, self.started, self.events = world or "unknown", self.clock(), []
        safe = re.sub(r"[^\w.-]+", "_", (world or "unknown").split(":", 1)[-1])[:40]
        self.path = os.path.join(self.dir, "%s-%s" % (time.strftime("%Y%m%d-%H%M", time.localtime(self.started)), safe))
        self.event("start", world=world, at=round(self.started, 1))


    def event(self, kind, **data):
        if self.path is None:
            return
        e = {"t": round(self.clock() - (self.started if self.started is not None else self.clock()), 2), "kind": kind}
        e.update({k: v for k, v in data.items() if v not in (None, "")})
        if kind in CONTEXT_KINDS and self.context and "ctx" not in e:
            try:
                e["ctx"] = self.context()
            except Exception:  # (never lose an event for its context)
                pass
        self.events.append(e)
        try:
            with open(self.path + ".jsonl", "a") as fh:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def finish(self):
        """You left: the summary next to the timeline."""
        if self.path is None or not self.events:
            self.path = None
            return None
        self.event("end")
        try:
            with open(self.path + ".md", "w") as fh:
                fh.write(self.summary())
        except OSError:
            pass
        done, self.path = self.path + ".md", None
        return done

    def summary(self):
        ev = self.events
        minutes = max(1 / 60, (ev[-1]["t"] - ev[0]["t"]) / 60) if ev else 1
        said = [e for e in ev if e["kind"] == "pip"]
        by = lambda src: [e for e in said if e.get("source") == src]  # noqa: E731
        you = [e for e in ev if e["kind"] == "you"]
        dropped = [e for e in ev if e["kind"] == "not_said"]
        cuts = [e for e in ev if e["kind"] == "cut"]
        tools = [e for e in ev if e["kind"] == "tool"]
        failed = [e for e in tools if not e.get("ok", True)]
        errors = [e for e in ev if e["kind"] == "error"]
        answers = [e for e in ev if e["kind"] == "answer"]
        slow = [e for e in answers if e.get("first_words", 0) > 4]
        her_words = sum(len(e.get("text", "").split()) for e in said)
        replies = by("reply")
        cut_replies = [c for c in cuts if c.get("by_player") and c.get("was") == "reply"]
        per_reply = sum(len(re.findall(r"[.!?…]+(\s|$)", e.get("text", "") + " ")) for e in replies) / max(1, len(replies))
        lines = ["# Session in %s" % (self.world or "?").split(":", 1)[-1],
                 "", "%s · %.0f minutes" % (time.strftime("%Y-%m-%d %H:%M", time.localtime(self.started)), minutes), "",
                 "| | |", "|---|---|",
                 "| you spoke | %d times |" % len(you),
                 "| she spoke | %d lines (%.1f a minute), %d words |" % (len(said), len(said) / minutes, her_words),
                 "| answering you | %d (%.1f sentences each) |" % (len(replies), per_reply),
                 "| you talked over her answer | %d of %d |" % (len(cut_replies), len(replies)),
                 "| on her own | %d (comments, musings, noticing things) |" % len(by("own")),
                 "| on instinct | %d (ow, warnings...) |" % (len(by("instinct")) + len(by("warning"))),
                 "| held back | %d (not the moment) |" % len(dropped),
                 "| interrupted | %d (by herself %d, by you %d) |" % (len(cuts), sum(1 for c in cuts if not c.get("by_player")),
                                                                    sum(1 for c in cuts if c.get("by_player"))),
                 "| tools | %d used, %d failed |" % (len(tools), len(failed)),
                 "| answers | %d, first words after %.1fs on average, %d slower than 4s |" % (
                     len(answers), sum(a.get("first_words", 0) for a in answers) / max(1, len(answers)), len(slow)),
                 "| errors | %d |" % len(errors)] + felt_rows(ev) + extra_rows(ev) + [""]
        flags = []
        if len(said) / minutes > 3:
            flags.append("She talked a lot: more than 3 lines a minute.")
        if len(by("own")) > max(3, len(by("reply"))):
            flags.append("She talked on her own more than she answered you.")
        if len(cuts) >= 3:
            flags.append("Her lines were interrupted %d times." % len(cuts))
        if replies and len(cut_replies) / len(replies) > 0.4:
            flags.append("You talked over %d of her %d answers: they're too long." % (len(cut_replies), len(replies)))
        if failed:
            flags.append("Failed tools: " + ", ".join(sorted({e.get("name", "?") for e in failed})))
        if errors:
            flags.append("Errors: " + "; ".join(sorted({e.get("text", "")[:80] for e in errors})))
        if flags:
            lines += ["**What stands out**", ""] + ["- " + f for f in flags] + [""]
        lines += ["## Timeline", ""]
        for e in ev:
            t = "%02d:%02d" % (e["t"] // 60, e["t"] % 60)
            k = e["kind"]
            if k == "you":
                lines.append("- `%s` **you**%s: %s" % (t, " (voice)" if e.get("spoken") else "", e.get("text", "")))
            elif k == "guest":
                lines.append("- `%s` **%s** (friend, in chat): %s" % (t, e.get("who", "?"), e.get("text", "")))
            elif k == "pip":
                lines.append("- `%s` **Pip** (%s%s): %s" % (t, e.get("source", ""), (", " + e["why"]) if e.get("why") else "",
                                                            e.get("text", "")))
            elif k == "not_said":
                lines.append("- `%s` _held back (%s)_: %s" % (t, e.get("reason", ""), e.get("text", "")))
            elif k == "cut":
                lines.append("- `%s` _interrupted%s_: %s" % (t, " by you" if e.get("by_player") else "", e.get("rest", "")))
            elif k == "tool":
                lines.append("- `%s` tool %s %s → %s" % (t, e.get("name"), e.get("args", ""), e.get("result", "")))
            elif k == "answer":
                lines.append("- `%s` _answer: first words after %.1fs, %.1fs in all_" % (
                    t, e.get("first_words", 0), e.get("total", 0)))
            elif k in ("heart", "alert", "error", "notice", "start", "end"):
                lines.append("- `%s` %s: %s" % (t, k, ", ".join("%s=%s" % (a, b) for a, b in e.items() if a not in ("t", "kind"))))
        return "\n".join(lines) + "\n"
