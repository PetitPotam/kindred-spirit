"""Finding the blueprint the player means, in the catalogue the mod keeps next to the files.

The mod describes every file in her blueprints folders (catalogue.json: a category, a biome or style, what it
is in plain words, its size, block count, beds, materials, tags; see mod/.../blueprint/Catalogue.java). This
searches it the way people ask: "a small desert house", "something big", "a house for three", "the plains
smithy", "a ship", and answers with a few short descriptions and sizes, best first, so she can say what they
look like and ask which one when several fit. Files the mod hasn't described yet (just added, or the game
isn't running) are still found by their names.
"""
import json
import os
import re

CATEGORY_WORDS = {
    "house": ("house", "home", "hut", "cottage", "cabin", "igloo", "shelter", "lodge", "dwelling"),
    "workshop": ("workshop", "shop", "smithy", "forge", "smith", "armorer", "armourer", "weaponsmith", "toolsmith",
                 "library", "temple", "church", "tannery", "mason", "shepherd", "fletcher", "cartographer", "butcher",
                 "fisher", "job"),
    "farm": ("farm", "field", "crop", "crops", "pen", "stable", "barn", "animals"),
    "well": ("well", "fountain", "square", "bell", "meeting"),
    "portal": ("portal", "nether"),
    "ship": ("ship", "boat", "wreck", "shipwreck"),
    "tower": ("tower", "watchtower", "lookout"),
    "castle": ("castle", "fort", "fortress", "keep", "palace"),
    "shape": ("circle", "shape", "ring", "round"),
    "decoration": ("decoration", "decor", "ornament"),
}
BIOMES = {"plains": "plains", "plain": "plains", "desert": "desert", "savanna": "savanna", "taiga": "taiga", "snowy": "snowy",
          "snow": "snowy", "winter": "snowy", "sandy": "desert", "sand": "desert", "forest": "taiga", "spruce": "taiga"}
SIZE_WORDS = {"tiny": ("tiny",), "little": ("tiny", "small"), "small": ("tiny", "small"), "medium": ("medium",),
              "big": ("big", "medium"), "large": ("big", "medium"), "huge": ("big",), "giant": ("big",),
              "biggest": ("big",), "enormous": ("big",)}
NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
FILLER = {"a", "an", "the", "of", "some", "something", "one", "me", "us", "for", "with", "please", "build", "make",
          "pip", "can", "you", "i", "want", "like", "that", "this", "to", "and", "people", "person", "is", "it"}
BIG_BLOCKS = 600   # confirm before building one this big
BIG_SIDE = 20


def load(dirs):
    """Every blueprint in the folders: catalogue entries, plus bare ones for files not described yet."""
    out = []
    for d in dirs:
        try:
            files = sorted(f for f in os.listdir(d) if f.lower().endswith((".nbt", ".schem", ".litematic"))
                           and not f.startswith("."))
        except OSError:
            continue
        described = {}
        try:
            with open(os.path.join(d, "catalogue.json"), encoding="utf-8") as fh:
                for e in json.load(fh).get("entries") or []:
                    described[e.get("file")] = dict(e, dir=d)
        except (OSError, ValueError):
            pass
        for f in files:
            out.append(described.get(f) or {"file": f, "name": f.rsplit(".", 1)[0], "dir": d, "category": "",
                                             "what": f.rsplit(".", 1)[0].replace("_", " "), "new": True})
    return out


def _stem(w):
    return w[:-1] if w.endswith("s") and len(w) > 3 and not w.endswith("ss") else w


def parse(query):
    """What the words ask for: categories, biome, sizes, beds, and the other words."""
    t = (query or "").lower()
    for k, v in NUMBERS.items():
        t = re.sub(r"\b%s\b" % k, str(v), t)
    words = [_stem(w) for w in re.findall(r"[a-z0-9]+", t)]
    want = {"categories": set(), "style": None, "sizes": None, "beds": 0, "words": []}
    m = re.search(r"\bfor (\d+)\b|\b(\d+) (?:people|persons?|of us|beds?)\b", t)
    if m:
        want["beds"] = int(m.group(1) or m.group(2))
    for w in words:
        cat = next((c for c, ws in CATEGORY_WORDS.items() if w in ws), None)
        if cat:
            want["categories"].add(cat)
        if w in BIOMES:
            want["style"] = BIOMES[w]
        elif w in SIZE_WORDS:
            want["sizes"] = SIZE_WORDS[w]
            want["size_word"] = {"little": "small", "large": "big", "huge": "big", "giant": "big"}.get(w, w)
        if w not in FILLER and not w.isdigit() and w not in SIZE_WORDS and w not in BIOMES and not cat:
            want["words"].append(w)
        elif cat and w not in ("house", "home") and w not in FILLER:
            want["words"].append(w)  # (the trade itself still helps: "armorer" over another workshop)
    return want


