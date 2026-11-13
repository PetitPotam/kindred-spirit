#!/usr/bin/env python3
"""Makes the player's spoken lines for the demo with the local Kokoro voice (a different voice
from the companion's), as two files each: NAME.wav at 16 kHz (what the game's push-to-talk
sends, so it goes through the real speech-to-text) and NAME_hq.wav for the video's sound.

    ../brain/.venv/bin/python make_voices.py      (the gateway and its voice must be running: scripts/start.sh)
"""
import array
import io
import json
import os
import urllib.request
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out", "voices")
VOICE = "am_puck"
LINES = {
    "q_hi": "Hi Pip! Say hello to everyone!",
    "q_build": "Pip, what could I build with all this birch wood?",
    "q_spin": "Pip! Can you do a spin?",
    "q_stay": "Pip, stay here.",
    "q_come": "Okay, come here!",
    # the singleplayer showcase (showcase-script.txt)
    "s_hello": "Hi Pip! What can you see around us?",
    "s_sheep": "Where are the sheep? Lead the way!",
    "s_mine": "Pip, can you mine this iron for me?",
    "s_chop": "Now chop this tree and bring me the logs.",
    "s_piston": "What am I missing to make a piston?",
    "s_cottage": "Pip, build us a cozy cottage right here, for two.",
    "s_name": "This is our cottage. Remember it!",
    "s_vision": "Can you give me night vision?",
    "s_enchant": "And enchant my sword with sharpness, please.",
    "s_help": "Help! Protect me!",
    "s_back": "Take me back to our cottage.",
    "s_sorry": "Oops, sorry Pip! That was an accident.",
    "s_light": "It's so dark out here. Can you light the way?",
    # the tour (tour-script.txt)
    "t_hello": "Hi! I'm Sam. Who are you?",
    "t_see": "What can you see around us?",
    "t_diamonds": "Pip, are there any diamonds around here?",
    "t_remember": "Pip, what do you remember about our adventures?",
    "t_origin": "Do you know where you come from now?",
    "t_where": "Where are the sheep?",
    "t_lead": "Lead the way, I'll follow you!",
    "t_chop": "Can you chop this tree for me?",
    "t_help": "Help! Protect me!",
    "t_iron": "How do I build an iron farm?",
    "t_sorry": "Oops, sorry Pip! That was an accident.",
    "t_torch": "It's so dark. Can you give me some light?",
    "t_torch2": "Okay, now can you place a torch for me?",
}


def speak(text):
    body = json.dumps({"input": text, "voice": VOICE, "speed": 0.92}).encode()
    req = urllib.request.Request("http://127.0.0.1:11437/v1/audio/speech", data=body,  # through the gateway
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def to_16k(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        rate, frames = w.getframerate(), w.readframes(w.getnframes())
    s = array.array("h")
    s.frombytes(frames)
    n = int(len(s) * 16000 / rate)
    out = array.array("h", [0] * n)
    for i in range(n):
        x = i * rate / 16000
        j = int(x)
        a, b = s[min(j, len(s) - 1)], s[min(j + 1, len(s) - 1)]
        out[i] = int(a + (b - a) * (x - j))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(out.tobytes())
    return buf.getvalue()


if __name__ == "__main__":
    import sys
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[1] if len(sys.argv) > 1 else ""  # e.g. "t_": only the tour's lines
    for name, text in LINES.items():
        if not name.startswith(only):
            continue
        hq = speak(text)
        with open(os.path.join(OUT, name + "_hq.wav"), "wb") as fh:
            fh.write(hq)
        with open(os.path.join(OUT, name + ".wav"), "wb") as fh:
            fh.write(to_16k(hq))
        print("%-8s %s" % (name, text))
