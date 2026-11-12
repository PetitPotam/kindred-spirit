"""Turning pages into clean text, cut into sections and chunks.

  parse_html(html)            a small DOM (standard library HTMLParser), forgiving of bad HTML
  wiki_sections(html)         a MediaWiki article (minecraft.wiki): infobox -> facts, crafting
                              grids -> recipes, tables -> rows, history/gallery/navboxes dropped
  web_sections(html)          any other page: the readable part (main/article), menus dropped
  markdown_sections(text)     a player's own notes or build guides
  chunk(sections)             sections -> search-sized chunks (~1200 characters)

A section is {"path": "Obtaining > Crafting", "text": "...", "data": {...}}; data holds what
could be read as structure (recipes, infobox fields).
"""
import html as htmllib
import re
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
        "track", "wbr"}
AUTOCLOSE = {"p": {"p"}, "li": {"li"}, "tr": {"tr", "td", "th"}, "td": {"td", "th"}, "th": {"td", "th"},
             "dt": {"dt", "dd"}, "dd": {"dt", "dd"}, "option": {"option"}}
BLOCK = {"p", "div", "section", "article", "main", "ul", "ol", "li", "table", "dl", "dt", "dd", "blockquote",
         "pre", "figure", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "header", "footer", "aside", "nav", "form",
         "center", "details", "summary", "caption"}
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = []
        self.parent = parent

    @property
    def classes(self):
        return set((self.attrs.get("class") or "").split())

    def iter(self):
        yield self
        for c in self.children:
            if isinstance(c, Node):
                yield from c.iter()

    def find(self, pred):
        for n in self.iter():
            if pred(n):
                return n
        return None

    def find_all(self, pred):
        return [n for n in self.iter() if pred(n)]

    def text(self, sep=""):
        out = []
        for c in self.children:
            if isinstance(c, Node):
                if c.tag in ("script", "style"):
                    continue
                if c.tag == "br":
                    out.append("\n")
                else:
                    out.append(c.text(sep))
            else:
                out.append(c)
        return sep.join(out)


def has_class(*names):
    names = set(names)
    return lambda n: bool(n.classes & names)


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        top = self.stack[-1]
        closes = AUTOCLOSE.get(tag)
        if closes and top.tag in closes and len(self.stack) > 1:
            self.stack.pop()
        node = Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if data:
            self.stack[-1].children.append(data)


def parse_html(text):
    b = _Builder()
    b.feed(text or "")
    b.close()
    return b.root


def clean(text):
    """Collapse spaces (keep line breaks), drop non-breaking/zero-width oddities."""
    text = text.replace("\xa0", " ").replace("​", "").replace("‌", "").replace("﻿", "")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ---------------------------------------------------------------- the generic walker

