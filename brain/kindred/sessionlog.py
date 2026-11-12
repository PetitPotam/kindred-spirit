"""A record of each play session, to look at afterwards (by you, or by whoever improves her).

Every session in a world gets two files in ~/.kindred-spirit/logs/sessions/:
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

DIR = os.environ.get("KINDRED_SESSION_DIR") or os.path.expanduser("~/.kindred-spirit/logs/sessions")


class SessionLog:
    def __init__(self, directory=None, clock=time.time):
        self.dir, self.clock = directory or os.environ.get("KINDRED_SESSION_DIR") or DIR, clock
        self.events, self.path, self.world, self.started = [], None, None, None

    def start(self, world):
        self.finish()
        os.makedirs(self.dir, exist_ok=True)
        self.world, self.started, self.events = world or "unknown", self.clock(), []
        safe = re.sub(r"[^\w.-]+", "_", (world or "unknown").split(":", 1)[-1])[:40]
        self.path = os.path.join(self.dir, "%s-%s" % (time.strftime("%Y%m%d-%H%M", time.localtime(self.started)), safe))
        self.event("start", world=world)

    def event(self, kind, **data):
        if self.path is None:
            return
        e = {"t": round(self.clock() - (self.started if self.started is not None else self.clock()), 2), "kind": kind}
        e.update({k: v for k, v in data.items() if v not in (None, "")})
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
        lines = ["# Session in %s" % (self.world or "?").split(":", 1)[-1],
                 "", "%s · %.0f minutes" % (time.strftime("%Y-%m-%d %H:%M", time.localtime(self.started)), minutes), "",
                 "| | |", "|---|---|",
                 "| you spoke | %d times |" % len(you),
                 "| she spoke | %d lines (%.1f a minute), %d words |" % (len(said), len(said) / minutes, her_words),
                 "| answering you | %d |" % len(by("reply")),
                 "| on her own | %d (comments, musings, noticing things) |" % len(by("own")),
                 "| on instinct | %d (ow, warnings...) |" % (len(by("instinct")) + len(by("warning"))),
                 "| held back | %d (not the moment) |" % len(dropped),
                 "| interrupted | %d (by herself %d, by you %d) |" % (len(cuts), sum(1 for c in cuts if not c.get("by_player")),
                                                                    sum(1 for c in cuts if c.get("by_player"))),
                 "| tools | %d used, %d failed |" % (len(tools), len(failed)),
                 "| answers | %d, first words after %.1fs on average, %d slower than 4s |" % (
                     len(answers), sum(a.get("first_words", 0) for a in answers) / max(1, len(answers)), len(slow)),
                 "| errors | %d |" % len(errors), ""]
        flags = []
        if len(said) / minutes > 3:
            flags.append("She talked a lot: more than 3 lines a minute.")
        if len(by("own")) > max(3, len(by("reply"))):
            flags.append("She talked on her own more than she answered you.")
        if len(cuts) >= 3:
            flags.append("Her lines were interrupted %d times." % len(cuts))
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
