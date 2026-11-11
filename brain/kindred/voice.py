"""Speech in and out, through local HTTP services (swappable: any OpenAI-style endpoints)."""
import asyncio
import json
import os
import urllib.error
import urllib.request


class VoiceError(Exception):
    pass


def _transcribe(url, wav, prompt="", timeout=60, key=""):
    boundary = "kindred" + os.urandom(8).hex()
    parts = [
        b"--" + boundary.encode() + b'\r\nContent-Disposition: form-data; name="file"; filename="speech.wav"\r\n'
        b"Content-Type: audio/wav\r\n\r\n" + wav + b"\r\n",
        b"--" + boundary.encode() + b'\r\nContent-Disposition: form-data; name="response_format"\r\n\r\njson\r\n',
        # a hint so the companion's name is heard right ("Pip", not "Hip")
        b"--" + boundary.encode() + b'\r\nContent-Disposition: form-data; name="prompt"\r\n\r\n'
        + prompt.encode("utf-8") + b"\r\n",
        b"--" + boundary.encode() + b"--\r\n",
    ]
    req = urllib.request.Request(url, data=b"".join(parts), method="POST",
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    if key:
        req.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return (json.loads(resp.read()).get("text") or "").strip()
    except urllib.error.HTTPError as e:
        raise VoiceError("speech-to-text HTTP %s: %s" % (e.code, e.read()[:200].decode("utf-8", "replace")))
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise VoiceError("speech-to-text not reachable at %s (%s)" % (url, getattr(e, "reason", e)))


def _speak(url, text, voice, speed, timeout=30, key=""):
    body = {"input": text, "response_format": "wav"}
    if voice:
        body["voice"] = voice
    if speed:
        body["speed"] = speed
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    if key:
        req.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        raise VoiceError("voice HTTP %s: %s" % (e.code, e.read()[:200].decode("utf-8", "replace")))
    except (urllib.error.URLError, OSError) as e:
        raise VoiceError("voice not reachable at %s (%s)" % (url, getattr(e, "reason", e)))
    if not data.startswith(b"RIFF"):
        raise VoiceError("voice did not return a WAV file")
    return data


def _base(cfg):
    return cfg["gateway"]["url"].rstrip("/")


async def transcribe(cfg, wav, prompt=""):
    return await asyncio.to_thread(_transcribe, _base(cfg) + "/audio/transcriptions", wav, prompt,
                                   key=cfg["gateway"].get("key", ""))


async def speak(cfg, text):
    v = cfg["voice"]
    return await asyncio.to_thread(_speak, _base(cfg) + "/audio/speech", text, v.get("voice", ""), v.get("speed", 0),
                                   key=cfg["gateway"].get("key", ""))
