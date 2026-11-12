#!/usr/bin/env python3
"""Edits the recorded demo (mod/run/recordings/demo) into a finished video: chapter titles,
captions of what is said, a title and an end card, crossfades, the voices back in place, and
music that dips under speech. Output: demo/out/kindred-spirit-demo.mp4 (+ a short preview GIF).

    .venv/bin/python make_video.py        the short demo (demo-script.txt)
    .venv/bin/python make_video.py tour   the full tour (tour-script.txt) -> demo/out/kindred-spirit-tour.mp4
"""
import json
import os
import subprocess
import sys
import textwrap
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CUT = sys.argv[1] if len(sys.argv) > 1 else "demo"
REC = os.path.join(ROOT, "mod", "run", "recordings", CUT)
OUT = os.path.join(HERE, "out")
TMP = os.path.join(OUT, "work" if CUT == "demo" else "work-" + CUT)
W, H, FPS = 1920, 1080, 30
XF = 0.5                      # crossfade between chapters, seconds
SR = 48000
FONT = "/System/Library/Fonts/SFNSRounded.ttf"
REPO = "github.com/PetitPotam/kindred-spirit"

sys.path.insert(0, HERE)
from make_music import make as make_music  # noqa: E402
from make_voices import LINES  # noqa: E402

CHAPTERS = [
    ("meet", "Meet Pip", "a little AI companion that floats beside you", "#7ADC6E"),
    ("talk", "Talk to it", "it sees your world and answers out loud", "#6EC8DC"),
    ("danger", "It watches your back", "danger warnings, instantly", "#F05A78"),
    ("alive", "It feels alive", "it looks back at you · pet it", "#FFB347"),
    ("direct", "Ask it things", "spin · stay · come", "#AA8CFF"),
    ("skins", "Make it yours", "pick a skin, or draw your own", "#FF9EC4"),
    ("fairy", "New: fairies", "with fluttering wings", "#E6B8FF"),
    ("night", "Glows at night", "", "#6E8CE6"),
]
TOUR = [
    ("meet", "Meet Pip", "a little spirit who floats beside you, a stranger at first", "#7ADC6E"),
    ("see", "She sees your world", "and answers out loud", "#6EC8DC"),
    ("discover", "She discovers her powers", "she doesn't know what she can do yet", "#FFB347"),
    ("remember", "Weeks later, she remembers", "your adventures, your name, what you love", "#E6B8FF"),
    ("origin", "Her own story", "she finds where she comes from while you play", "#AA8CFF"),
    ("find", "She finds things", "animals, flowers, ores, places", "#7ADC6E"),
    ("guide", "Lead the way", "she floats ahead and waits for you", "#6EC8DC"),
    ("chop", "Helping hands", "she chops, mines and lights the way", "#FFB347"),
    ("danger", "She watches your back", "creepers, lava, big drops: instant warnings", "#F05A78"),
    ("protect", "She protects you", "", "#F05A78"),
    ("fight", "Out of your way", "", "#FF9EC4"),
    ("know", "She knows the world", "answers from a Minecraft knowledge base", "#6E8CE6"),
    ("feelings", "She has feelings", "hit her by accident, say sorry, pet her", "#FF9EC4"),
    ("spam", "Be nice", "", "#FFB347"),
    ("modes", "Your rules", "how much power she has, and how", "#AA8CFF"),
    ("night", "Glows at night", "", "#6E8CE6"),
    ("skins", "Make her yours", "pick a skin, or draw your own", "#FF9EC4"),
]
CUTS = {
    "demo": {"chapters": CHAPTERS, "title_at": "fairy", "end_at": "night", "out": "kindred-spirit-demo.mp4",
             "title": [("a cute AI companion for Minecraft", 56, "Semibold", (240, 236, 255)),
                       ("talk to it · it talks back · it never changes your world", 34, "Medium", (206, 200, 236))],
             "fine": ["Recorded live in a test world. Pip's answers are real AI replies (Gemini 3.1 Flash-Lite) "
                      "spoken by a local Kokoro voice; the player's voice is synthesized."]},
    "tour": {"chapters": TOUR, "title_at": "guide", "end_at": "night", "out": "kindred-spirit-tour.mp4",
             "title": [("Pip's journey: a living AI companion for Minecraft", 52, "Semibold", (240, 236, 255)),
                       ("she talks, remembers, helps, has feelings, and grows with you", 34, "Medium",
                        (206, 200, 236))],
             "fine": ["Recorded live in a test world. Pip's answers are real AI replies (Gemini 3.1 Flash-Lite; her "
                      "deeper thinking on Claude), spoken by a local Kokoro voice. The player's voice is synthesized.",
                      "\"Weeks later\" starts from prepared memories of a made-up player (demo/seed_journey.py), "
                      "imported the way a player brings her to a new world."]},
}


