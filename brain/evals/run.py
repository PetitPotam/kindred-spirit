"""Pip's eval set: moments from real play sessions, replayed through the whole brain.

Each case is one moment from a playtest log: what she saw (a snapshot), the conversation so far, what
she remembered, and the words someone said to her, with what must and must not happen. The runner
plays the mod's part over the brain's real WebSocket (hello, join, snapshot, chat; it answers her
powers with the results the case gives) and records everything: her acts, the tools she used and
what reached the game, what she said, the AI calls behind it.

    scripts/eval.sh                        stub mode: no services, no AI (what CI runs)
    scripts/eval.sh --mode local           + System 0's understanding (local embeddings), still no AI
    scripts/eval.sh --mode live --judge    the real AI through your gateway (a few cents), and a judge
    scripts/eval.sh --mode live --repeat 3 --only follow-me
    scripts/eval.sh --brain ../other-checkout/brain    the same cases against another version

Checks come in two layers. "brain" checks hold whatever the AI says: in stub and local modes the AI's
part is played by what the real AI did in the playtest (its tool calls and words), so they test
System 0 and the guards against the mistakes that really happened. "ai" checks are about her choices
and words, so they only run with the real AI. The judge (--judge, live) reads each answer for
character: short, not needy, not cringe, no inventing, honest about what her powers did.

Results: evals/results/<label>-<mode>.json (not committed) and a table on screen. evals/baselines/
keeps the numbers each change is compared with.
"""
import argparse
import asyncio
import copy
import glob
import json
import os
import re
import statistics
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = "eval-token"
BASE_SNAPSHOT = {
    "type": "snapshot", "health": 20.0, "maxHealth": 20.0, "food": 20, "saturation": 5.0, "armor": 0,
    "air": 300, "maxAir": 300, "onFire": False, "gamemode": "survival", "effects": [],
    "where": {"x": 230, "y": 65, "z": -140, "dimension": "minecraft:overworld", "biome": "minecraft:plains",
              "facing": "south", "yaw": 0.0, "skyVisible": True, "light": 15},
    "time": {"day": 4, "timeOfDay": 1000, "raining": False, "thundering": False},
    "holding": "minecraft:oak_log", "offhand": "", "inventory": {"minecraft:oak_log": 64, "minecraft:cooked_beef": 20},
    "wearing": [], "lookingAt": {"block": "minecraft:short_grass", "distance": 6.0}, "hostiles": [], "animals": [],
    "playerName": "AlexCraftX",
}


# ---------------------------------------------------------------------------------------- the game's part

def game_result(action, args, case):
    """What the game answers when she uses a power: the case's script first, else a plain success."""
    for r in (case.get("game") or {}).get(action, []) if isinstance((case.get("game") or {}).get(action), list) else []:
        if matches(args, r.get("when") or {}):
            return copy.deepcopy(r["result"])
    r = (case.get("game") or {}).get(action)
    if isinstance(r, dict):
        return copy.deepcopy(r)
    host = case.get("snapshot", {}).get("playerName") or BASE_SNAPSHOT["playerName"]
    to = args.get("to") or host
    return {
        "guide": {"ok": True, "guiding": True, "distance": 40, "direction": "ahead"},
        "stop_guide": {"ok": True, "stopped": True},
        "follow_player": {"ok": True, "now": "Pip floats beside %s now." % (args.get("name") or "you"),
                          "following": args.get("name") or "you"},
        "give_item": {"ok": True, "gave": "%s %s" % (args.get("count", 1), args.get("item", "")), "to": to},
        "give_effect": {"ok": True, "to": to, "effect": args.get("effect", ""), "seconds": 180},
        "protect": {"ok": True, "pushedAway": 0},
        "place_torch": {"ok": True, "placedAt": "230 65 -142", "usedYourTorch": False},
        "command": {"ok": True, "command": "/" + str(args.get("command", "")).lstrip("/"), "result": "done"},
    }.get(action, {"ok": True})


# ---------------------------------------------------------------------------------------- one moment