def score(e, want):
    """How well one blueprint fits; None if it can't be what they mean."""
    text = " ".join([e.get("name", ""), e.get("what", ""), " ".join(e.get("tags") or [])]).lower().replace("_", " ")
    s = 0.0
    if want["categories"]:
        if e.get("category") in want["categories"]:
            s += 3
        elif e.get("category"):
            return None
    if want["style"]:
        if e.get("style") == want["style"] or want["style"] in text:
            s += 3
        elif e.get("style"):
            return None
    if want["sizes"] and e.get("size"):
        s += 2 if e["size"] == want["sizes"][0] else 1 if e["size"] in want["sizes"] else -2
        named = (e.get("name", "") + " " + e.get("what", "")).lower().replace("_", " ")  # (not the size tag)
        if want.get("size_word") and re.search(r"\b%s\b" % want["size_word"], named):
            s += 1  # ("a small house" over a medium house that happens to be small)
    if want["beds"]:
        beds = e.get("beds") or 0
        s += 2 if beds >= want["beds"] else (-3 if e.get("category") == "house" else -1)
    for w in want["words"]:
        if re.search(r"\b%s" % re.escape(w), text):
            s += 1.5
        elif w in text:
            s += 0.5
    if not any((want["categories"], want["style"], want["sizes"], want["words"], want["beds"])):
        return 0.0
    return s


def short(e):
    """One line for her: what it is and how big."""
    if e.get("new"):
        return {"name": e["name"], "what": e["what"], "note": "just added: not described yet (the game describes new "
                "files within a minute while it runs)"}
    out = {"name": e["name"], "what": e["what"], "category": e.get("category"),
           "size": "%s x %s, %s high" % (e.get("width"), e.get("length"), e.get("height")),
           "blocks": e.get("blocks"), "how_big": e.get("size")}
    if is_big(e):
        out["big"] = True
    return out


def is_big(e):
    return (e.get("blocks") or 0) > BIG_BLOCKS or max(e.get("width") or 0, e.get("length") or 0) > BIG_SIDE


def search(query, dirs, limit=6):
    entries = load(dirs)
    if not entries:
        return {"ok": False, "error": "There are no blueprint files yet (only the cottage you can make up)."}
    kinds = {}
    for e in entries:
        kinds[e.get("category") or "not described yet"] = kinds.get(e.get("category") or "not described yet", 0) + 1
    out = {"ok": True, "total": len(entries), "kinds": kinds}
    want = parse(query)
    if not (query or "").strip():
        out["say"] = "Tell what kinds there are; offer to look for something in particular."
        return out
    scored = []
    for e in entries:
        s = score(e, want)
        if s is not None and (s > 0 or not (want["words"] or want["categories"] or want["style"])):
            scored.append((s, -(e.get("blocks") or 0) if want["sizes"] and "big" in want["sizes"] else 0, e["name"], e))
    if not scored and want["words"]:  # nothing in that category or biome: the words alone
        scored = [(sum(w in (e.get("what", "") + " " + e["name"]).lower() for w in want["words"]), 0, e["name"], e)
                  for e in entries]
        scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))
    best = [x for x in scored if x[0] >= (scored[0][0] - 1 if scored else 0)]
    out["matches"] = [short(x[3]) for x in scored[:limit]]
    out["more"] = max(0, len(scored) - limit)
    if not scored:
        out["say"] = "None fits: say so, tell what kinds there are, or offer the cottage you can make up."
    elif len(best) > 1:
        out["say"] = ("Several fit: describe the two or three best in a few words (how they look, how big) and ask "
                      "which one before building.")
    else:
        out["say"] = "One fits best: name it in a few words and its size; build it if that's clearly what they want."
    if want["beds"]:
        out["say"] += " You can also make up a cottage with a bed each (blueprint with what='cottage', people=%d)." % want["beds"]
    if any(m.get("big") for m in out["matches"][:3]):
        out["say"] += " A big one: confirm before building it."
    return out


# ---------------------------------------------------------------------- the folders, for the dashboard

