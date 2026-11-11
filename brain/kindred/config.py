"""Brain settings: ~/.kindred-spirit/brain.toml, created with the defaults on first run.

Every value has a default here, so an old or partial file keeps working.
"""
import copy
import os
import tomllib

HOME = os.environ.get("KINDRED_HOME") or os.path.join(os.path.expanduser("~"), ".kindred-spirit")
PATH = os.path.join(HOME, "brain.toml")
TOKEN = os.path.join(HOME, "token")

DEFAULTS = {
    "name": "Pip",
    "personality": "",
    "server": {"host": "127.0.0.1", "port": 47811},
    "ai": {
        "url": "http://127.0.0.1:11437/v1",
        "model": "gemini-3.1-flash-lite",
        "api_key": "",
        "temperature": 0.8,
        "max_tokens": 160,
        "history_turns": 12,
    },
    "voice": {
        "enabled": True,
        "stt_url": "http://127.0.0.1:8090/audio/transcriptions",
        "tts_url": "http://127.0.0.1:8885/v1/audio/speech",
        "tts_voice": "af_heart",
        "tts_speed": 1.05,
    },
    "behaviour": {
        "alerts": True,
        "greet_on_join": True,
        "small_talk_minutes": 6,
    },
}

TEMPLATE = '''# Kindred brain settings. Delete a line to get its default back.

name = "Pip"                 # what your companion is called
personality = ""             # extra instructions, e.g. "Speaks like a pirate. Loves redstone."

[server]
port = 47811                 # the mod connects here (must match config/kindredspirit.json)

[ai]
url = "http://127.0.0.1:11437/v1"   # any OpenAI-compatible address; default = the Kindred gateway
model = "gemini-3.1-flash-lite"
api_key = ""                 # only if "url" needs one directly (the gateway keeps its own keys)
temperature = 0.8
max_tokens = 160

[voice]
enabled = true               # false = subtitles only, no speech
stt_url = "http://127.0.0.1:8090/audio/transcriptions"   # speech cleaner -> Whisper
tts_url = "http://127.0.0.1:8885/v1/audio/speech"         # Kokoro (local)
tts_voice = "af_heart"       # try af_bella, af_nicole, am_puck, bf_emma...
tts_speed = 1.05

[behaviour]
alerts = true                # warn about low health and creepers
greet_on_join = true
small_talk_minutes = 6       # say something on its own after this long without talking; 0 = never
'''


def merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(path=PATH):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(TEMPLATE)
    with open(path, "rb") as fh:
        return merge(DEFAULTS, tomllib.load(fh))


def read_or_create_token(path=TOKEN):
    """Same file the mod uses; whichever starts first creates it, readable only by you."""
    try:
        with open(path, encoding="utf-8") as fh:
            token = fh.read().strip()
            if token:
                return token
    except FileNotFoundError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    token = os.urandom(24).hex()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:  # the mod made it a moment ago
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    with os.fdopen(fd, "w") as fh:
        fh.write(token + "\n")
    return token