async def play(case, gw, mode, cfg_extra, timeout=45):
    from websockets.asyncio.client import connect
    from websockets.asyncio.server import serve

    from kindred import config
    from kindred.alerts import Alerts
    from kindred.memory import GatewayMemory, Memory
    from kindred.server import Brain

    world = "eval:" + case["id"]
    gw.begin(case.get("stub_ai") if mode != "live" else [])
    gw.seed(world, case.get("history") or [], case.get("memories") or [])
    setup = case.get("setup") or {}
    cfg = config.merge(config.DEFAULTS, cfg_extra)
    cfg = config.merge(cfg, {
        "gateway": {"url": gw.url, "key": ""},
        "voice": {"enabled": False},
        "behaviour": {"greet_on_join": False, "small_talk_minutes": 0, "instinct_lines_after": 0,
                      "alerts": bool(setup.get("alerts", False))},
        "heart": {"amnesia": bool(setup.get("amnesia", False)), "start_bond": setup.get("bond", 42),
                  "pranks": False, "fibs": False, "auto_protect": False},
    })
    brain = Brain(cfg, TOKEN, alerts=Alerts(), memory=Memory(GatewayMemory(gw.url)))
    brain.seconds_to_say = lambda text: 0
    trace = {"says": [], "acts": [], "tools": [], "game": [], "states": [], "error": None}
    real_run_tool = brain.run_tool

    async def run_tool(name, args):  # (records every use of a power or memory tool, and its result)
        result = await real_run_tool(name, args)
        trace["tools"].append({"name": name, "args": args, "result": result})
        return result
    brain.run_tool = run_tool

    hello = {"type": "hello", "mod": "eval", "minecraft": "1.21.1", "name": "Pip",
             "abilities": setup.get("abilities", ABILITIES), "power": setup.get("power", "allpowerful"),
             "style": setup.get("style", "magic"), "singleplayer": bool(setup.get("singleplayer", True)),
             "glow": True}
    hello.update(setup.get("hello") or {})
    snap = merge(BASE_SNAPSHOT, case.get("snapshot") or {})
    chats = []  # one message, or several in turn ("turns": a task over a few steps, two people talking)
    for turn in case.get("turns") or [{"who": case.get("who", "player"), "say": case["say"]}]:
        chat = {"type": "chat", "text": turn["say"]}
        if turn.get("who", "player") != "player":
            chat.update({"from": turn["who"], "powers": bool(setup.get("guest_powers", True))})
        chats.append((chat, turn.get("snapshot"), float(turn.get("after", 0))))

    async with serve(brain.handler, "127.0.0.1", 0, process_request=brain.check_auth, max_size=2 ** 24) as server:
        url = "ws://127.0.0.1:%d/" % server.sockets[0].getsockname()[1]
        async with connect(url, additional_headers={"Authorization": "Bearer " + TOKEN}, max_size=2 ** 24) as ws:
            t0 = [None]
            last_msg = [time.monotonic()]

            async def reader():
                async for raw in ws:
                    msg = json.loads(raw)
                    last_msg[0] = time.monotonic()
                    t = round(time.monotonic() - t0[0], 2) if t0[0] else None
                    kind = msg.get("type")
                    if kind == "do":
                        result = game_result(msg.get("action", ""), msg.get("args") or {}, case)
                        trace["game"].append({"action": msg.get("action"), "args": msg.get("args") or {},
                                              "result": result, "t": t})
                        await ws.send(json.dumps(dict(result, type="done", id=msg.get("id"))))
                    elif kind == "say" and t is not None:
                        trace["says"].append({"text": msg.get("text", ""), "mood": msg.get("mood"), "t": t})
                    elif kind == "act" and t is not None:
                        trace["acts"].append({k: v for k, v in msg.items() if k != "type"})
                    elif kind == "state" and t is not None:
                        trace["states"].append(msg.get("state"))

            await ws.send(json.dumps(hello))
            task = asyncio.create_task(reader())
            await ws.send(json.dumps({"type": "event", "event": "join", "world": world}))
            await ws.send(json.dumps(snap))
            await asyncio.sleep(0.4)
            if setup.get("following"):
                brain.snapshot["following"] = setup["following"]
            t0[0] = time.monotonic()
            for chat, turn_snap, after in chats:
                if turn_snap:  # (the world moved on between two turns)
                    await ws.send(json.dumps(merge(snap, turn_snap)))
                if after:  # (seconds after the turn before: 0 = when it's answered; a small number = talking over it)
                    await asyncio.sleep(after)
                said_before = len(trace["says"]) + len(trace["states"])
                await ws.send(json.dumps(chat))
                if after and after < 1:
                    continue
                seen_busy, started = False, time.monotonic()
                while time.monotonic() - started < timeout:
                    await asyncio.sleep(0.05)
                    busy = brain.talk_lock.locked() or bool(brain.inbox)
                    # (a quick answer can take and free the lock between two looks: what she said or did counts too)
                    seen_busy = seen_busy or busy or len(trace["says"]) + len(trace["states"]) > said_before
                    if seen_busy and not busy and time.monotonic() - last_msg[0] > 0.8:
                        break
                    if not seen_busy and time.monotonic() - started > 5:
                        break  # (System 0 answered alone, or nothing came)
                else:
                    trace["error"] = "timed out after %ds" % timeout
                    break
            task.cancel()
    trace["calls"] = summarize_calls(gw.calls)
    trace["prompt"] = last_user_message(gw.calls)
    trace["first_words"] = trace["says"][0]["t"] if trace["says"] else None
    trace["total"] = trace["says"][-1]["t"] if trace["says"] else None
    return trace


