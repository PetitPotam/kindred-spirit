#!/usr/bin/env python3
"""Pretend to be Minecraft: talk to the running brain without starting the game.

Uses the real brain, gateway, Whisper and Kokoro, so it tests your actual setup.
Run from the brain folder with its Python:

    .venv/bin/python tools/fake_game.py chat "what should I build first?"
    .venv/bin/python tools/fake_game.py creeper            # a creeper sneaks up behind you
    .venv/bin/python tools/fake_game.py lowhealth          # you drop to 2 hearts
    .venv/bin/python tools/fake_game.py voice question.wav # a recording, as push-to-talk sends it
    .venv/bin/python tools/fake_game.py speak "what's around me?"   # Kokoro says it, Whisper hears it
    .venv/bin/python tools/fake_game.py join               # you enter a world (it greets you)

Add --play to hear the answers (macOS afplay), --quiet to hide the JSON.
"""
import argparse
import array
import asyncio
import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kindred import config  # noqa: E402
from websockets.asyncio.client import connect  # noqa: E402

SNAPSHOT = {
    "type": "snapshot", "health": 18.0, "maxHealth": 20.0, "food": 17, "saturation": 2.0, "armor": 5,
    "air": 300, "maxAir": 300, "onFire": False, "gamemode": "survival", "effects": [],
    "where": {"x": 104, "y": 68, "z": -212, "dimension": "minecraft:overworld", "biome": "minecraft:birch_forest",
              "facing": "east", "yaw": -90.0, "skyVisible": True, "light": 14},
    "time": {"day": 3, "timeOfDay": 11500, "raining": False, "thundering": False},
    "holding": "minecraft:stone_axe", "offhand": "minecraft:torch",
    "inventory": {"minecraft:birch_log": 23, "minecraft:cobblestone": 41, "minecraft:torch": 12,
                  "minecraft:bread": 4, "minecraft:coal": 7},
    "wearing": ["minecraft:leather_boots", "minecraft:iron_chestplate"],
    "lookingAt": {"block": "minecraft:birch_log", "distance": 2.6}, "hostiles": [],
}


def to_16k_mono(wav_bytes):
    """Whisper wants 16 kHz mono; Kokoro speaks at 24 kHz. Simple linear resampling."""
    with wave.open(io.BytesIO(wav_bytes)) as w:
        rate, ch, frames = w.getframerate(), w.getnchannels(), w.readframes(w.getnframes())
    s = array.array("h")
    s.frombytes(frames)
    if ch > 1:
        s = array.array("h", s[::ch])
    n = int(len(s) * 16000 / rate)
    out = array.array("h", [0] * n)
    for i in range(n):
        x = i * rate / 16000
        j = int(x)
        f = x - j
        a, b = s[min(j, len(s) - 1)], s[min(j + 1, len(s) - 1)]
        out[i] = int(a + (b - a) * f)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(out.tobytes())
    return buf.getvalue()


def kokoro(text, cfg):
    body = json.dumps({"input": text, "voice": "am_puck", "speed": 1.0}).encode()
    req = urllib.request.Request(cfg["gateway"]["url"].rstrip("/") + "/audio/speech", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["chat", "creeper", "lowhealth", "voice", "speak", "join"])
    ap.add_argument("arg", nargs="?", default="")
    ap.add_argument("--play", action="store_true", help="play the voice replies (macOS)")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--wait", type=float, default=25, help="seconds to wait for replies")
    a = ap.parse_args()
    cfg = config.load()
    token = config.read_or_create_token()
    url = "ws://127.0.0.1:%d/" % cfg["server"]["port"]
    snap = json.loads(json.dumps(SNAPSHOT))
    try:
        ws_ctx = connect(url, additional_headers={"Authorization": "Bearer " + token}, max_size=2 ** 24)
        ws = await ws_ctx.__aenter__()
    except OSError:
        sys.exit("The brain is not running on %s. Start it with scripts/start.sh" % url)
    started = time.monotonic()
    await ws.send(json.dumps({"type": "hello", "mod": "fake_game", "minecraft": "1.21.1"}))
    await ws.send(json.dumps(snap))
    if a.action == "chat":
        await ws.send(json.dumps({"type": "chat", "text": a.arg or "hi! what do you see?"}))
    elif a.action == "creeper":
        snap["hostiles"] = [{"type": "minecraft:creeper", "distance": 4.2, "direction": "behind", "above": 0.0}]
        snap["urgent"] = True
        await ws.send(json.dumps(snap))
    elif a.action == "lowhealth":
        snap["health"] = 4.0
        await ws.send(json.dumps(snap))
    elif a.action == "voice":
        with open(a.arg, "rb") as fh:
            wav = to_16k_mono(fh.read())
        await ws.send(json.dumps({"type": "voice", "peak": 9000, "wav": base64.b64encode(wav).decode()}))
    elif a.action == "speak":
        wav = to_16k_mono(kokoro(a.arg or "What's around me?", cfg))
        print("(sending %.1f s of synthetic speech as your voice)" % (len(wav) / 32000))
        await ws.send(json.dumps({"type": "voice", "peak": 9000, "wav": base64.b64encode(wav).decode()}))
    elif a.action == "join":
        await ws.send(json.dumps({"type": "event", "event": "join"}))
    try:
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), a.wait))
            t = time.monotonic() - started
            if msg["type"] == "say":
                audio = base64.b64decode(msg.get("audio") or "")
                print("%5.2fs  SAY [%s] %s  (%s)" % (t, msg.get("mood"), msg.get("text"),
                                                    "%d KB voice" % (len(audio) // 1024) if audio else "no voice"))
                if a.play and audio:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        f.write(audio)
                    subprocess.run(["afplay", f.name])
                    os.unlink(f.name)
                break
            elif not a.quiet:
                print("%5.2fs  %s" % (t, json.dumps(msg)[:200]))
    except asyncio.TimeoutError:
        print("no reply within %.0f s" % a.wait)
    await ws_ctx.__aexit__(None, None, None)


if __name__ == "__main__":
    asyncio.run(main())