class Walker:
    """Walks a DOM and produces blocks: ("h", level, text) for headings, ("p", text, data) for text.
    special() may replace a node by (text, data); data {"recipes": [...]} found inside a list item or
    table cell is collected in pending_data and given to that item's or table's block."""

    skip_tags = {"script", "style", "noscript", "template", "svg", "iframe", "button", "select", "input", "img",
                 "audio", "video", "canvas", "map", "object"}
    skip_classes = set()
    skip_ids = set()

    def __init__(self):
        self.blocks = []
        self.buf = []

    # hooks for subclasses
    def special(self, node):
        """Return (text, data) to replace this node, or None to walk into it normally."""
        return None

    def skipped(self, node):
        if node.tag in self.skip_tags:
            return True
        if node.classes & self.skip_classes:
            return True
        if node.attrs.get("id") in self.skip_ids:
            return True
        if node.attrs.get("hidden") is not None or "display:none" in node.attrs.get("style", "").replace(" ", ""):
            return True
        return False

    def flush(self, data=None):
        text = clean("".join(self.buf))
        self.buf = []
        if text:
            self.blocks.append(("p", text, data))

    def inline(self, node):
        """All the text under node, flattened (used for list items, table cells, headings)."""
        out = []
        for c in node.children:
            if isinstance(c, Node):
                if self.skipped(c):
                    continue
                sp = self.special(c)
                if sp is not None:
                    out.append(" " + sp[0] + " ")
                    if sp[1]:
                        self.pending_data.extend(sp[1].get("recipes") or [])
                    continue
                if c.tag == "br":
                    out.append("\n")
                elif c.tag in BLOCK:
                    out.append(" " + self.inline(c) + " ")
                else:
                    out.append(self.inline(c))
            else:
                out.append(c)
        return "".join(out)

    pending_data = None

    def walk(self, node):
        for c in node.children:
            if not isinstance(c, Node):
                self.buf.append(c)
                continue
            if self.skipped(c):
                continue
            self.pending_data = []
            sp = self.special(c)
            if sp is not None:
                self.flush()
                if sp[0]:
                    self.blocks.append(("p", clean(sp[0]), sp[1]))
                continue
            tag = c.tag
            if tag in HEADINGS:
                self.flush()
                t = clean(self.inline(c)).replace("\n", " ")
                if t:
                    self.blocks.append(("h", HEADINGS[tag], t))
            elif tag == "br":
                self.buf.append("\n")
            elif tag == "li":
                self.flush()
                t = clean(self.inline(c)).replace("\n", " ")
                data = self.pending_data or None
                if t:
                    self.blocks.append(("p", "- " + t, {"recipes": data} if data else None))
            elif tag == "table":
                self.flush()
                self.table(c)
            elif tag == "pre":
                self.flush()
                t = c.text().strip("\n")
                if t.strip():
                    self.blocks.append(("p", t, None))
            elif tag in BLOCK:
                self.flush()
                self.walk(c)
                self.flush()
            else:
                self.walk(c)

    def table(self, node):
        rows = []
        self.pending_data = []
        for tr in node.find_all(lambda n: n.tag == "tr"):
            # rows of nested tables are read with their own table
            p = tr.parent
            while p is not None and p.tag != "table":
                p = p.parent
            if p is not node:
                continue
            cells = [re.sub(r"\s*\+\s*\n\s*", " + ", clean(self.inline(td))).replace("\n", ", ") for td in tr.children
                     if isinstance(td, Node) and td.tag in ("td", "th") and not self.skipped(td)]
            cells = [c for c in cells if c]
            if cells:
                rows.append(" | ".join(cells))
        cap = node.find(lambda n: n.tag == "caption")
        text = "\n".join(rows)
        if cap is not None:
            text = clean(cap.text()) + ":\n" + text
        if text.strip():
            data = self.pending_data
            self.blocks.append(("p", text, {"recipes": data} if data else None))

    def run(self, root):
        self.walk(root)
        self.flush()
        return self.blocks


def sections_from_blocks(blocks, skip=(), lead="Summary", skip_re=None):
    """Blocks -> sections with heading paths. Sections whose heading is in `skip` (any level), or
    matches skip_re, are dropped with everything under them."""
    skip = {s.lower() for s in skip}
    sections, path, cur, cur_data = [], [], [], []
    skipping_at = None

    def close():
        if cur:
            text = "\n\n".join(cur)
            data = {}
            for d in cur_data:
                for k, v in d.items():
                    if isinstance(v, list):
                        data.setdefault(k, []).extend(v)
                    else:
                        data[k] = v
            sections.append({"path": " > ".join(t for _, t in path) or lead, "text": text, "data": data or None})
        cur.clear()
        cur_data.clear()

    for b in blocks:
        if b[0] == "h":
            level, title = b[1], b[2]
            if skipping_at is not None and level > skipping_at:
                continue
            close()
            skipping_at = None
            while path and path[-1][0] >= level:
                path.pop()
            if title.lower() in skip or (skip_re is not None and skip_re.search(title)):
                skipping_at = level
                continue
            path.append((level, title))
        else:
            if skipping_at is not None:
                continue
            cur.append(b[1])
            if b[2]:
                cur_data.append(b[2])
    close()
    return sections


# ---------------------------------------------------------------- Minecraft Wiki (MediaWiki) pages

