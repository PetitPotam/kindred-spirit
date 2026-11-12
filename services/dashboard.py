#!/usr/bin/env python3
"""Kindred dashboard: see what your companion is doing, thinking and remembering, live.

    python3 services/dashboard.py            then open http://127.0.0.1:11440

Read-only, on this computer only (it listens on 127.0.0.1). Everything it shows already exists on
disk or behind the gateway; nothing new is collected:

  live      the brain's state (logs/brain-state.json): bond, mood score, powers waking up, offers,
            the conversation window and what was last sent to the AI (memories, feelings, game)
  events    what happened, from the brain's log: what you said and her answers, tools, notices...
  ai        every AI call through the gateway (logs/gateway.jsonl): kind, latency, tokens, the
            prompt's parts, tools offered, special instructions applied
  services  speech-to-text and voice calls (logs/gateway.log)
  memory    the memory store, per world, through the gateway's memory API (works for remote too)
  settings  the gateway's effective settings and special instructions, brain.toml, the mod's config

Standard library only, like the gateway.
"""
import json
import os
import re
import sys
import time
import tomllib
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kindred_gateway  # noqa: E402  (its settings, defaults and file locations)

HOST = "127.0.0.1"
PORT = int(os.environ.get("KINDRED_DASHBOARD_PORT", "11440"))
DIR = kindred_gateway.DIR
LOGS = kindred_gateway.LOG_DIR
GATEWAY = "http://127.0.0.1:%d/v1" % kindred_gateway.LISTEN_PORT
PAGE = os.path.join(HERE, "dashboard.html")
MOD_CONFIGS = [os.path.expanduser("~/Library/Application Support/minecraft-kindred/config/kindredspirit.json"),
               os.path.expanduser("~/.minecraft-kindred/config/kindredspirit.json"),
               os.path.join(os.environ.get("APPDATA", ""), "minecraft-kindred", "config", "kindredspirit.json")]
# what one million tokens cost (USD), to estimate; change with KINDRED_PRICE_IN / KINDRED_PRICE_OUT
PRICE_IN = float(os.environ.get("KINDRED_PRICE_IN", "0.25"))
PRICE_OUT = float(os.environ.get("KINDRED_PRICE_OUT", "1.50"))


# ---------------------------------------------------------------------- reading files