ABILITIES = ["find_ore", "find_animal", "find_block", "find_player", "locate", "guide", "stop_guide", "follow_player",
             "protect", "place_torch", "harvest", "build", "give_item", "give_effect", "set_time", "set_weather",
             "command"]  # (the mod's powers for "all-powerful, magic" since 2026-11-13: Minecraft commands too)


def merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def last_user_message(calls):
    for c in calls:
        if c["kind"] in ("reply", "own"):
            msgs = c["request"].get("messages") or []
            users = [m for m in msgs if m.get("role") == "user"]
            return users[-1]["content"] if users else ""
    return ""


def summarize_calls(calls):
    talk = [c for c in calls if c["kind"] in ("reply", "own", "")]
    out = {"ai_calls": len(talk), "forced": [], "offered": [], "tokens_in": 0, "tokens_out": 0, "cached_in": 0,
           "estimated": False, "sections": {}}
    for i, c in enumerate(talk):
        req = c["request"]
        tc = req.get("tool_choice")
        if isinstance(tc, dict):
            out["forced"].append((tc.get("function") or {}).get("name"))
        if i == 0:
            out["offered"] = [(t.get("function") or {}).get("name") for t in req.get("tools") or []]
            out["sections"] = sections(req)
        u = c.get("usage") or {}
        if u.get("prompt_tokens"):
            out["tokens_in"] += u["prompt_tokens"]
            out["tokens_out"] += u.get("completion_tokens") or 0
            out["cached_in"] += (u.get("prompt_tokens_details") or {}).get("cached_tokens") or u.get("cached_tokens") or 0
        else:
            out["estimated"] = True
            out["tokens_in"] += len(json.dumps(req.get("messages"))) // 4 + len(json.dumps(req.get("tools") or [])) // 4
    return out


SECTION = re.compile(r"^\[([^\]]+)\]\n", re.M)


def sections(req):
    """Characters per part of the prompt (system, history, each [section] of the newest message, tools)."""
    msgs = req.get("messages") or []
    out = {"tools": len(json.dumps(req.get("tools") or [])), "system": 0, "history": 0}
    for i, m in enumerate(msgs):
        content = m.get("content") or ""
        if not isinstance(content, str):
            content = json.dumps(content)
        if m.get("role") == "system":
            out["system"] += len(content)
        elif i == len(msgs) - 1 and m.get("role") == "user":
            parts = SECTION.split(content)
            out["history"] += len(parts[0])  # (an earlier assistant line merged into this message)
            for name, body in zip(parts[1::2], parts[2::2]):
                out[name] = out.get(name, 0) + len(body)
        else:
            out["history"] += len(content) + len(json.dumps(m.get("tool_calls") or ""))
    return out


# ---------------------------------------------------------------------------------------- checks

def matches(got, want):
    """want: {key: pattern}; a pattern is a regex (case-insensitive search) or a non-string value."""
    for k, v in (want or {}).items():
        g = got.get(k) if isinstance(got, dict) else None
        if isinstance(v, str):
            if g is None or not re.search(v, str(g), re.I):
                return False
        elif v is None:
            if g not in (None, ""):
                return False
        elif g != v:
            return False
    return True