WIKI_SKIP_SECTIONS = ("Contents", "History", "Data history", "Development", "Gallery", "Screenshots",
                      "Mojang screenshots", "Concept artwork", "In other media", "Videos", "Video", "References",
                      "Notes", "External links", "Navigation", "Navigation menu", "Issues", "Trivia", "See also",
                      "Sounds", "Audio", "Achievements",
                      # identifiers, block states and the advancement lists every mob page repeats: about 10% of
                      # the text, and what a player asks is never in them
                      "Advancements", "Data values", "Block states", "Block data", "Entity data", "Item data", "ID",
                      "IDs", "Item tags", "Block tags", "Entity tags", "Fluid tags")
# sections only about another edition (dropped when the source is for one edition)
EDITION_SECTIONS = {"java": ("Bedrock Edition", "Legacy Console Edition", "Minecraft Education", "Education Edition",
                             "Pocket Edition", "New Nintendo 3DS Edition", "Bedrock Edition only"),
                    "bedrock": ("Java Edition", "Legacy Console Edition", "Java Edition only")}

# "Basic Bedrock Edition farms": a heading that names only the other edition
OTHER_EDITION_HEADING = {"java": re.compile(r"^(?!.*\b(Java|JE)\b).*\b(Bedrock|BE|Pocket|Legacy Console|Education)"
                                            r"( Edition)?\b"),
                         "bedrock": re.compile(r"^(?!.*\b(Bedrock|BE)\b).*\b(Java|JE)( Edition)?\b")}


# ---------------------------------------------------------------- one edition, one version

EDITION_TAG = re.compile(r"\[([^\[\]\n]{1,70})\]")


def _tag_action(tag, edition):
    """What to do with a wiki note like [BE only], [upcoming: JE 26.4] or [until: JE 1.21.5]:
    'drop' the fact before it, 'strip' the note and keep the fact, or None (not such a note)."""
    t = tag.strip().lower()
    if t.startswith("upcoming"):
        return "drop"   # not in the game yet, not even in the latest release
    if t.startswith("until"):
        return "strip"  # true until a later version: true for an older one
    if not t.endswith(" only"):
        return None
    if edition == "java":
        return "strip" if re.search(r"\b(je|java)\b", t) else "drop"
    if edition == "bedrock":
        return "strip" if re.search(r"\b(be|bedrock|pe|pocket)\b", t) else "drop"
    return None


def _fact_start(text, end):
    """Where the fact a note belongs to starts: after the previous separator on its line
    (| ; , ( or a sentence end), skipping over whole [...] groups (a recipe sentence). An
    alternative ("41/42[upcoming]", "repeater or repeater[upcoming]") goes with its "/" or "or"."""
    i, depth = end - 1, 0
    while i >= 0:
        ch = text[i]
        if ch == "]":
            depth += 1
        elif ch == "[":
            if not depth:
                return i + 1
            depth -= 1
        elif not depth:
            if ch in "\n|;,(" or (ch == "." and text[i + 1:i + 2] == " "):
                return i + 1
            if ch == "/":
                return i
            for conj in (" or ", " and "):
                if text[i - len(conj) + 1:i + 1] == conj:
                    return i - len(conj) + 1
        i -= 1
    return 0


def edition_filter(text, edition):
    """Keep what is true in one edition: "70%[JE only], 75%[BE only]" -> "70%" for Java; facts
    marked upcoming are dropped, [until: ...] notes are removed and their facts kept."""
    if not edition or "[" not in (text or ""):
        return text
    matches = [m for m in EDITION_TAG.finditer(text) if _tag_action(m.group(1), edition)]
    cut = len(text)  # right to left; a dropped fact may swallow notes before it
    for m in reversed(matches):
        if m.end() > cut:
            continue
        if _tag_action(m.group(1), edition) == "strip":
            text = text[:m.start()] + text[m.end():]
            cut = m.start()
        else:
            start = _fact_start(text, m.start())
            text = text[:start] + text[m.end():]
            cut = start
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\(\s*[,;/]?\s*\)", "", text)
    text = re.sub(r"\s*,(\s*,)+", ",", text)
    text = re.sub(r"(^|\n|\|)\s*[,;/]\s*", r"\1 ", text)
    text = re.sub(r"\s*[,;/]\s*(?=\||\n|$)", "", text)
    text = re.sub(r"\.\s*\.", ".", text)
    text = re.sub(r":\s*;", ":", text)
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).strip().split("."))
    except ValueError:
        return None


