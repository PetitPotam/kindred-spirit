"""What her prompts are made of: a breakdown of the tokens sent for each answer, from the gateway's log.

    .venv/bin/python -m evals.context --since "2026-11-12 22:55" --until "2026-11-12 23:58"

The gateway logs each call's token count, how many messages it had, which tools were offered and the
newest user message in full (the game state, memories, heart and the player's words), but not the
system prompt or the earlier conversation. Those are rebuilt here with the brain's own code: her
character (mind.system_prompt) with who she'd become at that time (the last "becoming" System 2 wrote)
and the conversation summary (the last fold), the tool definitions by name (tools.py), and the
conversation window from the earlier answers in the log. Characters become tokens with two ratios
fitted on the calls themselves (prose, and tool definitions); the fit is printed so you can see how
close it is.

It also says how much of each prompt was the same as the call before it (what a provider's prefix
cache could reuse): the rounds of one answer (a tool round re-sends everything), and answer to answer.
"""
import argparse
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from kindred import mind as mind_mod  # noqa: E402
from kindred import tools as tools_mod  # noqa: E402

LOG = os.path.join(os.environ.get("KINDRED_HOME") or os.path.expanduser("~/.kindred-spirit"), "logs", "gateway.jsonl")
SECTION = re.compile(r"^\[([^\]]+)\]\n", re.M)
PREFIX = re.compile(r"^\(said aloud; speech-to-text may have misheard some words\) ")
DONE = re.compile(r"\n\(You already did this: .*?\.\)$", re.S)
TOOLS = {**tools_mod.ABILITY_TOOLS, **{t["function"]["name"]: t for t in tools_mod.MEMORY_TOOLS}}
FOLD_SYSTEM = 560  # (characters of mind.fold's system prompt)


def load(since, until, path=LOG):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if since <= d.get("time", "") <= until:
                out.append(d)
    return out


def split_sections(text):
    parts = SECTION.split(text or "")
    out = {"(before)": len(parts[0])} if parts[0] else {}
    for name, body in zip(parts[1::2], parts[2::2]):
        out[name] = len(body)
    return out


def player_words(last):
    """The [Player] part as the brain keeps it in the conversation (without the notes added for the AI)."""
    words = (last or "").split("[Player]\n", 1)[-1]
    return DONE.sub("", PREFIX.sub("", words)).strip()


def rebuild(recs, history_turns=8):
    """Each reply/own call with its parts in characters; answers grouped (the rounds of one answer)."""
    becoming, summary, window, calls = "", "", [], []
    answer = None
    for d in recs:
        kind = d.get("kind")
        if kind == "reflect" and '"becoming"' in (d.get("reply") or ""):
            m = re.search(r"\{.*\}", d["reply"], re.S)
            try:
                becoming = json.loads(m.group(0)).get("becoming", becoming) if m else becoming
            except ValueError:
                pass
            continue
        if kind == "fold" and d.get("reply"):
            summary = mind_mod.clean_summary(d["reply"]) or summary
            continue
        if kind not in ("reply", "own") or not d.get("tokens_in"):
            continue
        last = d.get("player") or ""
        new_answer = last.startswith("[What you see") and (answer is None or last != answer["last"])
        if new_answer:
            if answer:  # the previous answer joins the conversation window
                if answer["kind"] == "reply":
                    window.append(("user", player_words(answer["last"])))
                window.append(("assistant", answer["reply"]))
                window = window[-2 * history_turns:]
            answer = {"last": last, "kind": kind, "rounds": 0, "reply": ""}
        if answer is None:
            continue
        answer["rounds"] += 1
        answer["reply"] = d.get("reply") or answer["reply"]
        system = len(mind_mod.system_prompt("Pip", "", becoming)) + (
            len("\n\nEarlier in this conversation (summary): ") + len(summary) if summary else 0)
        tools_chars = sum(len(json.dumps(TOOLS[n])) for n in d.get("tools") or [] if n in TOOLS)
        calls.append({
            "time": d["time"], "kind": kind, "guest": "another player here, not the player you live beside" in last,
            "round": answer["rounds"], "tokens_in": d["tokens_in"], "messages": d.get("messages"),
            "tools_n": len(d.get("tools") or []), "tool_names": tuple(d.get("tools") or []),
            "chars": {"system (her character)": system - len(becoming) - (len(summary) + 43 if summary else 0),
                      "who she's become lately": len(becoming) + (49 if becoming else 0),
                      "conversation summary": len(summary) + 43 if summary else 0,
                      "conversation window": sum(len(c) + 12 for _, c in window),
                      **{"[%s]" % k: v for k, v in split_sections(last).items()}},
            "tools_chars": tools_chars, "becoming": becoming, "summary": summary, "window": list(window),
            "last": last,
        })
    return calls


def fit(calls):
    """chars per token for prose and for tool definitions (least squares on first rounds)."""
    first = [c for c in calls if c["round"] == 1]
    xs = [(sum(c["chars"].values()), c["tools_chars"], c["tokens_in"]) for c in first]
    # tokens = a*prose + b*tools (no intercept): normal equations
    s11 = sum(p * p for p, _, _ in xs)
    s12 = sum(p * t for p, t, _ in xs)
    s22 = sum(t * t for _, t, _ in xs)
    y1 = sum(p * y for p, _, y in xs)
    y2 = sum(t * y for _, t, y in xs)
    det = s11 * s22 - s12 * s12
    a, b = (y1 * s22 - y2 * s12) / det, (s11 * y2 - s12 * y1) / det
    errs = [abs(a * p + b * t - y) / y for p, t, y in xs]
    return a, b, statistics.median(errs)