DIRS = [os.path.expanduser(p) for p in os.environ.get("KINDRED_BLUEPRINTS", "").split(os.pathsep) if p] or [
    os.path.expanduser("~/Library/Application Support/minecraft-kindred/config/kindredspirit/blueprints"),
    os.path.expanduser("~/Library/Application Support/minecraft-kindred/schematics")]
EXTENSIONS = (".nbt", ".schem", ".litematic")
MAX_BYTES = 16 * 1024 * 1024
TRASH = ".trash"
PICTURE = re.compile(r"^[a-z0-9._-]+\.(top|front)\.png$")


def overview(dirs=None):
    """Every folder: its catalogue (entries, categories, sources), files not described yet, unreadable ones, trash."""
    out = []
    for i, d in enumerate(dirs or DIRS):
        info = {"index": i, "dir": d, "exists": os.path.isdir(d), "entries": [], "new": [], "errors": [], "trash": [],
                "sources": "", "categories": {}, "generated": None}
        if info["exists"]:
            try:
                with open(os.path.join(d, "catalogue.json"), encoding="utf-8") as fh:
                    cat = json.load(fh)
                info.update({k: cat.get(k) for k in ("entries", "errors", "categories", "generated") if cat.get(k) is not None})
                info["sources"] = cat.get("sources") or ""
            except (OSError, ValueError):
                pass
            if not info["sources"]:
                try:
                    with open(os.path.join(d, "SOURCES.txt"), encoding="utf-8") as fh:
                        info["sources"] = fh.read()
                except OSError:
                    pass
            known = {e.get("file") for e in info["entries"]} | {e.get("file") for e in info["errors"]}
            files = sorted(f for f in os.listdir(d) if f.lower().endswith(EXTENSIONS) and not f.startswith("."))
            info["entries"] = [e for e in info["entries"] if e.get("file") in files]  # (removed since)
            info["new"] = [f for f in files if f not in known]
            try:
                info["trash"] = sorted(f for f in os.listdir(os.path.join(d, TRASH)) if f.lower().endswith(EXTENSIONS))
            except OSError:
                pass
        out.append(info)
    return {"dirs": out}


def _clean_name(name):
    base = os.path.basename(str(name or "")).strip()
    base = re.sub(r"[^A-Za-z0-9 ._-]", "_", base).strip(" .")
    if not base.lower().endswith(EXTENSIONS):
        raise ValueError("a blueprint is a .nbt, .schem or .litematic file")
    if base.startswith("."):
        raise ValueError("not a hidden file")
    return base


def add(d, name, data, replace=False):
    """A file from the dashboard into the folder (the game describes it within a minute while it runs)."""
    base = _clean_name(name)
    if not data:
        raise ValueError("the file is empty")
    if len(data) > MAX_BYTES:
        raise ValueError("too big (%d MB; at most 16)" % (len(data) // (1024 * 1024)))
    if not (data[:2] == b"\x1f\x8b" or data[:1] == b"\x0a"):
        raise ValueError("that doesn't look like a Minecraft schematic (NBT)")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, base)
    if os.path.exists(path) and not replace:
        raise ValueError("there's already a %s: remove it first, or replace it" % base)
    tmp = path + ".part"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)
    return {"ok": True, "added": base, "bytes": len(data)}


def remove(d, name):
    """Into the folder's .trash (never deleted): out of her catalogue, back with restore."""
    base = _clean_name(name)
    src = os.path.join(d, base)
    if not os.path.isfile(src):
        raise ValueError("no %s here" % base)
    os.makedirs(os.path.join(d, TRASH), exist_ok=True)
    dst = os.path.join(d, TRASH, base)
    if os.path.exists(dst):
        stem, ext = os.path.splitext(base)
        dst = os.path.join(d, TRASH, "%s.%d%s" % (stem, int(time_now()), ext))
    os.replace(src, dst)
    return {"ok": True, "removed": base, "trash": os.path.basename(dst)}


def restore(d, name):
    base = _clean_name(name)
    src = os.path.join(d, TRASH, base)
    if not os.path.isfile(src):
        raise ValueError("no %s in the trash" % base)
    dst = os.path.join(d, re.sub(r"\.\d{9,}(?=\.\w+$)", "", base))
    if os.path.exists(dst):
        raise ValueError("there's already a %s" % os.path.basename(dst))
    os.replace(src, dst)
    return {"ok": True, "restored": os.path.basename(dst)}


def picture(d, name):
    """A picture the game drew (.catalogue/<name>.top.png or .front.png), or None."""
    if not PICTURE.match(name or ""):
        return None
    path = os.path.join(d, ".catalogue", name)
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def time_now():
    import time
    return time.time()