def check(expect, trace):
    """[(name, ok, detail)] for one layer of expectations."""
    out = []
    said = " ".join(s["text"] for s in trace["says"])
    for want in expect.get("acts", []):
        out.append(("act %s" % json.dumps(want), any(matches(a, want) for a in trace["acts"]),
                    "acts: %s" % json.dumps(trace["acts"])[:200]))
    for want in expect.get("no_acts", []):
        out.append(("no act %s" % json.dumps(want), not any(matches(a, want) for a in trace["acts"]),
                    "acts: %s" % json.dumps(trace["acts"])[:200]))
    for key, where in (("tools", "tools"), ("game", "game")):
        name_key = "name" if key == "tools" else "action"
        for want in expect.get(key, []):  # ("ok": true/false: and the power worked / failed)
            ok = any(t[name_key] == want["name"] and matches(t["args"], want.get("args")) and
                     ("ok" not in want or bool((t.get("result") or {}).get("ok", True)) == want["ok"])
                     for t in trace[where])
            out.append(("%s %s %s" % ("uses" if key == "tools" else "game gets", want["name"],
                                      json.dumps(want.get("args") or {})), ok, calls_text(trace[where], name_key)))
        for want in expect.get("no_" + key, []):
            bad = [t for t in trace[where] if t[name_key] == want["name"] and matches(t["args"], want.get("args"))]
            out.append(("%s %s %s" % ("never uses" if key == "tools" else "game never gets", want["name"],
                                      json.dumps(want.get("args") or {})), not bad, calls_text(bad, name_key)))
    for name, most in (expect.get("max_uses") or {}).items():
        n = sum(1 for t in trace["tools"] if t["name"] == name)
        out.append(("at most %d x %s" % (most, name), n <= most, "%d times" % n))
    for name in expect.get("not_forced", []):
        out.append(("System 0 doesn't force %s" % name, name not in trace["calls"]["forced"],
                    "forced: %s" % trace["calls"]["forced"]))
    for name in expect.get("forced", []):
        out.append(("System 0 forces %s" % name, name in trace["calls"]["forced"], "forced: %s" % trace["calls"]["forced"]))
    for pat in expect.get("prompt_has", []):
        out.append(("prompt has /%s/" % pat, bool(re.search(pat, trace["prompt"] or "", re.I)), ""))
    for pat in expect.get("prompt_not", []):
        out.append(("prompt lacks /%s/" % pat, not re.search(pat, trace["prompt"] or "", re.I), ""))
    for pat in expect.get("said", []):
        out.append(("says /%s/" % pat, bool(re.search(pat, said, re.I)), said[:200]))
    for pat in expect.get("said_not", []):
        m = re.search(pat, said, re.I)
        out.append(("never says /%s/" % pat, not m, said[:200]))
    if expect.get("answers"):
        out.append(("answers in words", bool(said.strip()), trace.get("error") or ""))
    return out


def calls_text(calls, name_key):
    return "; ".join("%s(%s)%s" % (t[name_key], json.dumps(t["args"])[:80], "" if (t.get("result") or {}).get("ok", True)
                                   else " FAILED") for t in calls)[:300]


# ---------------------------------------------------------------------------------------- the run

def load_cases(only=None):
    cases = []
    for path in sorted(glob.glob(os.path.join(HERE, "cases", "*.json"))):
        with open(path, encoding="utf-8") as fh:
            for c in json.load(fh)["cases"]:
                c["file"] = os.path.basename(path)
                cases.append(c)
    if only:
        cases = [c for c in cases if any(o in c["id"] for o in only.split(","))]
    return cases


