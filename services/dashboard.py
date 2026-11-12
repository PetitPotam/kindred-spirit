#!/usr/bin/env python3
"""Kindred dashboard: see what your companion is doing, thinking and remembering, live.

    python3 services/dashboard.py            then open http://127.0.0.1:11440

On this computer only (it listens on 127.0.0.1); it only accepts changes from its own page. Everything it shows already exists on
disk or behind the gateway; nothing new is collected:

  live      the brain's state (logs/brain-state.json): bond, mood score, powers waking up, offers,
            the conversation window and what was last sent to the AI (memories, feelings, game)
  events    what happened, from the brain's log: what you said and her answers, tools, notices...
  ai        every AI call through the gateway (logs/gateway.jsonl): kind, latency, tokens, the
            prompt's parts, tools offered, special instructions applied
  services  speech-to-text and voice calls (logs/gateway.log)
  memory    the memory store, per world, through the gateway's memory API (works for remote too)
  settings  the gateway's effective settings and special instructions, brain.toml, the mod's config;
            a short list of them can be changed here (brain: picked up live; gateway: next call)
  sessions  each play session (logs/sessions): the timeline, what went in and out of the AI, and
            her voice for every line, to play again

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
SESSIONS = os.path.join(LOGS, "sessions")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "brain"))
from kindred import config as brain_config  # noqa: E402  (her settings, with their defaults)

# what can be changed from the dashboard: (where, path, label, type, choices or None)
EDITABLE = [
    ("brain", "name", "Her name", "text", None),
    ("brain", "behaviour.alerts", "Danger warnings (creepers, lava, drops, low health)", "bool", None),
    ("brain", "behaviour.greet_on_join", "Greets you when you join", "bool", None),
    ("brain", "behaviour.small_talk_minutes", "Small talk when it's quiet, every N minutes (0 = never)", "int", None),
    ("brain", "behaviour.fill_silence_after", "A 'hmm' when an answer takes longer than N seconds (0 = never)", "float", None),
    ("brain", "heart.temperament", "Temperament", "choice", ["default", "thick-skinned", "sensitive", "forgiving"]),
    ("brain", "heart.amnesia", "Discovers her powers with you", "bool", None),
    ("brain", "heart.awakening", "A new power wakes up", "choice", ["slow", "instant"]),
    ("brain", "heart.curiosity", "Comments on what she notices", "bool", None),
    ("brain", "heart.auto_protect", "Protects you without being asked", "bool", None),
    ("brain", "heart.pranks", "Friendly pranks", "bool", None),
    ("brain", "heart.fibs", "Playful fibs she owns up to", "bool", None),
    ("brain", "heart.play_fights", "Play-fights between close friends", "bool", None),
    ("brain", "heart.can_vanish", "Leaves for a while when mistreated", "bool", None),
    ("brain", "heart.mischief_when_angry", "Mischief when she's cross", "choice", ["off", "mild", "spicy"]),
    ("brain", "heart.weather_follows_mood", "Her tears bring rain", "bool", None),
    ("brain", "voice.enabled", "Speaks aloud (off: subtitles only)", "bool", None),
    ("brain", "ai.temperature", "How free her words are (0.2 steady - 1.2 wild)", "float", None),
    ("gateway", "upstream", "AI for her conversation", "upstream", None),
    ("gateway", "by_kind.reflect", "AI for her deeper thinking (learning, her story)", "upstream", None),
    ("gateway", "upstreams.gemini.by_kind.reply.model", "Gemini model for her replies", "text", None),
    ("gateway", "tts.use", "Voice", "choice", None),
    ("gateway", "tts.providers.local_kokoro.voice", "Kokoro voice", "text", None),
    ("gateway", "tts.providers.local_kokoro.speed", "Kokoro speed", "float", None),
    ("gateway", "tts.providers.local_kokoro.pitch", "Kokoro pitch", "float", None),
    ("gateway", "stt.use", "Hearing you (speech-to-text)", "choice", None),
]


def _get(d, path):
    for k in path.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _set(d, path, value):
    keys = path.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def editable():
    """The changeable settings with their current values (and the choices for each)."""
    brain = brain_config.load()
    gw = kindred_gateway.load()
    out = []
    for where, path, label, kind, choices in EDITABLE:
        src = brain if where == "brain" else gw
        if kind == "upstream":
            choices = [""] + sorted(gw.get("upstreams") or {}) if path.startswith("by_kind") else sorted(gw.get("upstreams") or {})
            kind = "choice"
        elif kind == "choice" and choices is None:
            choices = sorted((_get(gw, path.rsplit(".", 1)[0]) or {}).get("providers") or {})
        out.append({"where": where, "path": path, "label": label, "type": kind, "choices": choices,
                    "value": _get(src, path)})
    return out


def change_settings(changes):
    """Apply changes from the dashboard: only the listed settings, with their types checked."""
    allowed = {(w, p): (k, c) for w, p, _, k, c in EDITABLE}
    current = {(e["where"], e["path"]): e for e in editable()}
    brain_over, gw_changes, done = brain_config.read_overrides(), [], []
    for ch in changes or []:
        key = (ch.get("where"), ch.get("path"))
        if key not in allowed:
            raise ValueError("%s can't be changed here" % (key,))
        kind, choices = current[key]["type"], current[key]["choices"]
        v = ch.get("value")
        if kind == "bool":
            v = bool(v) if not isinstance(v, str) else v.lower() in ("1", "true", "yes", "on")
        elif kind == "int":
            v = int(float(v))
        elif kind == "float":
            v = float(v)
        elif kind == "choice":
            if v not in choices:
                raise ValueError("%s must be one of %s" % (key[1], ", ".join(map(str, choices))))
        else:
            v = str(v)[:80]
        if key[0] == "brain":
            _set(brain_over, key[1], v)
        else:
            gw_changes.append((key[1], v))
        done.append({"where": key[0], "path": key[1], "value": v})
    if any(d["where"] == "brain" for d in done):
        tmp = brain_config.OVERRIDES + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(brain_over, fh, indent=1)
        os.replace(tmp, brain_config.OVERRIDES)
    if gw_changes:
        def apply(st):
            for path, v in gw_changes:
                if path == "by_kind.reflect" and not v:
                    (st.get("by_kind") or {}).pop("reflect", None)
                else:
                    _set(st, path, v)
        kindred_gateway.change(apply)
    return {"changed": done}


# ---------------------------------------------------------------------- sessions

SAFE = re.compile(r"^[\w.-]+$")


def sessions_list(limit=40):
    out = []
    try:
        names = sorted((f for f in os.listdir(SESSIONS) if f.endswith(".jsonl")), reverse=True)[:limit]
    except OSError:
        return []
    for f in names:
        sid = f[:-6]
        rows = _read_jsonl(os.path.join(SESSIONS, f))
        if not rows:
            continue
        start = rows[0]
        out.append({"id": sid, "world": (start.get("world") or "").split(":", 1)[-1], "at": start.get("at"),
                    "minutes": round(rows[-1].get("t", 0) / 60, 1),
                    "you": sum(1 for r in rows if r.get("kind") == "you"),
                    "pip": sum(1 for r in rows if r.get("kind") == "pip"),
                    "own": sum(1 for r in rows if r.get("kind") == "pip" and r.get("source") == "own"),
                    "errors": sum(1 for r in rows if r.get("kind") == "error")})
    return out


def _read_jsonl(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return rows


def session_one(sid):
    """A session's timeline, and the AI calls made during it (what went in, what came out)."""
    if not SAFE.match(sid or ""):
        raise ValueError("bad session id")
    rows = _read_jsonl(os.path.join(SESSIONS, sid + ".jsonl"))
    at = (rows[0].get("at") if rows else None) or 0
    end = at + (rows[-1].get("t", 0) if rows else 0) + 10
    calls = []
    for c in _read_jsonl(os.path.join(LOGS, "gateway.jsonl")):
        try:
            t = time.mktime(time.strptime(c.get("time", ""), "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            continue
        if at and at - 5 <= t <= end:
            msgs = c.get("messages") or []
            last_user = next((m for m in reversed(msgs) if m.get("role") == "user"), {})
            content = last_user.get("content")
            if isinstance(content, list):
                content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            calls.append({"t": round(t - at, 1), "kind": c.get("kind"), "model": c.get("model"),
                          "seconds": c.get("seconds"), "player": c.get("player"), "reply": c.get("reply"),
                          "input": (content or "")[-6000:], "tools": [x for x in (c.get("tools") or [])][:20],
                          "actions": c.get("actions"), "tokens_in": c.get("tokens_in"), "tokens_out": c.get("tokens_out")})
    md = os.path.join(SESSIONS, sid + ".md")
    summary = open(md, encoding="utf-8").read() if os.path.exists(md) else ""
    return {"id": sid, "events": rows, "calls": calls, "summary": summary}

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


# ---------------------------------------------------------------------- knowledge (what the world remembers)

def knowledge(op, **body):
    """The knowledge base through the gateway (search, stats, sources, learn)."""
    state = kindred_gateway.load()
    key = kindred_gateway.key_of(state.get("access_key"), "") if state.get("access_key") else ""
    req = urllib.request.Request(GATEWAY + "/knowledge/" + op, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    if key:
        req.add_header("Authorization", "Bearer " + key)
    with urllib.request.urlopen(req, timeout=60 if op == "learn" else 15) as r:
        return json.loads(r.read())


def knowledge_overview():
    """Stats and sources (gateway), plus recent pages, the learning log and settings (the file, read-only)."""
    out = {"stats": knowledge("stats"), "sources": knowledge("sources").get("sources", []), "pages": [], "log": []}
    try:
        import sqlite3
        from knowledge import learn as kb_learn, sources as kb_sources
        out["learning"] = kb_learn.settings(kb_sources.knowledge_dir())
        db = sqlite3.connect("file:%s?mode=ro" % out["stats"]["path"], uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        out["pages"] = [dict(r) for r in db.execute(
            "select p.title, p.url, p.source, p.fetched, count(c.id) as chunks from pages p left join chunks c "
            "on c.page_id = p.id group by p.id order by p.fetched desc limit 60")]
        out["log"] = [dict(r) for r in db.execute(
            "select t, query, status, pages, chunks, seconds from learn_log order by t desc limit 30")]
        db.close()
    except Exception as e:  # the overview still shows what the gateway gave
        out["error"] = str(e)
    return out


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
            if url.path == "/api/sim/token":  # the simulator talks to her brain like the game does (this computer only)
                with open(os.path.join(DIR, "token"), encoding="utf-8") as fh:
                    return self.send(200, {"token": fh.read().strip()})
            if url.path == "/api/settings/editable":
                return self.send(200, {"settings": editable()})
            if url.path == "/api/sessions":
                return self.send(200, {"sessions": sessions_list()})
            if url.path == "/api/sessions/one":
                return self.send(200, session_one(q.get("id", "")))
            if url.path == "/api/knowledge":
                return self.send(200, knowledge_overview())
            if url.path == "/api/knowledge/section":
                return self.send(200, knowledge("section", chunk_id=int(q.get("id", 0)), max_chars=100000))
            if url.path == "/api/knowledge/search":
                return self.send(200, knowledge("search", query=q.get("q", ""), k=8, max_chars=700))
            return self.send(404, {"error": "not found"})
        except (urllib.error.URLError, OSError) as e:
            return self.send(502, {"error": "the gateway isn't reachable (%s): is it running?" % getattr(e, "reason", e)})


def _post(handler):
    """What the dashboard can change: the listed settings, and asking the knowledge base to learn."""
    url = urlparse(handler.path)
    if url.path not in ("/api/knowledge/learn", "/api/settings", "/api/speak"):
        return handler.send(404, {"error": "not found"})
    if handler.headers.get("Origin") not in (None, "http://%s:%d" % (HOST, PORT), "http://localhost:%d" % PORT):
        return handler.send(403, {"error": "only from the dashboard itself"})
    body = json.loads(handler.rfile.read(int(handler.headers.get("Content-Length") or 0)) or b"{}")
    if url.path == "/api/speak":  # play a line again: her voice, made again from the text
        req = urllib.request.Request(GATEWAY + "/audio/speech", method="POST", headers={"Content-Type": "application/json"},
                                     data=json.dumps({"input": str(body.get("text", ""))[:600],
                                                      "style": str(body.get("style", ""))[:20]}).encode())
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return handler.send(200, r.read(), "audio/wav")
        except (urllib.error.URLError, OSError) as e:
            return handler.send(502, {"error": str(getattr(e, "reason", e))})
    if url.path == "/api/settings":
        try:
            return handler.send(200, change_settings(body.get("changes")))
        except (ValueError, TypeError) as e:
            return handler.send(400, {"error": str(e)})
    try:
        return handler.send(200, knowledge("learn", query=str(body.get("query", ""))[:300]))
    except (urllib.error.URLError, OSError) as e:
        return handler.send(502, {"error": str(getattr(e, "reason", e))})


Handler.do_POST = _post


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("Kindred dashboard on http://%s:%d" % (HOST, PORT), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
