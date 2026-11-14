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
  blueprints  the buildings she can build from files, by category, with the pictures and descriptions the
            game writes next to them (catalogue.json); add a file, move one to the trash, bring it back
  setup     the Setup's guided steps (/setup, services/setup_steps.py). The Setup app runs this file as
            `dashboard.py --setup`: on its own port (KINDRED_SETUP_PORT, 11441), from the app's own copy,
            and it quits by itself a while after its page is closed

Standard library only, like the gateway.
"""
import glob
import json
import os
import re
import sys
import threading
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
SESSIONS = os.environ.get("KINDRED_SESSION_DIR") or os.path.join(LOGS, "sessions")  # where the brain writes them
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "brain"))
from kindred import config as brain_config  # noqa: E402  (her settings, with their defaults)
from kindred import blueprints  # noqa: E402  (her blueprint folders and their catalogue)
import setup_steps  # noqa: E402  (the Setup's guided steps)
import setup_models  # noqa: E402  (its voice preview and microphone test)

SETUP_PAGE = os.path.join(HERE, "setup.html")
SETUP_MODE = False  # True when the Setup app runs this (dashboard.py --setup)
SETUP_IDLE_SECONDS = 15 * 60  # setup mode quits this long after the last request (its page polls while open)
last_request = time.time()

# what can be changed from the dashboard: everything in her brain settings (listed from its
# defaults, so new settings appear on their own), the mod's settings, and the gateway's main choices
LABELS = {
    "name": "Her name", "personality": "Extra wishes for her personality (words for the AI)",
    "ai.model": "AI model ('' = the gateway's choice)", "ai.temperature": "How free her words are (0.2 steady - 1.2 wild)",
    "ai.max_tokens": "Longest answer (tokens)", "ai.history_turns": "Turns kept word for word",
    "ai.reasoning_effort": "Thinking for thinking models ('' = default)",
    "voice.enabled": "Speaks aloud (off: subtitles only)", "voice.voice": "Voice ('' = the gateway's choice)",
    "voice.speed": "Voice speed (0 = the gateway's choice)",
    "behaviour.alerts": "Danger warnings (creepers, lava, drops, low health)", "behaviour.greet_on_join": "Greets you when you join",
    "behaviour.small_talk_minutes": "Small talk when it's quiet, every N minutes (0 = never)",
    "behaviour.instinct_lines_after": "Writes her instinct lines N seconds after you join (0 = never)",
    "behaviour.fill_silence_after": "Shows she's thinking after N seconds (0 = never)",
    "behaviour.becoming_minutes": "Rewrites who she's become at most every N minutes",
    "heart.same_companion_in_every_world": "The same companion in every world", "heart.amnesia": "Discovers her powers with you",
    "heart.awakening": "A new power wakes up", "heart.awakening_seconds": "...after about N seconds",
    "heart.favours": "Asks a small favour while a power wakes", "heart.start_bond": "Bond she starts with (0-100)",
    "heart.auto_protect": "Protects you without being asked", "heart.curiosity": "Comments on what she notices",
    "heart.pranks": "Friendly pranks", "heart.fibs": "Playful fibs she owns up to", "heart.block_pranks": "Pranks may borrow a block you placed",
    "heart.mischief_when_angry": "Mischief when she's cross", "heart.can_vanish": "Leaves for a while when mistreated",
    "heart.play_fights": "Play-fights between close friends", "heart.weather_follows_mood": "Her tears bring rain",
    "heart.temperament": "Temperament",
    "skin": "Skin", "power": "What she may do", "style": "How she does it", "allowPranks": "Pranks allowed in game",
    "allowMoodWeather": "Her moods may change the weather", "glow": "Her glow lights the dark", "guideArrow": "Arrow while she leads",
    "guideTrail": "Sparkle trail while she leads", "chatMode": "Which chat messages go to her", "showBond": "Heart meter on changes", "lanGuests": "Friends on your LAN world see her and talk to her", "lanGuestPowers": "Friends may ask for her powers", "follow": "Whom she stays with on LAN ('' = you)", "sharedPip": "In a friend's world: their Pip or your own", "lanVisitors": "A friend's Pip may use her powers in your world", "noBrainHint": "Say how to meet Pip when this computer has no brain",
    "quality": "Quality", "worldSubtitles": "Subtitles above her", "hudCaptions": "Captions on the screen",
    "subtitlesWithHiddenHud": "Subtitles even with the HUD hidden (F1)",
    "hudWithHiddenGui": "Her HUD even with the HUD hidden (F1)", "chatLog": "Conversation in your chat",
    "voiceVolume": "Her voice volume", "offsetRight": "Floats to your right (blocks)", "offsetForward": "Floats ahead (blocks)",
    "offsetUp": "Floats up (blocks)", "size": "Size", "maxRecordSeconds": "Longest push-to-talk (seconds)",
    "life.wander": "Wanders when you stand still", "life.drift": "Drifts beside you", "life.switchSides": "Switches shoulders",
    "life.glances": "Glances around", "life.lookBack": "Looks back at you", "life.eyeContactReactions": "Reacts to eye contact",
    "life.petting": "Can be petted", "life.watchThreats": "Watches monsters", "life.moodGestures": "Gestures with her mood",
    "life.aiGestures": "Plays the AI's gestures", "life.dozeAfterSeconds": "Dozes off after (seconds)",
    "life.turnSlack": "Turn before she follows (degrees)", "life.keepOutOfView": "Keeps out of the middle of your view",
}
# a sentence under the label, for settings whose name doesn't say it all
HELP = {
    "personality": "Added to her character for the AI, in your words. She stays herself: this nudges, it doesn't replace.",
    "ai.model": "Empty: the gateway picks. Set one to try another model for her replies only.",
    "ai.temperature": "Low: steady and predictable. High: surprising, sometimes odd.",
    "ai.max_tokens": "She speaks in short bursts; a higher limit lets the odd answer run longer.",
    "ai.history_turns": "How many recent exchanges go to the AI word for word; older ones are summarized.",
    "voice.voice": "A Kokoro voice name, or a blend like bf_lily*0.7+bf_emma*0.3.",
    "behaviour.fill_silence_after": "If the AI is slow, she shows she's thinking (a look, a hum) after this long.",
    "behaviour.instinct_lines_after": "Her instant reactions (ow!, eep!) rewritten in her own voice, once she knows you a bit.",
    "heart.same_companion_in_every_world": "Off: each world has its own Pip, who meets you fresh.",
    "heart.amnesia": "She wakes up not knowing what she can do, and finds out as you ask.",
    "heart.awakening": "Slow: she senses a power coming before it wakes. Instant: it's just there.",
    "heart.favours": "While a power wakes up, she may ask for something small in return.",
    "heart.start_bond": "15-35 wary, 35-65 friend, 65-85 close, 85+ best friend.",
    "heart.fibs": "Little tall tales she always owns up to.",
    "heart.block_pranks": "A prank may take a block you placed, and always gives it back.",
    "heart.mischief_when_angry": "What she gets up to when you've upset her.",
    "heart.can_vanish": "If you're cruel, she may leave for a while, and come back.",
    "heart.weather_follows_mood": "In singleplayer, a sad Pip can bring rain.",
    "heart.temperament": "How easily she's hurt and how quickly she forgives.",
    "upstream": "Which AI writes her words. Each one is set up in gateway.json.",
    "by_kind.reflect": "Learning, her story, her portrait: rare calls that can use a stronger model. Empty: the same as above.",
    "tts.providers.local_kokoro.pitch": "Above 1 sounds younger and lighter.",
    "power": "Advisor: talks, finds and guides. Helper: also protects you, places torches, chops, builds. All-powerful: also time and weather.",
    "style": "Grounded: uses only what really exists, like your own torches. Magic: can make things appear. Giving items and effects needs Magic (with Helper or All-powerful).",
    "lanGuestPowers": "On: friends on your LAN world can ask her for gifts, effects, finding and leading (within her power and style). Off: they only talk with her.",
    "sharedPip": "Host: in a friend's LAN world you see and share their Pip (their AI and voice; talk in chat). Own: your own Pip and brain.",
    "chatMode": "Auto: everything in singleplayer, only lines starting with her name on servers.",
    "quality": "Auto lowers her detail if your frame rate drops.",
    "showBond": "A small heart meter appears for a moment when the bond changes.",
    "hudCaptions": "Her lines at the bottom of the screen too, like subtitles in a film.",
    "hudWithHiddenGui": "Her heart meter, guide arrow, task line and notices stay when F1 hides the game's HUD (for filming).",
    "offsetRight": "Negative: your left.", "size": "1 is about a slime's head.",
    "life.wander": "Drifts around you when you stand still.", "life.drift": "0 still, 1 normal, 2 lively.",
    "life.switchSides": "Moves to your other shoulder now and then.", "life.glances": "Looks at animals, items and around.",
    "life.lookBack": "Looks at you when you look at her.", "life.eyeContactReactions": "Gets happy or shy when you hold her gaze.",
    "life.petting": "Sneak while looking at her to pet her.", "life.watchThreats": "Turns to watch nearby monsters.",
    "life.moodGestures": "Hops when excited, looks up while thinking.",
    "life.aiGestures": "The little moves the AI adds to her replies (spin, nod, wiggle...).",
    "life.dozeAfterSeconds": "0 = never.", "life.turnSlack": "0 = always right at your side.",
    "life.keepOutOfView": "She never parks in the middle of your view.",
}
CHOICES = {
    ("brain", "heart.temperament"): ["default", "thick-skinned", "sensitive", "forgiving"],
    ("brain", "heart.awakening"): ["slow", "instant"],
    ("brain", "heart.mischief_when_angry"): ["off", "mild", "spicy"],
    ("brain", "ai.reasoning_effort"): ["", "minimal", "low", "medium", "high"],
    ("mod", "power"): ["advisor", "helper", "allpowerful"], ("mod", "style"): ["grounded", "magic"],
    ("mod", "sharedPip"): ["host", "own"],
    ("mod", "chatMode"): ["auto", "all", "name", "command"], ("mod", "quality"): ["auto", "low", "medium", "high"],
}
BRAIN_SECTIONS = ("name", "personality", "ai", "voice", "behaviour", "heart")
MOD_HIDDEN = ("brainHost", "brainPort", "dashboardPort", "tokenFile", "written", "seen")
GATEWAY_EDITABLE = [
    ("upstream", "AI for her conversation", "upstream"),
    ("by_kind.reflect", "AI for her deeper thinking (learning, her story)", "upstream"),
    ("upstreams.gemini.by_kind.reply.model", "Gemini model for her replies", "text"),
    ("upstreams.gemini.by_kind.reply.reasoning_effort", "Gemini thinking for her replies", "effort"),
    ("tts.use", "Voice", "provider"),
    ("tts.providers.local_kokoro.voice", "Kokoro voice", "text"),
    ("tts.providers.local_kokoro.speed", "Kokoro speed", "float"),
    ("tts.providers.local_kokoro.pitch", "Kokoro pitch", "float"),
    ("stt.use", "Hearing you (speech-to-text)", "provider"),
]
TEMPERAMENT_DEFAULT = "default"
# numbers get a slider: (min, max, step)
RANGES = {
    ("brain", "ai.temperature"): (0, 1.5, 0.05), ("brain", "ai.max_tokens"): (60, 600, 10),
    ("brain", "ai.history_turns"): (2, 20, 1), ("brain", "voice.speed"): (0, 2, 0.05),
    ("brain", "behaviour.small_talk_minutes"): (0, 30, 1), ("brain", "behaviour.instinct_lines_after"): (0, 300, 5),
    ("brain", "behaviour.fill_silence_after"): (0, 6, 0.1), ("brain", "behaviour.becoming_minutes"): (5, 120, 5),
    ("brain", "heart.awakening_seconds"): (5, 180, 5), ("brain", "heart.start_bond"): (0, 100, 1),
    ("gateway", "tts.providers.local_kokoro.speed"): (0.7, 1.6, 0.01), ("gateway", "tts.providers.local_kokoro.pitch"): (0.8, 1.25, 0.01),
    ("mod", "voiceVolume"): (0, 2, 0.05), ("mod", "size"): (0.3, 3, 0.05), ("mod", "offsetRight"): (-3, 3, 0.05),
    ("mod", "offsetForward"): (-1, 5, 0.05), ("mod", "offsetUp"): (-2, 3, 0.05), ("mod", "maxRecordSeconds"): (5, 30, 1),
    ("mod", "life.drift"): (0, 2, 0.1), ("mod", "life.dozeAfterSeconds"): (0, 600, 10), ("mod", "life.turnSlack"): (0, 90, 1),
}
GEMINI_MODELS = ["gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-3.1-pro-preview"]
ROOT = os.path.dirname(HERE)


def skin_ids():
    """The skins she can wear: the ones that come with the mod, and the ones you added."""
    ids = set()
    builtin = os.path.join(ROOT, "mod", "src", "main", "resources", "assets", "kindredspirit", "skins")
    mp = mod_path()
    for d in (builtin, os.path.join(os.path.dirname(mp), "kindredspirit", "skins") if mp else None):
        try:
            ids |= {os.path.splitext(f)[0] for f in os.listdir(d) if f.endswith((".json", ".png"))}
        except (OSError, TypeError):
            pass
    return sorted(ids)


def kokoro_voices():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8885/v1/voices", timeout=3) as r:
            data = json.loads(r.read())
        names = data.get("voices") if isinstance(data, dict) else data
        return sorted(v if isinstance(v, str) else v.get("id", "") for v in names or [])
    except (urllib.error.URLError, OSError, ValueError):
        return []


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


def _leaves(d, prefix=""):
    for k, v in d.items():
        p = prefix + k
        if isinstance(v, dict):
            yield from _leaves(v, p + ".")
        else:
            yield p, v


def _kind(v):
    return "bool" if isinstance(v, bool) else "int" if isinstance(v, int) else "float" if isinstance(v, float) else "text"


def editable():
    """Every changeable setting: its current value, its default, its type (and choices)."""
    out = []
    brain, defaults = brain_config.load(), brain_config.DEFAULTS
    for path, default in _leaves({k: defaults[k] for k in BRAIN_SECTIONS if k in defaults}):
        if path == "heart.temperament":
            continue
        choices = CHOICES.get(("brain", path))
        out.append({"where": "brain", "path": path, "label": LABELS.get(path, path.split(".")[-1].replace("_", " ")),
                    "type": "choice" if choices else "longtext" if path == "personality" else _kind(default),
                    "choices": choices, "value": _get(brain, path), "default": default})
    out.append({"where": "brain", "path": "heart.temperament", "label": LABELS["heart.temperament"], "type": "choice",
                "choices": CHOICES[("brain", "heart.temperament")],
                "value": _get(brain, "heart.temperament") or TEMPERAMENT_DEFAULT, "default": TEMPERAMENT_DEFAULT})
    gw = kindred_gateway.load()
    for path, label, kind in GATEWAY_EDITABLE:
        if kind == "upstream":
            choices = ([""] if path.startswith("by_kind") else []) + sorted(gw.get("upstreams") or {})
        elif kind == "provider":
            choices = sorted((_get(gw, path.rsplit(".", 1)[0]) or {}).get("providers") or {})
        elif kind == "effort":
            choices = ["", "minimal", "low", "medium", "high"]
        else:
            choices = None
        out.append({"where": "gateway", "path": path, "label": label, "type": "choice" if choices is not None else kind,
                    "choices": choices, "value": _get(gw, path), "default": _get(kindred_gateway.DEFAULT_STATE, path)})
    mp = mod_path()
    mod = read_json(mp) if mp else None
    mod_defaults = read_json(os.path.join(os.path.dirname(mp), "kindredspirit.defaults.json")) if mp else None
    # (settings new in this version of the mod are shown and changeable before the game has saved them once)
    mod_defaults = dict(MOD_NEW, **(mod_defaults or {}))
    known = dict(mod_defaults)
    known.update(mod or {})
    for path, value in _leaves(known):
        if path in MOD_HIDDEN:
            continue
        choices = CHOICES.get(("mod", path))
        out.append({"where": "mod", "path": path, "label": LABELS.get(path, path.split(".")[-1]),
                    "type": "choice" if choices else _kind(value), "choices": choices, "value": value,
                    "default": _get(mod_defaults, path)})
    skins, voices = skin_ids(), kokoro_voices()
    for e in out:
        key = (e["where"], e["path"])
        e["help"] = HELP.get(e["path"])
        if key in RANGES and e["type"] in ("int", "float"):
            e["range"] = RANGES[key]
        if key == ("mod", "skin") and skins:
            e["type"], e["choices"] = "choice", skins
        elif key == ("gateway", "tts.providers.local_kokoro.voice") and voices:
            e["suggest"] = voices  # one voice, or a blend like "bf_lily*0.7+bf_emma*0.3"
        elif key == ("gateway", "upstreams.gemini.by_kind.reply.model"):
            e["suggest"] = GEMINI_MODELS
        elif key == ("brain", "ai.model"):
            e["suggest"] = [""] + GEMINI_MODELS
    return out


def change_settings(changes):
    """Apply changes from the dashboard: only listed settings, types checked; "default": true resets one."""
    current = {(e["where"], e["path"]): e for e in editable()}
    brain_over, gw_changes, mod_changes, done = brain_config.read_overrides(), [], [], []
    for ch in changes or []:
        key = (ch.get("where"), ch.get("path"))
        if key not in current:
            raise ValueError("%s can't be changed here" % (key,))
        e = current[key]
        v = e["default"] if ch.get("default") else ch.get("value")
        if v is None:
            raise ValueError("%s has no default to go back to" % key[1])
        kind = e["type"]
        if kind == "bool":
            v = bool(v) if not isinstance(v, str) else v.lower() in ("1", "true", "yes", "on")
        elif kind == "int":
            v = int(float(v))
        elif kind == "float":
            v = float(v)
        elif kind == "choice":
            if v not in e["choices"]:
                raise ValueError("%s must be one of %s" % (key[1], ", ".join(map(str, e["choices"]))))
        else:
            v = str(v)[:2000 if kind == "longtext" else 80]
        {"brain": lambda: _set(brain_over, key[1], v), "gateway": lambda: gw_changes.append((key[1], v)),
         "mod": lambda: mod_changes.append((key[1], v))}[key[0]]()
        done.append({"where": key[0], "path": key[1], "value": v})
    if any(d["where"] == "brain" for d in done):
        _write_json(brain_config.OVERRIDES, brain_over)
    if gw_changes:
        def apply(st):
            for path, v in gw_changes:
                if path == "by_kind.reflect" and not v:
                    (st.get("by_kind") or {}).pop("reflect", None)
                else:
                    _set(st, path, v)
        kindred_gateway.change(apply)
    if mod_changes:
        mp = mod_path()
        mod = read_json(mp) or {}
        for path, v in mod_changes:
            _set(mod, path, v)
        _write_json(mp, mod)  # (the mod sees it within two seconds, even in game)
    return {"changed": done}


# ---------------------------------------------------------------------- profiles: saved sets of settings

PROFILES = os.path.join(DIR, "profiles")
NAME = re.compile(r"^[\w .'-]{1,40}$")


def _profile_path(name):
    if not NAME.match(name or ""):
        raise ValueError("a profile name is up to 40 letters, numbers, spaces, - . or '")
    return os.path.join(PROFILES, re.sub(r"\s+", "_", name.strip()) + ".json")


def _snapshot():
    snap = {}
    for e in editable():
        snap.setdefault(e["where"], {})[e["path"]] = e["value"]
    return snap


def profiles_list():
    """The saved profiles; "active" marks the one your settings match right now (the one in use)."""
    out, now = [], None
    try:
        for f in sorted(os.listdir(PROFILES)):
            if f.endswith(".json"):
                d = read_json(os.path.join(PROFILES, f)) or {}
                saved = d.get("settings") or {}
                now = now if now is not None else _snapshot()
                same = [now[w][p] == v for w, vals in saved.items() for p, v in vals.items() if p in (now.get(w) or {})]
                out.append({"name": d.get("name") or f[:-5], "time": d.get("time"),
                            "count": sum(len(v) for v in saved.values()), "active": bool(same) and all(same)})
    except OSError:
        pass
    return out


def profile_action(action, name):
    if action == "save":
        os.makedirs(PROFILES, exist_ok=True)
        _write_json(_profile_path(name), {"name": name.strip(), "time": time.time(), "settings": _snapshot()})
        return {"saved": name}
    path = _profile_path(name)
    if action == "delete":
        os.remove(path)
        return {"deleted": name}
    if action == "apply":
        saved = (read_json(path) or {}).get("settings") or {}
        now = _snapshot()
        changes = [{"where": w, "path": p, "value": v} for w, vals in saved.items() for p, v in vals.items()
                   if p in (now.get(w) or {}) and now[w][p] != v]
        return change_settings(changes) if changes else {"changed": []}
    raise ValueError("unknown action")


def profile_compare(a, b):
    """What differs between two profiles ("current" = what's set now, "defaults" = the defaults)."""
    entries = editable()
    labels = {(e["where"], e["path"]): e["label"] for e in entries}

    def values(name):
        if name == "current":
            return {(e["where"], e["path"]): e["value"] for e in entries}
        if name == "defaults":
            return {(e["where"], e["path"]): e["default"] for e in entries if e["default"] is not None}
        saved = (read_json(_profile_path(name)) or {}).get("settings") or {}
        return {(w, p): v for w, vals in saved.items() for p, v in vals.items()}
    va, vb = values(a), values(b)
    rows = [{"where": k[0], "path": k[1], "label": labels.get(k, k[1]), "a": va.get(k), "b": vb.get(k)}
            for k in labels if k in va and k in vb and va[k] != vb[k]]
    return {"a": a, "b": b, "differences": rows}


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


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
            msgs = c.get("messages")
            if isinstance(msgs, list):  # (older logs kept the messages; the gateway now keeps how many, and the last one as "player")
                last_user = next((m for m in reversed(msgs) if isinstance(m, dict) and m.get("role") == "user"), {})
                content = last_user.get("content")
            else:
                content = c.get("player")
            if isinstance(content, list):
                content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            calls.append({"t": round(t - at, 1), "kind": c.get("kind"), "model": c.get("model"),
                          "seconds": c.get("seconds"), "player": c.get("player"), "reply": c.get("reply"),
                          "input": (content or "")[-6000:], "tools": [x for x in (c.get("tools") or [])][:20],
                          "actions": c.get("actions"), "tokens_in": c.get("tokens_in"), "tokens_out": c.get("tokens_out")})
    md = os.path.join(SESSIONS, sid + ".md")
    summary = open(md, encoding="utf-8").read() if os.path.exists(md) else ""
    return {"id": sid, "events": rows, "calls": calls, "summary": summary}

# the mod's settings for friends on LAN, with their defaults (KindredConfig.java), for before the game has
# written them to its settings file
MOD_NEW = {"lanGuests": True, "lanGuestPowers": True, "follow": "", "sharedPip": "host", "lanVisitors": True}


def mod_configs(env=None):
    """Where the mod's settings file may be: KINDRED_MOD_CONFIG if set (e.g. the dev game's
    mod/versions/1.21.1/run/config/kindredspirit.json while filming), else every Kindred profile's game folder (one per
    Minecraft version: minecraft-kindred for 1.21.1, minecraft-kindred-26.3...), and the instance whose mods folder
    the Setup put the mod in (another launcher's)."""
    env = os.environ if env is None else env
    if env.get("KINDRED_MOD_CONFIG"):
        return [os.path.expanduser(env["KINDRED_MOD_CONFIG"])]
    rel = os.path.join("config", "kindredspirit.json")
    found = []
    for base, name in ((os.path.expanduser("~/Library/Application Support"), "minecraft-kindred"),
                       (os.path.expanduser("~"), ".minecraft-kindred"), (env.get("APPDATA", ""), "minecraft-kindred")):
        if base:
            found.append(os.path.join(base, name, rel))
            found += sorted(glob.glob(os.path.join(glob.escape(base), name + "-*", rel)))
    try:
        folder = setup_steps.load_state().get("mods_folder")
    except Exception:  # (no Setup state, or an unreadable one: only the profiles then)
        folder = None
    if folder:
        found.append(os.path.join(os.path.dirname(os.path.expanduser(folder).rstrip("/")), rel))
    return found


def mod_path():
    """The mod's settings file in use: of those that exist, the one changed last (the game played last)."""
    there = [p for p in mod_configs() if os.path.exists(p)]
    return max(there, key=os.path.getmtime) if there else None


def blueprint_dirs():
    """The blueprint folders of the game played last (its config/kindredspirit/blueprints and its schematics), the
    same ones the mod reads (#175); KINDRED_BLUEPRINTS, or the first Kindred profile's, when no game was found."""
    if os.environ.get("KINDRED_BLUEPRINTS"):
        return blueprints.DIRS
    path = mod_path()
    if not path:
        return blueprints.DIRS
    config = os.path.dirname(path)
    return [os.path.join(config, "kindredspirit", "blueprints"), os.path.join(os.path.dirname(config), "schematics")]
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
    mp = mod_path()
    mod = read_json(mp) if mp else None
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

    def host_ok(self):
        """Only pages addressed to this computer by name: a web page that points its own domain at 127.0.0.1
        (DNS rebinding) must not read her token or her memories."""
        if (self.headers.get("Host") or "").lower() in ("%s:%d" % (HOST, PORT), "localhost:%d" % PORT):
            return True
        self.send(403, {"error": "open the dashboard as http://%s:%d" % (HOST, PORT)})
        return False

    def do_GET(self):
        global last_request
        if not self.host_ok():
            return
        last_request = time.time()
        url = urlparse(self.path)
        q = {k: v[-1] for k, v in parse_qs(url.query).items()}
        try:
            if url.path in ("/", "/index.html") and not SETUP_MODE:
                with open(PAGE, "rb") as fh:
                    return self.send(200, fh.read(), "text/html")
            if url.path in ("/setup", "/"):
                with open(SETUP_PAGE, "rb") as fh:
                    return self.send(200, fh.read(), "text/html")
            if url.path == "/open":  # what opening the app shows: her dashboard once she's set up, else the steps
                self.send_response(302)
                self.send_header("Location", setup_steps.open_target())
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            if url.path == "/api/setup/hello":  # "is this a Kindred dashboard or Setup, and which version?"
                return self.send(200, {"kindred": True, "setup": SETUP_MODE, "version": setup_steps.own_version()})
            if url.path == "/api/setup/state":
                return self.send(200, setup_steps.overview())
            if url.path == "/api/live":
                mod = read_json(mod_path() or "") or {}
                return self.send(200, {"brain": read_json(os.path.join(LOGS, "brain-state.json")),
                                       "snapshot": read_json(os.path.join(LOGS, "last-snapshot.json")),
                                       "friends": {k: mod.get(k) for k in ("lanGuests", "lanGuestPowers", "follow")},
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
            if url.path == "/api/places":  # the places she knows in a world: on her own, named by you, found
                w = q.get("world") or None
                return self.send(200, {"places": memory("list", kinds=["spot", "place", "found"], world=w, all_worlds=not w,
                                                        limit=400).get("results", [])})
            if url.path == "/api/memory/doc":
                return self.send(200, memory("doc", key=q.get("key", "")))
            if url.path == "/api/settings":
                return self.send(200, settings())
            if url.path == "/api/sim/token":  # the simulator talks to her brain like the game does (this computer only)
                with open(os.path.join(DIR, "token"), encoding="utf-8") as fh:
                    return self.send(200, {"token": fh.read().strip()})
            if url.path == "/api/profiles":
                return self.send(200, {"profiles": profiles_list()})
            if url.path == "/api/profiles/compare":
                return self.send(200, profile_compare(q.get("a", "current"), q.get("b", "defaults")))
            if url.path == "/api/settings/editable":
                return self.send(200, {"settings": editable()})
            if url.path == "/api/sessions":
                return self.send(200, {"sessions": sessions_list()})
            if url.path == "/api/sessions/one":
                return self.send(200, session_one(q.get("id", "")))
            if url.path == "/api/blueprints":
                return self.send(200, blueprints.overview(blueprint_dirs()))
            if url.path == "/api/blueprints/picture":
                dirs = blueprint_dirs()
                i = int(q.get("d", 0)) if str(q.get("d", "0")).isdigit() else -1
                png = blueprints.picture(dirs[i], q.get("f", "")) if 0 <= i < len(dirs) else None
                return self.send(200, png, "image/png") if png else self.send(404, {"error": "no such picture"})
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
    global last_request
    if not handler.host_ok():
        return
    last_request = time.time()
    url = urlparse(handler.path)
    if url.path not in ("/api/knowledge/learn", "/api/settings", "/api/speak", "/api/profiles", "/api/places",
                        "/api/blueprints/add", "/api/blueprints/remove", "/api/blueprints/restore",
                        "/api/setup/run", "/api/setup/help", "/api/setup/quit", "/api/setup/preview",
                        "/api/setup/hear"):
        return handler.send(404, {"error": "not found"})
    if handler.headers.get("Origin") not in (None, "http://%s:%d" % (HOST, PORT), "http://localhost:%d" % PORT):
        return handler.send(403, {"error": "only from the dashboard itself"})
    length = int(handler.headers.get("Content-Length") or 0)
    if length > blueprints.MAX_BYTES * 2:
        return handler.send(413, {"error": "too big"})
    raw = handler.rfile.read(length)
    if url.path == "/api/setup/hear":  # the microphone test: a short WAV from the page, written down by her hearing
        try:
            return handler.send(200, {"text": setup_models.transcribe(raw)})
        except setup_steps.SetupError as e:
            return handler.send(400, {"error": str(e)})
    body = json.loads(raw or b"{}")
    if url.path == "/api/setup/preview":  # "Hear it": her voice saying a line, in the chosen voice
        try:
            return handler.send(200, setup_models.speak(voice=str(body.get("voice") or "")), "audio/wav")
        except setup_steps.SetupError as e:
            return handler.send(400, {"error": str(e)})
    if url.path == "/api/setup/run":  # a step's button: do it, or test it
        return handler.send(200, setup_steps.run(str(body.get("step", "")), str(body.get("action", "")), body))
    if url.path == "/api/setup/help":  # the "Copy a help prompt" button
        return handler.send(200, {"prompt": setup_steps.help_prompt(str(body.get("step", "")), body.get("error") or None)})
    if url.path == "/api/setup/quit":  # the Setup's "Close" button, or a newer Setup taking over
        if not SETUP_MODE:
            return handler.send(400, {"error": "only the Setup app quits; the dashboard keeps running"})
        handler.send(200, {"ok": True})
        threading.Thread(target=handler.server.shutdown, daemon=True).start()
        return
    if url.path.startswith("/api/blueprints/"):  # her blueprint folders: add a file, move one to the trash, back
        try:
            dirs = blueprint_dirs()
            i = int(body.get("d", 0))
            if not 0 <= i < len(dirs):
                raise ValueError("no such folder")
            if url.path.endswith("/add"):
                import base64
                return handler.send(200, blueprints.add(dirs[i], body.get("name"), base64.b64decode(body.get("data") or ""),
                                                        bool(body.get("replace"))))
            if url.path.endswith("/remove"):
                return handler.send(200, blueprints.remove(dirs[i], body.get("name")))
            return handler.send(200, blueprints.restore(dirs[i], body.get("name")))
        except (ValueError, TypeError, OSError) as e:
            return handler.send(400, {"error": str(e)})
    if url.path == "/api/speak":  # play a line again: her voice, made again from the text
        req = urllib.request.Request(GATEWAY + "/audio/speech", method="POST", headers={"Content-Type": "application/json"},
                                     data=json.dumps({"input": str(body.get("text", ""))[:600],
                                                      "style": str(body.get("style", ""))[:20]}).encode())
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return handler.send(200, r.read(), "audio/wav")
        except (urllib.error.URLError, OSError) as e:
            return handler.send(502, {"error": str(getattr(e, "reason", e))})
    if url.path == "/api/places":  # rename a place she knows, or forget it
        try:
            pid = int(body.get("id"))
            if body.get("action") == "forget":
                return handler.send(200, memory("delete", id=pid, kinds=["spot", "place", "found"]))
            if body.get("action") == "rename" and str(body.get("text", "")).strip():
                return handler.send(200, memory("update", id=pid, text=str(body["text"]).strip()[:120]))
            return handler.send(400, {"error": "forget or rename (with a text)"})
        except (ValueError, TypeError) as e:
            return handler.send(400, {"error": str(e)})
        except (urllib.error.URLError, OSError) as e:
            return handler.send(502, {"error": str(getattr(e, "reason", e))})
    if url.path == "/api/profiles":
        try:
            return handler.send(200, profile_action(str(body.get("action", "")), str(body.get("name", ""))))
        except (ValueError, TypeError, OSError) as e:
            return handler.send(400, {"error": str(e)})
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


def quit_when_idle(server, idle=None, every=30):
    """Setup mode: nobody has looked at the page for a while (it polls while open), so the Setup is done."""
    while True:
        time.sleep(every)
        if time.time() - last_request > (idle or SETUP_IDLE_SECONDS):
            server.shutdown()
            return


def main(argv=None):
    global PORT, SETUP_MODE
    argv = sys.argv[1:] if argv is None else argv
    if "--setup" in argv:
        SETUP_MODE = True
        PORT = int(os.environ.get("KINDRED_SETUP_PORT", "11441"))
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("Kindred %s on http://%s:%d" % ("Setup" if SETUP_MODE else "dashboard", HOST, PORT), flush=True)
    if SETUP_MODE:
        threading.Thread(target=quit_when_idle, args=(server,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