def real_settings():
    """The player's gateway address and AI settings (read before KINDRED_HOME points elsewhere)."""
    import tomllib
    home = os.environ.get("KINDRED_HOME") or os.path.join(os.path.expanduser("~"), ".kindred-spirit")
    try:
        with open(os.path.join(home, "brain.toml"), "rb") as fh:
            t = tomllib.load(fh)
    except OSError:
        t = {}
    gw = t.get("gateway") or {}
    ai = {k: v for k, v in (t.get("ai") or {}).items() if k in ("model", "temperature", "max_tokens", "reasoning_effort",
                                                                  "history_turns")}
    return gw.get("url", "http://127.0.0.1:11437/v1"), gw.get("key", ""), ai


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--mode", choices=("stub", "local", "live"), default="stub")
    p.add_argument("--only", help="case ids (or parts of them), comma separated")
    p.add_argument("--repeat", type=int, default=1, help="run each case this many times (live: the AI varies)")
    p.add_argument("--judge", action="store_true", help="live: an AI judge reads each answer for character")
    p.add_argument("--judge-kind", default="reflect", help="the gateway's call kind for the judge (reflect = Claude)")
    p.add_argument("--brain", help="another checkout's brain folder to evaluate (default: this one)")
    p.add_argument("--abilities", help="her powers, comma separated (default: the ones the mod had on 2026-11-12)")
    p.add_argument("--label", default="now")
    p.add_argument("--json", help="where to write the results (default evals/results/<label>-<mode>.json)")
    p.add_argument("--list", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    a = p.parse_args(argv)

    upstream, key, ai = real_settings()
    scratch = tempfile.mkdtemp(prefix="kindred-eval-home-")
    os.makedirs(os.path.join(scratch, "logs"), exist_ok=True)
    os.environ["KINDRED_HOME"] = scratch                       # her settings and files: a scratch folder,
    os.environ["KINDRED_SESSION_DIR"] = os.path.join(scratch, "sessions")  # never the player's own
    brain_dir = os.path.abspath(a.brain or os.path.dirname(HERE))
    sys.path.insert(0, brain_dir)
    if not a.quiet:
        import logging
        logging.basicConfig(level=logging.WARNING)

    cases = load_cases(a.only)
    if a.abilities:
        ABILITIES[:] = [x.strip() for x in a.abilities.split(",") if x.strip()]
    if a.list:
        for c in cases:
            print("%-34s %-12s %-11s %s" % (c["id"], c.get("play", "singleplayer"), c.get("who", "player"),
                                            (c.get("say") or c["turns"][0]["say"])[:70]))
        return 0
    from .gateway import EvalGateway
    gw = EvalGateway(a.mode, upstream, key, os.path.join(os.path.dirname(brain_dir), "services"))
    results = []
    try:
        for c in cases:
            for n in range(a.repeat):
                try:
                    trace = asyncio.run(play(c, gw, a.mode, {"ai": ai} if a.mode == "live" else {}))
                except Exception as e:  # (one broken case doesn't stop the others)
                    trace = {"error": "%s: %s" % (type(e).__name__, e), "says": [], "acts": [], "tools": [], "game": [],
                             "calls": {"ai_calls": 0, "forced": [], "offered": [], "tokens_in": 0}, "prompt": "",
                             "first_words": None, "total": None}
                expect = c.get("expect") or {}
                r = {"id": c["id"], "run": n, "who": c.get("who", "player"), "say": c.get("say") or c["turns"][0]["say"],
                     "play": c.get("play", "singleplayer"), "trace": trace,
                     "brain": check(expect.get("brain") or {}, trace) if not trace.get("error") else
                     [("runs", False, trace["error"])],
                     "ai": check(expect.get("ai") or {}, trace) if a.mode == "live" and not trace.get("error") else []}
                if a.judge and a.mode == "live" and not trace.get("error"):
                    from .judge import judge
                    r["judge"] = judge(c, trace, upstream, key, a.judge_kind)
                results.append(r)
                if not a.quiet:
                    show(r)
    finally:
        gw.close()
    summary = summarize(results, a.mode)
    print_summary(summary)
    out = a.json or os.path.join(HERE, "results", "%s-%s.json" % (a.label, a.mode))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"label": a.label, "mode": a.mode, "brain": brain_dir, "time": time.strftime("%Y-%m-%d %H:%M"),
                   "summary": summary, "results": results}, fh, indent=1, default=str)
    print("saved", out)
    return 0


def show(r):
    said = " / ".join(s["text"] for s in r["trace"]["says"]) or "(nothing)"
    tools_ = ", ".join("%s%s" % (t["name"], "" if (t.get("result") or {}).get("ok", True) else "✗")
                       for t in r["trace"]["tools"])
    print("\n%s  [%s] %s" % (r["id"], r["who"], r["say"][:80]))
    print("   Pip: %s" % said[:240])
    if tools_ or r["trace"]["acts"]:
        print("   tools: %s   acts: %s" % (tools_ or "-", json.dumps(r["trace"]["acts"])[:120]))
    for layer in ("brain", "ai"):
        for name, ok, detail in r[layer]:
            print("   %s %-5s %s%s" % ("✓" if ok else "✗", layer, name, "" if ok else "   <- " + str(detail)[:160]))
    j = r.get("judge")
    if j:
        for k, v in j.get("rubric", {}).items():
            if not v.get("pass"):
                print("   ✗ judge %s: %s" % (k, v.get("why", "")[:160]))
        for q in j.get("case", []):
            print("   %s judge %s%s" % ("✓" if q.get("pass") else "✗", q.get("q", "")[:90],
                                        "" if q.get("pass") else "   <- " + q.get("why", "")[:140]))


