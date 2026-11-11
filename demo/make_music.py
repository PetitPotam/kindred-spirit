#!/usr/bin/env python3
"""A small cozy background track for the demo video, made from scratch (no samples, no
copyright): a soft pad, a plucked arpeggio, a gentle bass, light drums and little bells.

    python make_music.py SECONDS out.wav
"""
import sys
import wave

import numpy as np

SR = 44100
BPM = 92
BEAT = 60 / BPM
BAR = 4 * BEAT
# cozy, slightly dreamy progression: Fmaj7 - Em7 - Dm7 - Cmaj7, two bars each
CHORDS = [[53, 57, 60, 64], [52, 55, 59, 62], [50, 53, 57, 60], [48, 52, 55, 59]]
rng = np.random.default_rng(7)


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def env(n, attack, release, total):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    r = np.clip((total - t) / max(release, 1e-4), 0, 1)
    return a * r


def pad(freq, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.zeros(n)
    for det in (-0.12, 0.0, 0.11):  # slightly detuned voices make it soft and wide
        f = freq * 2 ** (det / 12)
        s += np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t) + 0.08 * np.sin(6 * np.pi * f * t)
    return s / 3 * env(n, 0.8, 1.0, dur)


def pluck(freq, dur=0.6):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(6 * np.pi * freq * t) * np.exp(-t * 12)
    return s * np.exp(-t * 6.5) * np.clip(t / 0.004, 0, 1)


def bell(freq, dur=1.6):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(2 * np.pi * freq * 2.76 * t) * np.exp(-t * 4)
    return s * np.exp(-t * 3) * np.clip(t / 0.002, 0, 1)


def kick(dur=0.35):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 50 + 70 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)


def hat(dur=0.06):
    n = int(dur * SR)
    noise = rng.standard_normal(n)
    noise = noise - np.convolve(noise, np.ones(4) / 4, "same")  # keep the hiss, drop the rumble
    return noise * np.exp(-np.arange(n) / SR * 70)


def add(track, sig, at, pan=0.0, gain=1.0):
    i = int(at * SR)
    if i >= track.shape[0]:
        return
    sig = sig[: track.shape[0] - i] * gain
    track[i:i + len(sig), 0] += sig * (1 - max(0, pan))
    track[i:i + len(sig), 1] += sig * (1 + min(0, pan))


def reverb(x, seconds=1.8, mix=0.22):
    n = int(seconds * SR)
    ir = rng.standard_normal((n, 2)) * np.exp(-np.arange(n) / SR * 3.2)[:, None]
    ir[:, 0] = np.convolve(ir[:, 0], np.ones(8) / 8, "same")  # darker tail
    ir[:, 1] = np.convolve(ir[:, 1], np.ones(8) / 8, "same")
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    wet = np.stack([np.fft.irfft(np.fft.rfft(x[:, c], size) * np.fft.rfft(ir[:, c], size), size)[: len(x)]
                    for c in range(2)], axis=1)
    wet /= np.max(np.abs(wet)) + 1e-9
    return x * (1 - mix) + wet * np.max(np.abs(x)) * mix


def make(seconds):
    total = int(seconds * SR)
    music = np.zeros((total + SR * 3, 2))
    bars = int(np.ceil(seconds / BAR))
    for bar in range(bars):
        start = bar * BAR
        chord = CHORDS[(bar // 2) % len(CHORDS)]
        section = "intro" if bar < 2 else "outro" if bar >= bars - 2 else "main"
        if bar % 2 == 0:  # pad holds for two bars
            for k, m in enumerate(chord):
                add(music, pad(hz(m), 2 * BAR + 0.8), start, pan=(k - 1.5) * 0.25, gain=0.055)
            add(music, bell(hz(chord[-1] + 24)), start + 0.02, pan=0.3, gain=0.05)
        if section != "intro":
            # plucked arpeggio in eighth notes, up and back down, gently varied
            pattern = [0, 1, 2, 3, 2, 3, 1, 2]
            for i, p in enumerate(pattern):
                m = chord[p] + 12 + (12 if (bar % 4 == 3 and i >= 6) else 0)
                vel = 0.07 * (0.8 + 0.4 * rng.random())
                add(music, pluck(hz(m)), start + i * BEAT / 2, pan=0.35 if i % 2 else -0.35, gain=vel)
            add(music, pluck(hz(chord[0] - 12), 1.4) * 1.2, start, gain=0.13)            # bass
            add(music, pluck(hz(chord[0] - 12), 1.0), start + 2 * BEAT, gain=0.1)
        if section == "main":
            for b in (0, 2):
                add(music, kick(), start + b * BEAT, gain=0.16)
            for e in range(4):
                add(music, hat(), start + (e + 0.5) * BEAT, pan=0.2, gain=0.035)
    music = reverb(music)
    music = music[:total]
    fade = int(2.5 * SR)
    music[:int(1.0 * SR)] *= np.linspace(0, 1, int(1.0 * SR))[:, None]
    music[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return music / (np.max(np.abs(music)) + 1e-9) * 0.8


if __name__ == "__main__":
    secs, out = float(sys.argv[1]), sys.argv[2]
    data = (make(secs) * 32767).astype("<i2")
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    print("wrote", out)