def wiki_since(html):
    """The first Java Edition release the page's History section names: when it was added (None
    when the page has no history, or names no Java release)."""
    i = html.find('id="History"')
    if i < 0:
        return None
    j = html.find("<h2", i + 20)
    seg = html[i:j if j > 0 else len(html)]
    vs = [v for v in (version_tuple(x) for x in re.findall(r'title="Java Edition (\d+\.\d+(?:\.\d+)?)"', seg)) if v]
    return ".".join(map(str, min(vs))) if vs else None


# page status from the wiki's own categories (exact names: "Pages needing historical sounds" is
# housekeeping on a current page, not a sign that it's old)
# (a page that only mentions an Education detail is in "Minecraft Education" too: only the kinds count)
SPINOFF = re.compile(r"^((Minecraft (Education|Earth|Dungeons|Legends|Story Mode|Mini-Series)|MinecraftEdu|"
                     r"Minecraft: Story Mode) (mobs|items|blocks|entities|characters|NPCs|structures|biomes|"
                     r"enchantments|features|locations)|Minecraft Mini-Series)$")


# pages about the game rather than in it: updates, people, websites, the films and toys
META_CATEGORIES = {"Named updates", "Development phases", "Websites", "Community", "People", "Mojang Studios",
                   "Mojang Studios employees", "Minecraft (franchise)", "Merchandise", "LEGO Minecraft", "Films",
                   "Novels", "Books", "Minecraft Live", "Real-world", "Versions", "Java Edition versions",
                   "Bedrock Edition versions", "Planned versions", "Events", "Video games", "Soundtracks"}


def wiki_status(meta, title="", lead="", game_version=None, edition=None):
    """Is this page about the game as the player has it? 'current', or why not: 'joke' (April
    Fools), 'spin-off' (Education, Earth, Dungeons...), 'meta' (updates, people, websites),
    'other-edition' (only in Bedrock),
    'removed' (removed or unused features), 'outdated' (a tutorial for an older version),
    'future' (added after the player's version, e.g. the Happy Ghast for a 1.21.1 player)."""
    cats = set((meta or {}).get("categories") or [])
    if "Joke features" in cats or any(c.endswith("(joke dimension)") for c in cats):
        return "joke"
    if any(SPINOFF.match(c) for c in cats):
        return "spin-off"
    # ("Bedrock Edition" is also on pages both editions share, like Brewing: only a page that says
    # nothing about Java, no Java history and no Java category, is Bedrock's alone)
    if edition == "java" and "Bedrock Edition" in cats and not (meta or {}).get("since_java") and \
            not any(re.search(r"\bJava\b", c) for c in cats):
        return "other-edition"
    if "Removed features" in cats or any(c.startswith(("Removed ", "Unused ")) for c in cats) or \
            "Unused features" in cats or title.endswith("(old)"):
        return "removed"
    if "Outdated tutorials" in cats or re.search(r"\b(as it formerly worked|this (tutorial|page|article) is outdated)\b",
                                                 (lead or "")[:600], re.I):
        return "outdated"
    if cats & META_CATEGORIES:
        return "meta"
    target = version_tuple(game_version) if game_version else None
    since = version_tuple((meta or {}).get("since_java") or "")
    # ("Java Edition upcoming" is on Zombie and Block too: a detail of theirs is upcoming)
    if target and ((since and since > target) or (not since and "In development" in cats)):
        return "future"
    return "current"


def slot_name(slot):
    """One crafting-grid slot -> a name: 'Iron Ingot', 'any Planks', or '' for an empty slot."""
    names = []
    for item in slot.find_all(has_class("invslot-item")):
        a = item.find(lambda n: n.attrs.get("title"))
        name = a.attrs["title"] if a is not None else ""
        if not name:
            img = item.find(lambda n: n.tag == "img" and n.attrs.get("alt"))
            name = img.attrs["alt"].split(":")[0].replace("Invicon ", "").rsplit(".", 1)[0] if img is not None else ""
        name = htmllib.unescape(name).strip()
        if name and name not in names:
            names.append(name)
    count = slot.find(has_class("invslot-stacksize"))
    n = clean(count.text()) if count is not None else ""
    if not names:
        return "", n
    if len(names) == 1:
        return names[0], n
    words = [x.split() for x in names]
    tail = []
    while all(len(w) > len(tail) for w in words) and len({tuple(w[len(w) - len(tail) - 1:]) for w in words}) == 1:
        tail = words[0][len(words[0]) - len(tail) - 1:]
    if tail:
        return "any " + " ".join(tail), n
    return "any of " + ", ".join(names[:4]) + (", ..." if len(names) > 4 else ""), n