def summarize(results, mode):
    def rate(layer):
        checks = [ok for r in results for _, ok, _ in r[layer]]
        cases = [all(ok for _, ok, _ in r[layer]) for r in results if r[layer]]
        return {"checks": "%d/%d" % (sum(checks), len(checks)), "cases": "%d/%d" % (sum(cases), len(cases)),
                "case_rate": round(sum(cases) / len(cases), 2) if cases else None}
    out = {"mode": mode, "runs": len(results), "brain": rate("brain")}
    out["by_play"] = {}  # (singleplayer first: most play is alone with her; then LAN with friends)
    for play in ("singleplayer", "lan"):
        rs = [r for r in results if r.get("play") == play]
        if rs:
            ok = [all(c[1] for c in r["brain"] + r["ai"]) for r in rs]
            out["by_play"][play] = "%d/%d" % (sum(ok), len(ok))
    if mode == "live":
        out["ai"] = rate("ai")
        fw = [r["trace"]["first_words"] for r in results if r["trace"].get("first_words") is not None]
        tot = [r["trace"]["total"] for r in results if r["trace"].get("total") is not None]
        calls = [r["trace"]["calls"]["ai_calls"] for r in results]
        toks = [r["trace"]["calls"]["tokens_in"] for r in results if r["trace"]["calls"]["ai_calls"]]
        out["latency"] = {"first_words_median": med(fw), "first_words_max": max(fw) if fw else None,
                          "last_line_median": med(tot)}
        cached = sum(r["trace"]["calls"].get("cached_in", 0) for r in results)
        out["per_answer"] = {"ai_calls_mean": round(sum(calls) / len(calls), 2) if calls else None,
                             "tokens_in_median": med(toks),
                             "cached_share": round(cached / max(1, sum(toks)), 2)}
    judged = [r["judge"] for r in results if r.get("judge")]
    if judged:
        keys = sorted({k for j in judged for k in j.get("rubric", {})})
        out["judge"] = {k: round(sum(1 for j in judged if j["rubric"].get(k, {}).get("pass")) /
                                 max(1, sum(1 for j in judged if k in j["rubric"])), 2) for k in keys}
        qs = [q.get("pass") for j in judged for q in j.get("case", [])]
        out["judge"]["case_questions"] = "%d/%d" % (sum(1 for q in qs if q), len(qs))
        out["judge"]["character_score"] = round(statistics.mean(
            sum(1 for v in j["rubric"].values() if v.get("pass")) / max(1, len(j["rubric"])) for j in judged), 2)
    out["failing"] = sorted({r["id"] for r in results
                             if not all(ok for _, ok, _ in r["brain"] + r["ai"])})
    return out


def med(xs):
    return round(statistics.median(xs), 2) if xs else None


def print_summary(s):
    print("\n==== %s mode, %d runs" % (s["mode"], s["runs"]))
    print("brain checks %s, cases passing %s" % (s["brain"]["checks"], s["brain"]["cases"]))
    print("cases passing every check, by kind of play: %s" % ", ".join("%s %s" % kv for kv in s.get("by_play", {}).items()))
    if "ai" in s:
        print("ai checks    %s, cases passing %s" % (s["ai"]["checks"], s["ai"]["cases"]))
        print("first words: median %ss, max %ss; last line median %ss" % (
            s["latency"]["first_words_median"], s["latency"]["first_words_max"], s["latency"]["last_line_median"]))
        print("per answer: %s AI calls, %s tokens in (median), %s of tokens in served from the cache" % (
            s["per_answer"]["ai_calls_mean"], s["per_answer"]["tokens_in_median"], s["per_answer"]["cached_share"]))
    if "judge" in s:
        print("judge: %s" % json.dumps(s["judge"]))
    if s["failing"]:
        print("failing: %s" % ", ".join(s["failing"]))


if __name__ == "__main__":
    sys.exit(main())
