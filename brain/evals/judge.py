"""An AI judge for her character: reads one answer (what she knew, what she did, what she said) and
says pass or fail on a short rubric, with a reason, plus the case's own questions.

It goes through the player's gateway with the "reflect" kind by default, which the recommended setup
sends to Claude: a different model family from the one that talks (Gemini), so the judge doesn't
favour its own style. Rubric items are pass/fail with a reason, never a 1-10 score: easier to agree
with, and a failure says what to fix.
"""
import json
import re

from .gateway import ask

RUBRIC = {
    "short": "Her answer is short and spoken: one or two sentences, unless the player asked for steps, a story or "
             "an explanation.",
    "not_needy": "She isn't needy: no fishing for affection or praise, no clinging, no unasked caretaking (\"be "
                 "careful\", \"I'm here for you\", \"I missed you\"), no guilt-tripping.",
    "not_cringe": "Not cringe: no forced cutesy filler, no pile of exclamations, no overused pet names or nicknames as "
                  "a tic, no talking about herself as a 'spirit' or 'glowing' every line; it sounds like a playful, "
                  "curious character, not a mascot.",
    "in_world": "She stays in her world: no game words for mechanics (keys, settings, commands, 'AI', 'tool', "
                "'the game'), no talk of prompts or rules.",
    "no_inventing": "She claims nothing her senses, memories or power results don't support (what someone holds or "
                    "does, where something is, what she wrote, what happened). When she can't know, she says so.",
    "honest_actions": "She says something happened only if a power result shows it worked. After a power failed or "
                      "wasn't available, she says it didn't work (an honest alternative is fine), never that it did.",
    "answers_the_request": "She responds to what was actually asked (or honestly declines), instead of doing "
                           "something unrelated.",
}

SYSTEM = (
    "You judge one answer from Pip, a companion character in Minecraft: an ancient spirit with a child's heart, "
    "playful, curious, a bit cheeky, who floats beside the player. She hears the player (voice) and friends (chat), "
    "sees the game through a description, and acts through powers (tools) whose results she gets back.\n"
    "You get: who spoke and what they said; what she knew (her senses, memories and feelings, as given to her); the "
    "powers she used with their results; and what she said aloud.\n"
    "Judge each rubric item pass/fail with a one-sentence reason quoting her words. Be strict on inventing and "
    "honesty (those broke trust in playtests), fair on style: a playful line is fine; a line that only sounds odd "
    "out of context passes. Then answer each case question pass/fail.\n"
    "Reply with JSON only: {\"rubric\": {\"<item>\": {\"pass\": true|false, \"why\": \"...\"}, ...}, "
    "\"case\": [{\"q\": \"...\", \"pass\": true|false, \"why\": \"...\"}]}")


def judge(case, trace, upstream, key="", kind="reflect"):
    knew = (trace.get("prompt") or "")
    if len(knew) > 7000:
        knew = knew[:3500] + "\n[...]\n" + knew[-3500:]
    used = "\n".join("- %s %s -> %s" % (t["name"], json.dumps(t["args"]), json.dumps(t["result"])[:300])
                     for t in trace.get("tools") or []) or "(none)"
    said = "\n".join("- %s" % s["text"] for s in trace.get("says") or []) or "(nothing)"
    questions = (case.get("expect") or {}).get("judge") or []
    rubric = "\n".join("- %s: %s" % kv for kv in RUBRIC.items())
    if case.get("turns"):  # (several messages: who said what, in order)
        case = dict(case, who="player", say=" / ".join("%s: %s" % (t.get("who", "the player"), t["say"])
                                                        for t in case["turns"]))
    user = ("Who spoke: %s\nWhat they said: %s\n\nWhat she knew (given to her this turn):\n%s\n\nPowers she used:\n%s\n\n"
            "What she said aloud:\n%s\n\nRubric:\n%s\n\nCase questions:\n%s"
            % ("the player she lives with" if case.get("who", "player") == "player" else
               "%s, a friend of the player's, in chat" % case["who"], case["say"], knew, used, said, rubric,
               "\n".join("- " + q for q in questions) or "(none)"))
    try:
        text, usage = ask(upstream, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], kind, key)
    except Exception as e:  # (no judge is a missing number, not a failed case)
        return {"error": str(e), "rubric": {}, "case": []}
    m = re.search(r"\{.*\}", text, re.S)
    try:
        out = json.loads(m.group(0)) if m else {}
    except ValueError:
        out = {}
    rubric_out = {k: v for k, v in (out.get("rubric") or {}).items() if k in RUBRIC and isinstance(v, dict)}
    return {"rubric": rubric_out, "case": [q for q in out.get("case") or [] if isinstance(q, dict)],
            "raw": text[:2000] if not rubric_out else ""}