def read_mcui(node):
    """A crafting/smelting interface (span.mcui) -> (sentence, recipe dict)."""
    kind = ""
    for c in node.classes:
        if c.startswith("mcui-") and c not in ("mcui-input", "mcui-output"):
            kind = c[5:].replace("_", " ").replace("&#95;", " ")
    inp = node.find(has_class("mcui-input"))
    out = node.find(has_class("mcui-output"))
    rows = []
    if inp is not None:
        row_nodes = inp.find_all(has_class("mcui-row")) or [inp]
        for r in row_nodes:
            slots = [s for s in r.children if isinstance(s, Node) and "invslot" in s.classes]
            rows.append([slot_name(s)[0] for s in slots])
    # the shape is what matters, not where it sits in the 3x3 grid: trim empty rows and columns
    while rows and not any(rows[-1]):
        rows.pop()
    while rows and not any(rows[0]):
        rows.pop(0)
    width = max((len(r) for r in rows), default=0)
    rows = [r + [""] * (width - len(r)) for r in rows]
    while width and not any(r[width - 1] for r in rows):
        rows = [r[:-1] for r in rows]
        width -= 1
    while width and not any(r[0] for r in rows):
        rows = [r[1:] for r in rows]
        width -= 1
    fuel = node.find(has_class("mcui-fuel"))
    result, count = ("", "")
    if out is not None:
        slot = out.find(has_class("invslot"))
        if slot is not None:
            result, count = slot_name(slot)
    shapeless = node.find(has_class("mcui-shapeless")) is not None
    recipe = {"station": kind or "crafting", "grid": rows, "output": result, "count": int(count) if count.isdigit() else 1,
              "shapeless": shapeless}
    ingredients = {}
    for r in rows:
        for name in r:
            if name:
                ingredients[name] = ingredients.get(name, 0) + 1
    recipe["ingredients"] = ingredients
    if not result or not ingredients:
        return "", None
    makes = "%s %s" % (recipe["count"], result)
    have = ", ".join("%d %s" % (n, name) for name, n in ingredients.items())
    if kind.lower() in ("furnace", "blast furnace", "smoker", "campfire"):
        text = "[%s recipe: smelt %s -> %s]" % (kind, have.split(" ", 1)[1] if have else "?", makes)
    elif shapeless:
        text = "[%s recipe (shapeless): %s -> %s]" % (kind or "Crafting", have, makes)
    else:
        names = {1: ["in one row"], 2: ["top row", "bottom row"], 3: ["top row", "middle row", "bottom row"]}.get(
            len(rows), ["row %d" % (i + 1) for i in range(len(rows))])
        grid = "; ".join("%s: %s" % (names[i], ", ".join(x or "empty" for x in r)) for i, r in enumerate(rows))
        text = "[%s recipe for %s: %s. Uses %s.]" % (kind or "Crafting", makes, grid, have)
    if fuel is not None:
        recipe["fuel"] = True
    return text, recipe


def read_infobox(node):
    """div.infobox -> (title, {field: value})."""
    title_n = node.find(has_class("infobox-title"))
    title = clean(title_n.text()) if title_n is not None else ""
    fields = {}
    for tr in node.find_all(lambda n: n.tag == "tr"):
        th = next((c for c in tr.children if isinstance(c, Node) and c.tag == "th"), None)
        td = next((c for c in tr.children if isinstance(c, Node) and c.tag == "td"), None)
        if th is None or td is None:
            continue
        k = wiki_polish(clean(th.text()).replace("\n", " ")).strip(" :")
        v = wiki_polish("; ".join(x.strip(" ;:") for x in clean(td.text()).split("\n") if x.strip(" ;:")))
        if k and v:
            fields[k] = v
    return title, fields