# ------------------------------------------------------------------ helpers

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed:\n" + " ".join(cmd)[:600] + "\n" + r.stderr[-2000:])


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout
    return float(out.strip())


def font(size, weight="Bold"):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


def wav_read(path):
    with wave.open(path) as w:
        rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        data = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float32) / 32768
    data = data.reshape(-1, ch).mean(axis=1) if ch > 1 else data
    if rate != SR:  # linear resampling is plenty for speech
        x = np.arange(int(len(data) * SR / rate)) * rate / SR
        data = np.interp(x, np.arange(len(data)), data)
    return data


def wav_seconds(path):
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ------------------------------------------------------------------ overlays (Pillow)

def rounded(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def chapter_card(n, title, sub, color, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ft, fs, fn = font(50, "Heavy"), font(31, "Medium"), font(34, "Heavy")
    tw = d.textlength(title, font=ft)
    sw = d.textlength(sub, font=fs) if sub else 0
    w = int(max(tw, sw) + 150)
    h = 128 if sub else 92
    x, y = 56, 52
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x + 4, y + 8, x + w + 4, y + h + 8), radius=36, fill=(0, 0, 0, 90))
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(img)
    rounded(d, (x, y, x + w, y + h), 36, (22, 20, 38, 205))
    cx, cy, r = x + 50, y + h // 2, 30
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=hexrgb(color) + (255,))
    d.text((cx, cy + 1), str(n), font=fn, fill=(28, 24, 44), anchor="mm")
    d.text((x + 100, y + (24 if sub else h // 2)), title, font=ft, fill=(255, 255, 255), anchor="la" if sub else "lm")
    if sub:
        d.text((x + 102, y + 82), sub, font=fs, fill=(214, 210, 236))
    img.save(path)


def dialogue_card(who, text, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fw, ft = font(40, "Heavy"), font(42, "Semibold")
    label = "You" if who == "player" else "Pip"
    color = (150, 205, 255) if who == "player" else (140, 236, 150)
    lines = textwrap.wrap(text, 52)
    lw = d.textlength(label + "  ", font=fw)
    tw = max(d.textlength(l, font=ft) for l in lines)
    bw, bh = int(lw + tw + 80), 40 + 58 * len(lines)
    x, y = (W - bw) // 2, H - 90 - bh
    rounded(d, (x, y, x + bw, y + bh), 30, (18, 16, 32, 200))
    d.text((x + 40, y + 24), label, font=fw, fill=color)
    for i, l in enumerate(lines):
        d.text((x + 40 + lw, y + 22 + 58 * i), l, font=ft, fill=(255, 255, 255))
    img.save(path)


def caption_card(text, path):
    """A note under the chapter title (what's going on, a setting's name)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ft = font(32, "Semibold")
    lines = textwrap.wrap(text, 70)
    tw = max(d.textlength(l, font=ft) for l in lines)
    x, y, bw, bh = 56, 200, int(tw + 56), 26 + 44 * len(lines)
    rounded(d, (x, y, x + bw, y + bh), 24, (255, 236, 160, 225))
    for i, l in enumerate(lines):
        d.text((x + 28, y + 14 + 44 * i), l, font=ft, fill=(40, 32, 20))
    img.save(path)


def card(background, path, title, lines, fine=None, icon=True):
    bg = background.resize((W, H)).filter(ImageFilter.GaussianBlur(22))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (30, 24, 60)), 0.45).convert("RGBA")
    # soft vignette
    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).ellipse((-W * 0.25, -H * 0.35, W * 1.25, H * 1.35), fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(120))
    dark = Image.new("RGBA", (W, H), (10, 8, 24, 255))
    bg = Image.composite(bg, dark, vig)
    d = ImageDraw.Draw(bg)
    y = 190
    if icon:
        ic = Image.open(os.path.join(ROOT, "mod", "src", "main", "resources", "assets", "kindredspirit", "icon.png")).convert("RGBA")
        ic = ic.resize((230, 230), Image.LANCZOS)
        bg.alpha_composite(ic, ((W - 230) // 2, y))
        y += 260
    ft = font(132, "Heavy")
    d.text((W // 2 + 4, y + 6), title, font=ft, fill=(0, 0, 0, 110), anchor="mt")
    d.text((W // 2, y), title, font=ft, fill=(255, 255, 255), anchor="mt")
    y += 170
    for text, size, weight, color in lines:
        d.text((W // 2, y), text, font=font(size, weight), fill=color, anchor="mt")
        y += int(size * 1.45)
    for k, text in enumerate(reversed(fine or [])):
        d.text((W // 2, H - 60 - 38 * k), text, font=font(25, "Regular"), fill=(200, 196, 224), anchor="mb")
    bg.convert("RGB").save(path)


# ------------------------------------------------------------------ the edit

def main():
    os.makedirs(TMP, exist_ok=True)
    video = os.path.join(REC, "video.mp4")
    events = [json.loads(l) for l in open(os.path.join(REC, "events.jsonl"))]
    marks = {e["name"]: e["t"] for e in events if e["type"] == "mark"}
    players = [(e["t"], e["file"]) for e in events if e["type"] == "player"]
    pips = [(e["t"], os.path.join(REC, e["file"])) for e in events if e["type"] == "pip"]
    lines = [(e["t"], e["text"]) for e in events if e["type"] == "line" and e.get("name") == "pip"]
    typed = [(e["t"], e["text"]) for e in events if e["type"] == "line" and e.get("name") == "you"]
    captions = [(e["t"], e["text"]) for e in events if e["type"] == "line" and e.get("name") == "caption"]
    cut = CUTS[CUT]

    pieces, timeline_sounds = [], []  # timeline_sounds: (piece index, local time, wav path)

    # title card on a blurred frame of the fairy chapter
    still = os.path.join(TMP, "still.png")
    t_still = marks.get(cut["title_at"], marks["meet"]) + 1.5
    run(["ffmpeg", "-y", "-v", "error", "-ss", str(t_still), "-i", video, "-frames:v", "1", still])
    bg = Image.open(still).convert("RGB")
    card(bg, os.path.join(TMP, "title.png"), "Kindred Spirit", cut["title"])
    pieces.append(still_clip(os.path.join(TMP, "title.png"), 4.0, "title"))

    for i, (name, title, sub, color) in enumerate(cut["chapters"], start=1):
        if name not in marks or name + "_end" not in marks:
            print("skipping chapter", name, "(no marks)")
            continue
        ts, te = marks[name], marks[name + "_end"]
        dur = te - ts
        overlays = []
        cpath = os.path.join(TMP, "chapter-%d.png" % i)
        chapter_card(i, title, sub, color, cpath)
        overlays.append((cpath, 0.35, dur - 0.45))
        # what the player says
        said = [(t - ts, f) for t, f in players if ts <= t < te]
        spoken = [(t - ts, txt) for t, txt in lines if ts - 0.2 <= t < te]
        for k, (tau, f) in enumerate(said):
            stem = os.path.basename(f).replace("_hq.wav", "").replace(".wav", "")
            text = LINES.get(stem, "")
            end = tau + wav_seconds(f) + 0.5
            nxt = [s for s, _ in spoken if s > tau]
            if nxt:
                end = min(end, nxt[0] - 0.05)
            if text:
                p = os.path.join(TMP, "say-%d-%d.png" % (i, k))
                dialogue_card("player", text, p)
                overlays.append((p, tau, min(end, dur - 0.2)))
            timeline_sounds.append((len(pieces), tau, f))
        # what the player typed in chat, and the notes about what's going on
        for k, (tau, text) in enumerate([(t - ts, x) for t, x in typed if ts <= t < te]):
            nxt = [s for s, _ in spoken if s > tau] + [t - ts for t, _ in typed if t - ts > tau]
            p = os.path.join(TMP, "typed-%d-%d.png" % (i, k))
            dialogue_card("player", text, p)
            overlays.append((p, tau, min(tau + 3.0, (min(nxt) - 0.05) if nxt else dur, dur - 0.2)))
        notes = [(t - ts, x) for t, x in captions if ts - 0.5 <= t < te]
        for k, (tau, text) in enumerate(notes):
            p = os.path.join(TMP, "note-%d-%d.png" % (i, k))
            caption_card(text, p)
            end = notes[k + 1][0] - 0.05 if k + 1 < len(notes) else dur - 0.2
            overlays.append((p, max(0.5, tau), end))
        # what Pip says (its voice may come in several sentence clips)
        for k, (tau, text) in enumerate(spoken):
            nxt = [s for s, _ in spoken if s > tau] + [s for s, _ in said if s > tau]
            limit = min(nxt) - 0.05 if nxt else dur - 0.2
            clips = [(t - ts, f) for t, f in pips if tau - 0.3 <= t - ts < limit + 0.3]
            end = max([c + wav_seconds(f) for c, f in clips], default=tau + 2.5) + 0.5
            p = os.path.join(TMP, "pip-%d-%d.png" % (i, k))
            dialogue_card("pip", text, p)
            overlays.append((p, max(0, tau), min(end, limit, dur - 0.2)))
        for t, f in pips:
            if ts - 0.3 <= t < te:
                timeline_sounds.append((len(pieces), t - ts, f))
        pieces.append(chapter_clip(video, ts, dur, overlays, name))

    end_still = os.path.join(TMP, "end-still.png")
    run(["ffmpeg", "-y", "-v", "error", "-ss", str(marks.get(cut["end_at"], marks["meet"]) + 2), "-i", video,
         "-frames:v", "1", end_still])
    card(Image.open(end_still).convert("RGB"), os.path.join(TMP, "end.png"), "Kindred Spirit",
         [("Open source (MIT) · contributors welcome", 50, "Semibold", (240, 236, 255)),
          ("Fabric 1.21.1 · client-side, nothing added to your world", 34, "Medium", (206, 200, 236)),
          ("local voice (Whisper + Kokoro) · bring your own AI", 34, "Medium", (206, 200, 236)),
          (REPO, 40, "Bold", (160, 236, 170))],
         fine=cut["fine"])
    pieces.append(still_clip(os.path.join(TMP, "end.png"), 6.5, "end"))

    # join with crossfades
    durs = [duration(p) for p in pieces]
    starts, acc = [], 0.0
    for k, d in enumerate(durs):
        starts.append(acc)
        acc += d - XF
    total = acc + XF
    inputs, chain, last = [], [], "0:v"
    for p in pieces:
        inputs += ["-i", p]
    for k in range(1, len(pieces)):
        out = "v%d" % k
        chain.append("[%s][%d:v]xfade=transition=fade:duration=%s:offset=%.3f[%s]" % (last, k, XF, starts[k], out))
        last = out
    silent = os.path.join(TMP, "joined.mp4")
    run(["ffmpeg", "-y", "-v", "error"] + inputs + ["-filter_complex", ";".join(chain), "-map", "[%s]" % last,
                                                    "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", silent])

    # sound: voices where they happened, music underneath that dips when someone speaks
    n = int((total + 0.5) * SR)
    voice = np.zeros(n)
    for piece, tau, f in timeline_sounds:
        t0 = starts[piece] + tau
        s = wav_read(f)
        i = int(t0 * SR)
        if i < 0 or i >= n:
            continue
        s = s[: n - i]
        voice[i:i + len(s)] += s * (0.95 if os.path.basename(f)[:2] in ("q_", "t_") else 1.0)
    music_path = os.path.join(TMP, "music.wav")
    with wave.open(music_path, "wb") as w:
        m = make_music(total + 0.5)
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes((m * 32767).astype("<i2").tobytes())
    with wave.open(music_path) as w:
        mus = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32).reshape(-1, 2) / 32768
    x = np.arange(n) * 44100 / SR
    mus = np.stack([np.interp(x, np.arange(len(mus)), mus[:, c]) for c in range(2)], axis=1)
    # ducking: follow the voice loudness with a fast attack and a slow release
    level = np.abs(voice)
    env = np.zeros(n)
    a, r, v = np.exp(-1 / (0.03 * SR)), np.exp(-1 / (0.45 * SR)), 0.0
    for k in range(0, n, 64):  # control rate is enough
        blk = level[k:k + 64].max()
        v = blk + (v - blk) * (a ** 64 if blk > v else r ** 64)
        env[k:k + 64] = v
    duck = 1 - 0.62 * np.clip(env / 0.08, 0, 1)
    base = np.full(n, 0.42)
    title_end, end_start = durs[0] - XF, starts[-1]
    base[: int(title_end * SR)] = 0.75                        # music up on the title and end cards
    base[int(end_start * SR):] = 0.75
    base = np.convolve(base, np.ones(SR) / SR, "same")          # smooth the level changes
    mix = mus * (base * duck)[:, None] + voice[:, None] * 0.92
    mix /= max(1.0, np.max(np.abs(mix)) / 0.95)
    mix_path = os.path.join(TMP, "mix.wav")
    with wave.open(mix_path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype("<i2").tobytes())

    final = os.path.join(OUT, cut["out"])
    # -14 LUFS: the loudness phones and video sites expect
    run(["ffmpeg", "-y", "-v", "error", "-i", silent, "-i", mix_path, "-c:v", "copy",
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", final])
    print("video:", final, "%.1f s" % duration(final))

    # a short, light preview for the README: the skins and the fairy
    k = [i for i, p in enumerate(pieces) if p.endswith("skins.mp4")]
    if k:
        gif = os.path.join(OUT, "demo-preview.gif" if CUT == "demo" else CUT + "-preview.gif")
        st = starts[k[0]] + 0.6
        run(["ffmpeg", "-y", "-v", "error", "-ss", "%.2f" % st, "-t", "10.5", "-i", final, "-vf",
             "fps=12,scale=640:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
             gif])
        print("preview:", gif)


def still_clip(png, seconds, name):
    out = os.path.join(TMP, name + ".mp4")
    frames = int(seconds * FPS)
    # a slow push-in, rendered from a 2x image so it moves smoothly
    run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", png, "-vf",
         "scale=%d:%d,zoompan=z='1+0.05*on/%d':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=%d:s=%dx%d:fps=%d,"
         "fade=t=in:st=0:d=0.6,format=yuv420p" % (W * 2, H * 2, frames, frames, W, H, FPS),
         "-frames:v", str(frames), "-c:v", "libx264", "-preset", "fast", "-crf", "16", out])
    return out


def chapter_clip(video, start, dur, overlays, name):
    out = os.path.join(TMP, name + ".mp4")
    args = ["ffmpeg", "-y", "-v", "error", "-ss", "%.3f" % start, "-t", "%.3f" % dur, "-i", video]
    chain, last = ["[0:v]fps=%d,scale=%d:%d,setsar=1,format=yuv420p[b0]" % (FPS, W, H)], "b0"
    for k, (png, a, b) in enumerate(overlays, start=1):
        length = max(0.3, b - a)
        args += ["-framerate", str(FPS), "-loop", "1", "-t", "%.3f" % length, "-i", png]
        chain.append("[%d:v]format=rgba,fade=t=in:st=0:d=0.3:alpha=1,fade=t=out:st=%.3f:d=0.3:alpha=1,"
                     "setpts=PTS-STARTPTS+%.3f/TB[o%d]" % (k, max(0, length - 0.3), a, k))
        chain.append("[%s][o%d]overlay=0:0:eof_action=pass[b%d]" % (last, k, k))
        last = "b%d" % k
    run(args + ["-filter_complex", ";".join(chain), "-map", "[%s]" % last, "-an",
                "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p", out])
    return out


if __name__ == "__main__":
    main()