def tail_lines(path, max_bytes=600_000):
    """The last part of a (possibly big) log file, as lines."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            data = fh.read().decode("utf-8", "replace")
    except OSError:
        return []
    lines = data.splitlines()
    return lines[1:] if size > max_bytes else lines


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def brain_log():
    for name in ("brain.log", "brain.out"):
        p = os.path.join(LOGS, name)
        if os.path.exists(p):
            return p
    return os.path.join(LOGS, "brain.log")


# ---------------------------------------------------------------------- the brain's events

LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ (\w+) (.*)$")
EVENTS = [
    ("chat", re.compile(r"^you: (?P<you>.*?) \| (?P<name>[^:]+): \[(?P<mood>\w+)\](?: \{(?P<gesture>\w+)\})? (?P<said>.*)$")),
    ("tool", re.compile(r"^tool (?P<tool>\w+)\((?P<args>.*?)\) -> (?P<result>.*)$")),
    ("notice", re.compile(r"^noticed (?P<event>\w+) \((?P<detail>.*?)\): (?P<said>.*)$")),
    ("own", re.compile(r"^on her own: (?P<said>.*)$")),
    ("awakening", re.compile(r"^awakening (?P<power>\w+): (?P<plan>.*)$")),
    ("bond", re.compile(r"^bond (?P<change>[+-][\d.]+) \((?P<why>.*?)\) -> (?P<value>\d+) (?P<level>.*)$")),
    ("act", re.compile(r"^acting on: (?P<what>.*)$")),
    ("check", re.compile(r"^claimed an action without doing it, asking again: (?P<said>.*)$")),
    ("learn", re.compile(r"^learned (?P<n>\d+) new things?(?:; diary: (?P<diary>.*))?$")),
    ("game", re.compile(r"^(?P<what>game connected|game disconnected|a new game connected.*|mod .* on Minecraft .*|abilities: .*)$")),
    ("protect", re.compile(r"^auto-protect: (?P<result>.*)$")),
    ("weather", re.compile(r"^mood weather (?P<weather>\w+): (?P<result>.*)$")),
    ("pet", re.compile(r"^(?P<what>petted)$")),
]


def events(limit=400):
    out = []
    for line in tail_lines(brain_log()):
        m = LINE.match(line)
        if not m:
            continue
        when, level, msg = m.groups()
        if level == "DEBUG" or msg.startswith(("connection open", "connection closed")):
            continue
        ev = {"time": when, "level": level, "kind": "info", "text": msg}
        if level in ("WARNING", "ERROR", "CRITICAL"):
            ev["kind"] = "problem"
        else:
            for kind, rx in EVENTS:
                e = rx.match(msg)
                if e:
                    ev["kind"] = kind
                    ev.update({k: v for k, v in e.groupdict().items() if v is not None})
                    break
        out.append(ev)
    return out[-limit:]


# ---------------------------------------------------------------------- AI calls (gateway.jsonl)

SECTIONS = ("Game state right now", "What you see and sense right now", "What you remember",
            "How you feel about the player", "Your settings", "What you can do", "Player")


def split_prompt(text):
    """The last user message the brain sends is made of [Sections]: split them for display."""
    parts, current = {}, None
    for line in (text or "").splitlines():
        m = re.match(r"^\[(.+)\]$", line.strip())
        if m and m.group(1) in SECTIONS:
            current = m.group(1)
            parts[current] = []
        elif current:
            parts[current].append(line)
    return {k: "\n".join(v).strip() for k, v in parts.items()}


def kind_of(player, parts):
    if player.startswith("Already known"):
        return "reflect"
    if player.startswith("Summary so far"):
        return "fold"
    said = parts.get("Player", "")
    if said.startswith("(") and said.endswith(")"):
        return "own"  # an instruction, not something you said: greeting, notice, small talk, awakening
    return "reply" if parts else "other"


def ai_calls(limit=300):
    out = []
    for line in tail_lines(os.path.join(LOGS, "gateway.jsonl"), 3_000_000)[-limit:]:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        player = r.get("player") or ""
        parts = split_prompt(player)
        r["kind"] = r.get("kind") or kind_of(player, parts)  # recorded by the gateway since it knows
        r["parts"] = parts
        r["said"] = parts.get("Player") or player[:400]
        if not parts:
            r["prompt"] = player[-4000:]
        r.pop("player", None)
        out.append(r)
    return out


def totals(calls):
    tin = sum(c.get("tokens_in") or 0 for c in calls)
    tout = sum(c.get("tokens_out") or 0 for c in calls)
    measured = [c for c in calls if c.get("tokens_in")]
    return {"calls": len(calls), "tokens_in": tin, "tokens_out": tout, "measured": len(measured),
            # the provider's own figure when it gives one (the Claude CLI does), else list prices
            "cost": round(sum(c["cost_usd"] if c.get("cost_usd") is not None else
                              (c.get("tokens_in") or 0) / 1e6 * PRICE_IN + (c.get("tokens_out") or 0) / 1e6 * PRICE_OUT
                              for c in calls), 4),
            "price": {"in": PRICE_IN, "out": PRICE_OUT},
            "avg_seconds": round(sum(c.get("seconds") or 0 for c in calls) / len(calls), 2) if calls else 0}


# ---------------------------------------------------------------------- speech and voice (gateway.log)

SERVICE = [
    ("ai", re.compile(r"^ai (?P<provider>\S+) (?P<model>\S+) (?P<seconds>[\d.]+)s \| .*$")),
    ("stt", re.compile(r"^stt (?P<provider>\S+) (?P<seconds>[\d.]+)s: (?P<text>.*)$")),
    ("tts", re.compile(r"^tts (?P<provider>\S+) (?P<seconds>[\d.]+)s, (?P<chars>\d+) chars$")),
    ("start", re.compile(r"^kindred gateway on (?P<url>\S+) \| (?P<parts>.*)$")),
]


def services(limit=300):
    out = []
    for line in tail_lines(os.path.join(LOGS, "gateway.log")):
        m = LINE.match(line)
        if not m:
            continue
        when, level, msg = m.groups()
        ev = {"time": when, "level": level, "kind": "problem" if level in ("WARNING", "ERROR") else "other", "text": msg}
        for kind, rx in SERVICE:
            e = rx.match(msg)
            if e:
                ev["kind"] = kind
                ev.update(e.groupdict())
                break
        out.append(ev)
    return out[-limit:]


# ---------------------------------------------------------------------- memory (through the gateway)

def memory(op, **body):
    state = kindred_gateway.load()
    key = kindred_gateway.key_of(state.get("access_key"), "") if state.get("access_key") else ""
    req = urllib.request.Request(GATEWAY + "/memory/" + op, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    if key:
        req.add_header("Authorization", "Bearer " + key)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def memory_overview(world=None):
    rows = memory("list", limit=5000, all_worlds=True, order="recent")["results"]
    worlds = {}
    for r in rows:
        w = r["world"] or "(every world)"
        worlds.setdefault(w, {}).setdefault(r["kind"], 0)
        worlds[w][r["kind"]] += 1
    try:
        docs = memory("docs").get("docs", [])
    except (urllib.error.URLError, OSError, ValueError):
        docs = []  # an older gateway: restart it to see the saved documents
    now = time.time()
    picked = [r for r in rows if world in (None, "", "all") or (r["world"] or "(every world)") == world]
    for r in picked:
        exp = (r.get("meta") or {}).get("expires")
        r["expired"] = bool(exp and exp < now)
    return {"worlds": worlds, "memories": picked, "docs": docs}


# ---------------------------------------------------------------------- settings

def redact(obj):
    """Keys are shown as where they come from (env:NAME), never as values."""
    if isinstance(obj, dict):
        return {k: (v if not (k in ("key", "access_key") and v and not str(v).startswith("env:")) else "(hidden)")
                if not isinstance(v, (dict, list)) else redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def settings():
    state = kindred_gateway.load()
    in_use = {"ai": state.get("upstream")}
    for section in ("stt", "tts", "embeddings", "memory"):
        in_use[section] = (state.get(section) or {}).get("use")
    try:
        with open(os.path.join(DIR, "brain.toml"), "rb") as fh:
            brain = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as e:
        brain = {"error": str(e)}
    mod = next((read_json(p) for p in MOD_CONFIGS if os.path.exists(p)), None)
    secrets = []
    try:
        with open(kindred_gateway.SECRETS, encoding="utf-8") as fh:
            secrets = [line.split("=", 1)[0].strip() for line in fh if "=" in line and not line.startswith("#")]
    except OSError:
        pass
    return {
        "in_use": in_use,
        "instructions": {"persona": state.get("persona", ""), "facts": state.get("facts", []),
                         "hint_next": state.get("hint_next", ""), "paused": state.get("paused", False),
                         "model": state.get("model", ""), "temperature": state.get("temperature")},
        "gateway": redact(state), "brain": redact(brain), "mod": mod, "secrets_set": secrets,
    }


def health():
    out = {}
    try:
        with urllib.request.urlopen(GATEWAY.rsplit("/v1", 1)[0] + "/health", timeout=2) as r:
            out["gateway"] = json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError) as e:
        out["gateway"] = {"status": "down", "error": str(getattr(e, "reason", e))}
    st = read_json(os.path.join(LOGS, "brain-state.json"))
    out["brain_age"] = round(time.time() - st["time"], 1) if st and st.get("time") else None
    return out


# ---------------------------------------------------------------------- the web server

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if "json" in ctype or "html" in ctype else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[-1] for k, v in parse_qs(url.query).items()}
        try:
            if url.path in ("/", "/index.html"):
                with open(PAGE, "rb") as fh:
                    return self.send(200, fh.read(), "text/html")
            if url.path == "/api/live":
                return self.send(200, {"brain": read_json(os.path.join(LOGS, "brain-state.json")),
                                       "snapshot": read_json(os.path.join(LOGS, "last-snapshot.json")),
                                       "health": health()})
            if url.path == "/api/events":
                return self.send(200, {"events": events(int(q.get("limit", 400)))})
            if url.path == "/api/ai":
                calls = ai_calls(int(q.get("limit", 300)))
                today = time.strftime("%Y-%m-%d")
                return self.send(200, {"calls": calls, "totals": totals(calls),
                                       "today": totals([c for c in calls if (c.get("time") or "").startswith(today)])})
            if url.path == "/api/services":
                return self.send(200, {"services": services()})
            if url.path == "/api/memory":
                return self.send(200, memory_overview(q.get("world")))
            if url.path == "/api/memory/search":
                world = q.get("world") or None
                body = {"query": q.get("q", ""), "k": 10}
                if world and world != "(every world)":
                    body["world"] = world
                else:
                    body["all_worlds"] = True
                return self.send(200, memory("search", **body))
            if url.path == "/api/memory/doc":
                return self.send(200, memory("doc", key=q.get("key", "")))
            if url.path == "/api/settings":
                return self.send(200, settings())
            return self.send(404, {"error": "not found"})
        except (urllib.error.URLError, OSError) as e:
            return self.send(502, {"error": "the gateway isn't reachable (%s): is it running?" % getattr(e, "reason", e)})


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("Kindred dashboard on http://%s:%d" % (HOST, PORT), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