def wiki_polish(text):
    """What icons leave behind in wiki text: "20HP × 10" -> "20 HP (10 hearts)", "2 ()" -> "2"."""
    text = re.sub(r"(\d)HP × (\d+(?:\.\d+)?)", r"\1 HP (\2 hearts)", text)
    text = re.sub(r"(\d)HP\b", r"\1 HP", text)
    text = re.sub(r"\s*\(\s*\)", "", text)
    text = re.sub(r"(?:,\s*){2,}", ", ", text)
    text = re.sub(r"\s+,", ",", text)
    return re.sub(r",\s*(\||$)", r" \1", text, flags=re.M).replace(" \n", "\n").strip(" ,")


class WikiWalker(Walker):
    skip_classes = {"navbox", "mw-editsection", "reference", "references", "reflist", "mw-references-wrap", "toc",
                    "noprint", "hatnote", "mw-empty-elt", "gallery", "thumb", "msgbox", "printfooter", "catlinks",
                    "mw-jump-link", "load-page", "mw-collapsible-toggle", "sound", "mw-cite-backlink",
                    "infobox-imagearea", "infobox-imagelabel", "sprite-file", "notaninfobox-imagearea"}
    skip_ids = {"toc", "catlinks", "siteSub", "contentSub", "jump-to-nav"}

    def __init__(self, edition=None):
        super().__init__()
        self.infobox = None
        self.edition = edition

    def run(self, root):
        blocks = super().run(root)
        out = []
        for b in blocks:
            if b[0] == "h":
                out.append((b[0], b[1], wiki_polish(b[2])))
            else:
                t = edition_filter(wiki_polish(b[1]), self.edition)
                if t.strip(" -|"):
                    out.append((b[0], t, b[2]))
        return out

    def special(self, node):
        cls = node.classes
        if "mcui" in cls:
            text, recipe = read_mcui(node)
            return text, ({"recipes": [recipe]} if recipe else None)
        if "infobox" in cls and self.infobox is None:
            title, fields = read_infobox(node)
            self.infobox = {"title": title, "fields": fields}
            return "", None  # becomes its own "Facts" section
        if node.tag == "sup" and ("reference" in cls or node.attrs.get("id", "").startswith("cite_ref")):
            return "", None
        return None



def wiki_meta(html):
    """What the page itself says about itself: revision id, title, categories, canonical URL."""
    meta = {}
    m = re.search(r'"wgRevisionId":(\d+)', html)
    if m:
        meta["revid"] = int(m.group(1))
    m = re.search(r'"wgPageName":"((?:[^"\\]|\\.)*)"', html)
    if m:
        meta["page"] = m.group(1).encode().decode("unicode_escape", "ignore") if "\\u" in m.group(1) else m.group(1)
    m = re.search(r'"wgCategories":\[(.*?)\]', html)
    if m:
        meta["categories"] = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))
    m = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    if m:
        meta["canonical"] = htmllib.unescape(m.group(1))
    m = re.search(r'<h1[^>]*id="firstHeading"[^>]*>(.*?)</h1>', html, re.S)
    if m:
        meta["title"] = clean(htmllib.unescape(re.sub(r"<[^>]+>", "", m.group(1))))
    return meta


def wiki_links(html, article_path="/w/"):
    """The articles a page links to, from its body (not menus or navboxes), once each, in order."""
    root = parse_html(html)
    content = root.find(lambda n: n.attrs.get("id") == "mw-content-text") or root
    seen, out = set(), []
    for a in content.find_all(lambda n: n.tag == "a" and n.attrs.get("href", "").startswith(article_path)):
        p = a.parent
        skip = False
        while p is not None:
            if p.classes & {"navbox", "reference", "references", "hatnote", "msgbox", "infobox-imagearea"}:
                skip = True
                break
            p = p.parent
        if skip:
            continue
        t = a.attrs.get("title") or ""
        if not t or "?" in a.attrs["href"] or t.startswith(("File:", "Category:", "Special:", "Template:", "Help:",
                                                            "Minecraft Wiki:", "User:", "Talk:")):
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def wiki_aliases(html):
    """The names a page gives itself in bold in its first paragraph: "A **redstone comparator** (or
    **comparator**)", "**Experience** (**EXP** or **XP**)". Lowercase, at most 6."""
    root = parse_html(html)
    content = root.find(lambda n: n.attrs.get("id") == "mw-content-text") or root
    outputs = content.find_all(has_class("mw-parser-output"))
    body = max(outputs, key=lambda n: sum(1 for _ in n.iter())) if outputs else content
    first = next((c for c in body.children if isinstance(c, Node) and c.tag == "p" and clean(c.text()).strip()), None)
    if first is None:
        return []
    out = []
    for b in first.find_all(lambda n: n.tag == "b"):
        name = clean(b.text()).lower().strip(" .,:;")
        if 2 <= len(name) <= 40 and name not in out:
            out.append(name)
    return out[:6]