def report(calls):
    a, b, err = fit(calls)
    print("fit: %.2f chars per token for prose, %.2f for tool definitions; median error %.1f%%"
          % (1 / a, 1 / b if b else float("inf"), 100 * err))
    first = [c for c in calls if c["round"] == 1]
    groups = {"the player's turn": [c for c in first if c["kind"] == "reply" and not c["guest"]],
              "a friend's turn (chat)": [c for c in first if c["guest"]],
              "her own line": [c for c in first if c["kind"] == "own"]}
    out = {"fit": {"prose_chars_per_token": round(1 / a, 2), "tool_chars_per_token": round(1 / b, 2) if b else None,
                   "median_error": round(err, 3)}, "groups": {}}
    for name, cs in groups.items():
        if not cs:
            continue
        keys = sorted({k for c in cs for k in c["chars"]}, key=lambda k: -statistics.mean(c["chars"].get(k, 0) for c in cs))
        parts = {k: round(a * statistics.mean(c["chars"].get(k, 0) for c in cs)) for k in keys}
        parts["tool definitions (%d tools)" % round(statistics.mean(c["tools_n"] for c in cs))] = round(
            b * statistics.mean(c["tools_chars"] for c in cs))
        measured = statistics.median(c["tokens_in"] for c in cs)
        out["groups"][name] = {"calls": len(cs), "measured_median_tokens": measured, "parts": parts}
        print("\n%s: %d answers, measured median %d tokens in (first round)" % (name, len(cs), measured))
        for k, v in sorted(parts.items(), key=lambda kv: -kv[1]):
            print("   %-46s %5d" % (k, v))
    # rounds
    answers, cur = [], None
    for c in calls:
        if c["round"] == 1:
            cur = [c]
            answers.append(cur)
        elif cur is not None:
            cur.append(c)
    rounds = [len(x) for x in answers]
    total = sum(c["tokens_in"] for c in calls)
    later = sum(c["tokens_in"] for c in calls if c["round"] > 1)
    reused_rounds = sum(prev["tokens_in"] for x in answers for prev, c in zip(x, x[1:]))
    # answer to answer: the same system prompt and tools, and how much of the window was unchanged
    stable, window_kept = 0, 0
    for prev, c in zip([x[0] for x in answers], [x[0] for x in answers][1:]):
        same_sys = prev["becoming"] == c["becoming"] and prev["summary"] == c["summary"]
        same_tools = prev["tool_names"] == c["tool_names"]
        sys_tokens = a * (c["chars"]["system (her character)"] + c["chars"]["who she's become lately"]
                          + c["chars"]["conversation summary"])
        if same_sys:
            stable += sys_tokens + (b * c["tools_chars"] if same_tools else 0)
            n = 0
            for m1, m2 in zip(prev["window"], c["window"]):
                if m1 != m2:
                    break
                n += 1
            window_kept += a * sum(len(x) + 12 for _, x in c["window"][:n])
    first_total = sum(x[0]["tokens_in"] for x in answers)
    out["rounds"] = {"answers": len(answers), "calls": len(calls), "calls_per_answer": round(len(calls) / len(answers), 2),
                     "answers_with_tool_rounds": sum(1 for r in rounds if r > 1),
                     "tokens_in_total": total, "tokens_in_later_rounds": later,
                     "later_rounds_share": round(later / total, 2),
                     "reusable_in_later_rounds": round(reused_rounds / total, 2),
                     "answer_to_answer_stable_prefix_share": round(stable / first_total, 2),
                     "answer_to_answer_window_kept_share": round(window_kept / first_total, 2),
                     "same_tools_as_previous_answer": round(sum(
                         1 for p, c in zip(answers, answers[1:]) if p[0]["tool_names"] == c[0]["tool_names"])
                         / max(1, len(answers) - 1), 2)}
    print("\nrounds: %(answers)d answers, %(calls)d calls (%(calls_per_answer)s per answer); "
          "%(answers_with_tool_rounds)d answers had tool rounds" % out["rounds"])
    print("tokens in: %(tokens_in_total)d in all; later rounds %(tokens_in_later_rounds)d (%(later_rounds_share)s of all), "
          "of which the part repeated from the round before is %(reusable_in_later_rounds)s of all tokens" % out["rounds"])
    print("answer to answer: stable prefix (character + who she's become + summary + same tools) %s of first-round "
          "tokens; conversation window unchanged at its start %s; same tool list as the answer before %s"
          % (out["rounds"]["answer_to_answer_stable_prefix_share"], out["rounds"]["answer_to_answer_window_kept_share"],
             out["rounds"]["same_tools_as_previous_answer"]))
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--since", default="2026-11-12 22:55")
    p.add_argument("--until", default="2026-11-12 23:58")
    p.add_argument("--log", default=LOG)
    p.add_argument("--json")
    a = p.parse_args(argv)
    calls = rebuild(load(a.since, a.until, a.log))
    out = report(calls)
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
