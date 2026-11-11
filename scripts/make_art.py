#!/usr/bin/env python3
"""Draws the mod's small images with no image library: the white texture the slime is tinted
from, and the 128x128 mod icon (a green slime ball with a face). Run it again after changing
the drawing; the PNGs are committed so nobody needs Python to build the mod.

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
    bx, by, rx, ry = px / 0.86, (py - 0.08) / 0.78, 1, 1
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


if __name__ == "__main__":
    png(os.path.join(ASSETS, "textures", "companion", "white.png"), 16, 16, lambda x, y: (255, 255, 255, 255))
    png(os.path.join(ASSETS, "icon.png"), 128, 128, icon)
    print("wrote white.png and icon.png in", ASSETS)