def wiki_sections(html, skip=WIKI_SKIP_SECTIONS, edition=None):
    """A MediaWiki article (full page or the parser output from api.php) -> (sections, data).
    edition ("java" or "bedrock"): keep what is true in that edition (see edition_filter)."""
    root = parse_html(html)
    # the article's own parser output, inside #mw-content-text: featured or protected pages carry a
    # small one first, in the page-status indicators
    content = root.find(lambda n: n.attrs.get("id") == "mw-content-text") or root
    outputs = content.find_all(has_class("mw-parser-output"))
    body = max(outputs, key=lambda n: sum(1 for _ in n.iter())) if outputs else content
    w = WikiWalker(edition)
    blocks = w.run(body)
    sections = sections_from_blocks(blocks, skip=tuple(skip) + EDITION_SECTIONS.get(edition or "", ()),
                                    skip_re=OTHER_EDITION_HEADING.get(edition or ""))
    data = {}
    recipes = [r for s in sections for r in ((s.get("data") or {}).get("recipes") or [])]
    if recipes:
        data["recipes"] = recipes
    if w.infobox and w.infobox["fields"]:
        data["infobox"] = w.infobox
        title = w.infobox["title"] or ""
        fields = {k: edition_filter(v, edition) for k, v in w.infobox["fields"].items()}
        w.infobox["fields"] = {k: v for k, v in fields.items() if v.strip(" ,;")}
        facts = "\n".join("%s: %s" % (k, v) for k, v in w.infobox["fields"].items())
        sections.insert(0, {"path": "Facts", "text": ("%s\n%s" % (title, facts)).strip(),
                            "data": {"infobox": w.infobox["fields"]}})
    return sections, data


# ---------------------------------------------------------------- any web page

class WebWalker(Walker):
    skip_tags = Walker.skip_tags | {"nav", "header", "footer", "aside", "form"}
    skip_words = ("nav", "navbar", "navigation", "menu", "sidebar", "footer", "cookie", "cookies", "breadcrumb",
                  "breadcrumbs", "share", "sharing", "social", "comments", "comment-list", "advert", "ad-slot",
                  "newsletter", "related-posts", "skip-link", "site-header", "site-footer")

    def skipped(self, node):
        if super().skipped(node):
            return True
        cls = " ".join(node.classes).lower() + " " + node.attrs.get("id", "").lower()
        toks = set(re.split(r"[\s_]+", cls))
        if toks & set(self.skip_words):
            return True
        if node.attrs.get("role") in ("navigation", "banner", "contentinfo", "complementary", "search"):
            return True
        if node.attrs.get("aria-hidden") == "true":
            return True
        return False


def web_title(root):
    t = root.find(lambda n: n.tag == "meta" and n.attrs.get("property") == "og:title")
    if t is not None and t.attrs.get("content"):
        return clean(t.attrs["content"])
    t = root.find(lambda n: n.tag == "title")
    if t is not None and clean(t.text()):
        return clean(t.text())
    h = root.find(lambda n: n.tag == "h1")
    return clean(h.text()) if h is not None else ""


