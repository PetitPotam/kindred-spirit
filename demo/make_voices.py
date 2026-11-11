#!/usr/bin/env python3
"""Makes the player's spoken lines for the demo with the local Kokoro voice (a different voice
from the companion's), as two files each: NAME.wav at 16 kHz (what the game's push-to-talk
sends, so it goes through the real speech-to-text) and NAME_hq.wav for the video's sound.

    ../brain/.venv/bin/python make_voices.py      (Kokoro must be running: scripts/start.sh)
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
}


def speak(text):
    body = json.dumps({"input": text, "voice": VOICE, "speed": 0.92}).encode()
    req = urllib.request.Request("http://127.0.0.1:8885/v1/audio/speech", data=body,
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
    os.makedirs(OUT, exist_ok=True)
    for name, text in LINES.items():
        hq = speak(text)
        with open(os.path.join(OUT, name + "_hq.wav"), "wb") as fh:
            fh.write(hq)
        with open(os.path.join(OUT, name + ".wav"), "wb") as fh:
            fh.write(to_16k(hq))
        print("%-8s %s" % (name, text))
