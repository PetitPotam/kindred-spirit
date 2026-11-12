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
    # everything from the outside goes through one gateway: AI, speech-to-text, voice, memory
    "gateway": {"url": "http://127.0.0.1:11437/v1", "key": ""},
    "ai": {
        "model": "",            # "" = the gateway's choice (gateway.json)
        "temperature": 0.8,
        "max_tokens": 160,
        "history_turns": 8,     # kept word for word; older turns are folded into a short summary
    },
    "voice": {
        "enabled": True,
        "voice": "",            # "" = the gateway's choice; or a voice name for its voice provider
        "speed": 0,             # 0 = the gateway's choice
    },
    "behaviour": {
        "alerts": True,
        "greet_on_join": True,
        "small_talk_minutes": 4,
    },
    "heart": {
        "amnesia": True,               # she discovers her powers with you, one by one
        "awakening": "slow",           # slow: "I'll try!" now, the power wakes up a bit later | instant
        "awakening_seconds": 40,       # about how long a power takes to wake up (slow)
        "favours": True,               # while a power wakes up, she may ask you a small favour
        "start_bond": 30,              # 0-100; 30 = strangers who'd like to be friends
        "auto_protect": False,         # protect you without being asked (she'll offer otherwise)
        "curiosity": True,             # notices advancements, new items, biomes... and talks about them
        "pranks": True,                # playful pranks once you're friends
        "fibs": True,                  # pranks may include a playful fib she owns up to (otherwise she never lies)
        "block_pranks": True,          # pranks may borrow a block you just placed (it goes to your inventory)
        "mischief_when_angry": "spicy",  # off | mild (sulks, spooky sounds) | spicy (also borrows your blocks)
        "can_vanish": True,            # disappears for a while when mistreated
        "play_fights": True,           # as close friends she may bonk you back, or play-hit and heal you
        "weather_follows_mood": True,  # her tears bring rain, a real apology clears it (singleplayer)
    },
}

TEMPLATE = '''# Kindred brain settings. Delete a line to get its default back.

name = "Pip"                 # what your companion is called
personality = ""             # extra instructions, e.g. "Speaks like a pirate. Loves redstone."

[server]
port = 47811                 # the mod connects here (must match config/kindredspirit.json)

[gateway]
# The one address for AI, speech-to-text, voice and memory. Which services it uses (Gemini, local
# Whisper, Kokoro, a deployed gateway...) is set in the gateway: see docs/GATEWAY.md.
url = "http://127.0.0.1:11437/v1"
key = ""                     # only if your gateway has an access key (e.g. deployed on a server)

[ai]
model = ""                   # "" = the gateway's choice
temperature = 0.8
max_tokens = 160

[voice]
enabled = true               # false = subtitles only, no speech
voice = ""                   # "" = the gateway's choice; or e.g. af_bella, am_puck, bf_emma (Kokoro)
speed = 0                    # 0 = the gateway's choice

[behaviour]
alerts = true                # warn about low health and creepers
greet_on_join = true
small_talk_minutes = 4       # say something on its own after this long without talking; 0 = never

[heart]
# who she is with you (docs/HEART.md)
amnesia = true               # she discovers her powers with you, one by one
awakening = "slow"           # slow: "I'll try!" at once, the power wakes up a little later | instant
awakening_seconds = 40       # about how long a new power takes to wake up
favours = true               # while it wakes up, she may ask you a small favour
start_bond = 30              # 0-100; how close she feels to you at first (30 = strangers)
auto_protect = false         # protect you without being asked (otherwise she offers, once you've asked before)
curiosity = true             # notices advancements, new items, biomes... and talks about them
pranks = true                # playful pranks once you're friends
fibs = true                  # pranks may include a playful fib she owns up to (otherwise she never lies)
block_pranks = true          # pranks may borrow a block you just placed (it goes to your inventory)
mischief_when_angry = "spicy"  # off | mild (sulks, spooky sounds) | spicy (also borrows your blocks)
can_vanish = true            # disappears for a while when mistreated
play_fights = true           # as close friends she may bonk you back, or play-hit you and heal you
weather_follows_mood = true  # her tears bring rain, a real apology clears it (singleplayer)
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