def web_sections(html):
    """Any page -> (title, sections): the main/article part when the page marks one."""
    root = parse_html(html)
    title = web_title(root)
    main = (root.find(lambda n: n.tag == "main") or root.find(lambda n: n.tag == "article")
            or root.find(lambda n: n.attrs.get("role") == "main")
            or root.find(lambda n: n.attrs.get("id") in ("content", "main", "main-content"))
            or root.find(lambda n: n.tag == "body") or root)
    blocks = WebWalker().run(main)
    # the page's own <h1> repeats the title: don't make it a section level
    blocks = [b for b in blocks if not (b[0] == "h" and b[1] == 1 and b[2] == title)]
    return title, sections_from_blocks(blocks, lead="Introduction")


# ---------------------------------------------------------------- Markdown / text files

def _md_inline(line):
    line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)          # images
    line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)       # links
    line = re.sub(r"(\*\*|__)(.+?)\1", r"\2", line)            # bold
    line = re.sub(r"(?<![\w*])([*_])(\S.*?)\1(?![\w*])", r"\2", line)  # italics
    return line.replace("`", "")


def markdown_sections(text, fallback_title=""):
    """Markdown (or plain text) -> (title, sections). The first '# Title' names the document."""
    title, blocks, para, in_code = "", [], [], False
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        m = None if in_code else re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            if para:
                blocks.append(("p", clean("\n".join(para)), None))
                para = []
            level, heading = len(m.group(1)), _md_inline(m.group(2)).strip()
            if level == 1 and not title:
                title = heading
                continue
            blocks.append(("h", level, heading))
        elif not line.strip():
            if para:
                blocks.append(("p", clean("\n".join(para)), None))
                para = []
        else:
            para.append(line if in_code else _md_inline(line))
    if para:
        blocks.append(("p", clean("\n".join(para)), None))
    return title or fallback_title, sections_from_blocks(blocks, lead="Introduction")


# ---------------------------------------------------------------- chunking

def _split_long(text, max_chars, repeat_head=True):
    if len(text) <= max_chars:
        return [text]
    lines = text.split("\n")
    if len(lines) > 1:  # tables and lists: cut between lines; a table's header row starts every piece
        head = ""
        if not repeat_head:
            pass
        elif " | " in lines[0]:
            head = lines[0]
        elif lines[0].endswith(":") and len(lines) > 2 and " | " in lines[1]:
            head = lines[0] + "\n" + lines[1]
        if len(head) > max_chars // 3:
            head = ""
        out, cur = [], ""
        for line in lines:
            if cur and len(cur) + 1 + len(line) > max_chars:
                out.append(cur)
                cur = (head + "\n" + line) if head else line
            else:
                cur = cur + "\n" + line if cur else line
        if cur:
            out.append(cur)
        if len(out) == 1 and len(lines) == 1:
            return out
        # a piece still too long (one enormous row): cut it further, without adding the header again
        return [p for o in out for p in (_split_long(o, max_chars, False) if len(o) > max_chars else [o])]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out, cur = [], ""
    for s in sentences:
        while len(s) > max_chars:  # one enormous "sentence"
            out.append(s[:max_chars])
            s = s[max_chars:]
        if cur and len(cur) + 1 + len(s) > max_chars:
            out.append(cur)
            cur = s
        else:
            cur = cur + " " + s if cur else s
    if cur:
        out.append(cur)
    return out


def chunk(sections, max_chars=1200):
    """Sections -> chunks [{section, text, data}], each at most ~max_chars, cut between
    paragraphs, then lines, then sentences. A section's data stays with the chunk that holds it."""
    out = []
    for s in sections:
        paras = [p for p in s["text"].split("\n\n") if p.strip()]
        pieces, cur = [], ""
        for p in paras:
            for part in _split_long(p, max_chars):
                if cur and len(cur) + 2 + len(part) > max_chars:
                    pieces.append(cur)
                    cur = part
                else:
                    cur = cur + "\n\n" + part if cur else part
        if cur:
            pieces.append(cur)
        data = s.get("data") or {}
        recipes = data.get("recipes") or []
        for i, text in enumerate(pieces):
            d = {k: v for k, v in data.items() if k != "recipes"} if i == 0 else {}
            mine = [r for r in recipes if r.get("output") and r["output"] in text and "recipe" in text]
            if mine:
                d["recipes"] = mine
            out.append({"section": s["path"], "text": text, "data": d or None})
    return out
