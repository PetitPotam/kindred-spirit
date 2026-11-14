#!/usr/bin/env python3
"""Draws the mod's small images with no image library: the white texture the slime is tinted
from, the 128x128 mod icon, and the textures of the built-in skins. Run it again after changing
a drawing; the PNGs are committed so nobody needs Python to build the mod.

Skin textures are wrapped around the body like a world map (2:1, e.g. 64x32): left to right goes
once around, top to bottom goes from the top of the head to the bottom. The face is drawn on top
by the mod, at one quarter of the way across.

    python3 scripts/make_art.py
"""
import math
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "mod", "src", "main", "resources", "assets", "kindredspirit")


def png(path, w, h, pixel):
    rows = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(w)) for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def icon(x, y, n=128):
    # supersample 3x3 for smooth edges
    acc = [0, 0, 0, 0]
    for sy in range(3):
        for sx in range(3):
            px = (x + (sx + 0.5) / 3) / n * 2 - 1
            py = (y + (sy + 0.5) / 3) / n * 2 - 1
            c = icon_sample(px, py)
            a = c[3] / 255
            for i in range(3):
                acc[i] += c[i] * a
            acc[3] += a
    if acc[3] == 0:
        return (0, 0, 0, 0)
    return tuple(round(acc[i] / acc[3]) for i in range(3)) + (round(acc[3] / 9 * 255),)


def icon_sample(px, py):
    # body: slightly squashed ball resting low in the frame
    bx, by = px / 0.86, (py - 0.08) / 0.78
    d = bx * bx + by * by
    if d > 1:
        # soft shadow under it
        sd = (px / 0.7) ** 2 + ((py - 0.9) / 0.09) ** 2
        return (40, 60, 40, 70) if sd < 1 else (0, 0, 0, 0)
    green, dark, light = (122, 220, 110), (70, 160, 70), (200, 250, 190)
    shade = mix(green, dark, max(0, min(1, (by + 0.2) * 0.7)))
    # rim light and glossy highlight
    if (bx + 0.42) ** 2 / 0.05 + (by + 0.55) ** 2 / 0.02 < 1:
        return (250, 255, 250, 255)
    shade = mix(shade, light, max(0, 0.35 - d * 0.35) * max(0, -by))
    # eyes
    for ex in (-0.32, 0.32):
        ey = -0.02
        if ((bx - ex) / 0.13) ** 2 + ((by - ey) / 0.2) ** 2 < 1:
            if ((bx - ex - 0.05) / 0.05) ** 2 + ((by - ey + 0.08) / 0.06) ** 2 < 1:
                return (255, 255, 255, 255)
            return (30, 26, 46, 255)
        # cheeks
        if ((bx - ex * 1.6) / 0.15) ** 2 + ((by - 0.24) / 0.07) ** 2 < 1:
            return mix(shade, (255, 143, 171), 0.8) + (255,)
    # smile: lower half of a thin ring
    r = math.hypot(bx / 1.0, (by - 0.18) / 1.0)
    if by > 0.18 and abs(r - 0.13) < 0.035:
        return (58, 26, 42, 255)
    return shade + (255,)


def strawberry(x, y, w=64, h=32):
    u, v = (x + 0.5) / w, (y + 0.5) / h
    # leafy green cap with a jagged edge
    edge = 0.16 + 0.05 * math.sin(u * 2 * math.pi * 6)
    if v < edge:
        return mix((70, 150, 60), (40, 110, 40), v / edge) + (255,)
    red = mix((235, 60, 80), (200, 35, 60), v)
    # seeds on a staggered grid, smaller near the top and bottom
    gx, gy = u * 16, v * 9
    if int(gy) % 2:
        gx += 0.5
    dx, dy = gx - math.floor(gx) - 0.5, gy - math.floor(gy) - 0.5
    if dx * dx * 4 + dy * dy * 9 < 0.08 and v > edge + 0.04:
        return (255, 225, 120, 255)
    return red + (255,)


def starry(x, y, w=64, h=32):
    v = (y + 0.5) / h
    base = mix((40, 50, 130), (90, 40, 140), v)
    base = mix(base, (120, 160, 255), max(0, 0.35 - abs(v - 0.5)) * 0.8)
    # deterministic stars
    hsh = (x * 73856093) ^ (y * 19349663)
    if hsh % 23 == 0:
        return (255, 250, 220, 255)
    if hsh % 41 == 1:
        return (255, 210, 120, 255)
    return base + (255,)


def smooth(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def wing(x, y, n=64):
    """A fairy wing, white so the mod can tint it: hinge on the left edge, tip on the right."""
    acc = [0.0, 0.0]
    for sy in range(2):
        for sx in range(2):
            u = (x + (sx + 0.5) / 2) / n
            v = (y + (sy + 0.5) / 2) / n
            narrow = 0.3 + 0.7 * smooth(0.0, 0.55, u)          # thin at the hinge
            d = ((u - 0.55) / 0.45) ** 2 + ((v - 0.5) / (0.46 * narrow)) ** 2
            if d >= 1:
                continue
            a = 0.55 + 0.25 * u                               # more see-through near the body
            if d > 0.82:
                a = 0.95                                      # a soft rim
            ang = math.atan2(v - 0.5, u + 0.05)
            if abs(math.sin(ang * 9)) < 0.07 and u > 0.12 and d < 0.82:
                a = 0.85                                      # veins fanning from the hinge
            acc[0] += a
            acc[1] += 0.9 + 0.1 * u
    if acc[0] == 0:
        return (255, 255, 255, 0)
    shade = round(235 * acc[1] / 4)
    return (shade, shade, 255, round(255 * min(1.0, acc[0] / 4 * 1.25)))


if __name__ == "__main__":
    png(os.path.join(ASSETS, "textures", "companion", "white.png"), 16, 16, lambda x, y: (255, 255, 255, 255))
    # (the icon is a picture of Pip taken in the game since 2026-11-13: docs/art/README.md; not drawn here any more)
    png(os.path.join(ASSETS, "textures", "skins", "strawberry.png"), 64, 32, strawberry)
    png(os.path.join(ASSETS, "textures", "skins", "starry.png"), 64, 32, starry)
    png(os.path.join(ASSETS, "textures", "companion", "wing.png"), 64, 64, wing)
    print("wrote white.png and the skin textures in", ASSETS)
