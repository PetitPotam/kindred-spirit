"""Speech in and out, through local HTTP services (swappable: any OpenAI-style endpoints)."""
import asyncio
import json
import os
import urllib.error
import urllib.request


class VoiceError(Exception):
    pass


def _transcribe(url, wav, timeout=60):
    boundary = "kindred" + os.urandom(8).hex()
    parts = [
        b"--" + boundary.encode() + b'\r\nContent-Disposition: form-data; name="file"; filename="speech.wav"\r\n'
        b"Content-Type: audio/wav\r\n\r\n" + wav + b"\r\n",
        b"--" + boundary.encode() + b'\r\nContent-Disposition: form-data; name="response_format"\r\n\r\njson\r\n',
        b"--" + boundary.encode() + b"--\r\n",
    ]
    req = urllib.request.Request(url, data=b"".join(parts), method="POST",
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return (json.loads(resp.read()).get("text") or "").strip()
    except urllib.error.HTTPError as e:
        raise VoiceError("speech-to-text HTTP %s: %s" % (e.code, e.read()[:200].decode("utf-8", "replace")))
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise VoiceError("speech-to-text not reachable at %s (%s)" % (url, getattr(e, "reason", e)))


def _speak(url, text, voice, speed, timeout=30):
    body = json.dumps({"model": "kokoro", "input": text, "voice": voice, "speed": speed,
                       "response_format": "wav"}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
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


async def transcribe(cfg, wav):
    return await asyncio.to_thread(_transcribe, cfg["voice"]["stt_url"], wav)


async def speak(cfg, text):
    v = cfg["voice"]
    return await asyncio.to_thread(_speak, v["tts_url"], text, v.get("tts_voice", "af_heart"), v.get("tts_speed", 1.0))
