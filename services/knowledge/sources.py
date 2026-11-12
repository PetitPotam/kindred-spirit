"""Where knowledge comes from. Each source is an adapter that can:

    discover(fetcher, opts)  -> the Items to fetch (key, title, url, token)
    fetch(fetcher, item)     -> a Document (title, url, sections, data, meta), or GONE
    params(opts)             -> what to remember so `kb.py refresh` can ask again later

A token says which version an item is in (a wiki revision id, a sitemap lastmod, a file's
mtime): when the stored page has the same token, the crawler does not fetch it again.

Kinds shipped:
  mediawiki   a MediaWiki wiki: through api.php when its robots.txt allows it; otherwise (as on
              minecraft.wiki, whose robots.txt disallows api.php) through the article pages,
              the category pages and the sitemap, which it does allow
  web         any site: a list of URLs and/or a sitemap, the readable part of each page
  local       Markdown/text files in a folder (a player's own build guides and notes)

Built-in sources: "minecraft-wiki" and "local". More are added to sources.json in the
knowledge folder (or with `kb.py add`), see docs/KNOWLEDGE.md.
"""
import gzip
import hashlib
import html as htmllib
import json
import os
import re
import time
import urllib.parse

from . import textify
from .fetcher import Blocked


class Item:
    __slots__ = ("key", "title", "url", "token")

    def __init__(self, key, title="", url="", token=None):
        self.key, self.title, self.url, self.token = key, title, url, token

    def __repr__(self):
        return "Item(%r, token=%r)" % (self.key, self.token)


class Document:
    def __init__(self, key, title, url, sections, data=None, meta=None, token=None):
        self.key = key
        self.title = title
        self.url = url
        self.sections = sections
        self.data = data or {}
        self.meta = meta or {}
        self.token = token

    @property
    def hash(self):
        h = hashlib.sha1()
        h.update(self.title.encode("utf-8"))
        for s in self.sections:
            h.update(b"\x00" + s["path"].encode("utf-8") + b"\x01" + s["text"].encode("utf-8"))
        return h.hexdigest()


GONE = object()  # the page no longer exists: remove it


class Source:
    kind = ""

    def __init__(self, name, config):
        self.name = name
        self.config = dict(config)
        self.title = config.get("title") or name
        self.license = config.get("license") or "unknown: check the site's terms before using it"
        self.license_url = config.get("license_url") or ""
        self.attribution = config.get("attribution") or self.title
        self.edition = config.get("edition") or ""
        self.delay = config.get("delay")

    def describe(self):
        return {"name": self.name, "kind": self.kind, "title": self.title, "license": self.license,
                "license_url": self.license_url, "attribution": self.attribution, "edition": self.edition,
                "terms": self.config.get("terms", "")}

    def params(self, opts):
        return {}

    def discover(self, fetcher, opts, log):
        raise NotImplementedError

    def fetch(self, fetcher, item, offline=False):
        raise NotImplementedError


# ---------------------------------------------------------------- sitemaps

def _ungzip(body):
    return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body


def read_sitemap(fetcher, url, log, depth=0, offline=False, max_age=None):
    """A sitemap (or sitemap index, followed one level) -> {url: lastmod or None}."""
    try:
        r = fetcher.get(url, offline=offline, max_age=max_age)
    except Blocked as exc:
        log("  skipped sitemap: %s" % exc)
        return {}
    if r.status != 200:
        log("  sitemap %s: HTTP %s" % (url, r.status))
        return {}
    text = _ungzip(r.body).decode("utf-8", "replace")
    out = {}
    if "<sitemapindex" in text and depth == 0:
        for loc in re.findall(r"<sitemap>.*?<loc>\s*(.*?)\s*</loc>", text, re.S):
            out.update(read_sitemap(fetcher, htmllib.unescape(loc), log, depth + 1, offline, max_age))
        return out
    for block in re.findall(r"<url>(.*?)</url>", text, re.S):
        loc = re.search(r"<loc>\s*(.*?)\s*</loc>", block, re.S)
        if not loc:
            continue
        mod = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", block, re.S)
        out[htmllib.unescape(loc.group(1))] = mod.group(1) if mod else None
    return out


# ---------------------------------------------------------------- MediaWiki (minecraft.wiki)

class MediaWikiSource(Source):
    kind = "mediawiki"

    def __init__(self, name, config):
        super().__init__(name, config)
        self.base = config["base"].rstrip("/")
        self.article_path = config.get("article_path", "/w/")
        self.api = self.base + config.get("api_path", "/api.php")
        self.mode = config.get("mode", "auto")   # auto | api | html
        self.sitemaps = [urllib.parse.urljoin(self.base + "/", s) for s in config.get("sitemaps", [])]
        self.namespaces = set(config.get("namespaces", ["", "Tutorial"]))
        self.skip_titles = [re.compile(p) for p in config.get("skip_titles", [])]
        self.skip_sections = config.get("skip_sections") or textify.WIKI_SKIP_SECTIONS
        self._lastmods = None
        self._lastmods_at = 0.0

    # names and addresses
    def url_of(self, title):
        return self.base + self.article_path + urllib.parse.quote(title.replace(" ", "_"), safe=":/()',!*-._~")

    def title_of(self, url):
        path = urllib.parse.urlsplit(url).path
        if not path.startswith(self.article_path):
            return None
        return urllib.parse.unquote(path[len(self.article_path):]).replace("_", " ")

    def wanted(self, title):
        ns = title.split(":", 1)[0] if ":" in title else ""
        if ns not in self.namespaces:
            return False
        return not any(p.search(title) for p in self.skip_titles)

    def use_api(self, fetcher):
        if self.mode in ("api", "html"):
            return self.mode == "api"
        return fetcher.allowed(self.api + "?action=query&format=json")

    def params(self, opts):
        p = {}
        for k in ("categories", "pages", "depth", "all"):
            if opts.get(k):
                p[k] = opts[k]
        return p

    def lastmods(self, fetcher, log, offline=False, max_age=None):
        """url -> lastmod from the wiki's sitemaps (fetched once per run): the cheap way to know
        which pages changed without asking for each one. max_age: a cached sitemap younger than
        that many seconds is used as it is."""
        if self._lastmods is None or (max_age and time.time() - self._lastmods_at > max_age):
            self._lastmods = {}
            self._lastmods_at = time.time()
            for sm in self.sitemaps:
                self._lastmods.update(read_sitemap(fetcher, sm, log, offline=offline, max_age=max_age))
        return self._lastmods

    # ---- finding the pages that answer one question (on-demand learning, see learn.py)
    def find_pages(self, fetcher, query, log, n=10, max_age=None):
        """Titles worth reading for a question: the wiki's own search when robots.txt allows the
        API; otherwise every title in the sitemaps (articles and tutorials), as Items with tokens,
        for learn.py to rank."""
        if self.use_api(fetcher):
            data = self._api(fetcher, action="query", list="search", srsearch=query, srlimit=str(n),
                             srnamespace=self.config.get("search_namespaces", "0"), srwhat="text")
            hits = [h["title"] for h in (data.get("query") or {}).get("search", [])]
            return [it for it in self._api_titles(fetcher, hits)] if hits else []
        out = []
        for url, lm in self.lastmods(fetcher, log, max_age=max_age).items():
            t = self.title_of(url)
            if t and self.wanted(t):
                out.append(Item(t, t, url, "lastmod:" + lm if lm else None))
        return out

    def _item(self, title, token=None):
        url = self.url_of(title)
        return Item(title, title, url, token)

    # ---- discovery
    def discover(self, fetcher, opts, log):
        api = self.use_api(fetcher)
        if not api:
            log("  %s: robots.txt disallows api.php, so reading article and category pages instead" % self.title)
        seen = set()
        cats = opts.get("categories") or []
        depth = int(opts.get("depth", self.config.get("depth", 1)))
        sources = []
        if opts.get("pages"):
            sources.append(self._api_titles(fetcher, opts["pages"]) if api else
                           (self._item(t.strip()) for t in opts["pages"]))
        for c in cats:
            sources.append(self._api_category(fetcher, c, depth, log) if api else
                           self._html_category(fetcher, c, depth, log, set()))
        if opts.get("all"):
            sources.append(self._api_all(fetcher) if api else self._sitemap_all(fetcher, log))
        lastmods = None if api else self.lastmods(fetcher, log, offline=opts.get("offline"))
        for gen in sources:
            for it in gen:
                if it.key in seen or not self.wanted(it.key):
                    continue
                seen.add(it.key)
                if it.token is None and lastmods:
                    lm = lastmods.get(it.url)
                    it.token = "lastmod:" + lm if lm else None
                yield it

    def _html_category(self, fetcher, cat, depth, log, visited):
        title = cat if cat.lower().startswith("category:") else "Category:" + cat
        if title in visited:
            return
        visited.add(title)
        try:
            r = fetcher.get(self.url_of(title))
        except Blocked as exc:
            log("  skipped %s: %s" % (title, exc))
            return
        if r.status != 200:
            log("  %s: HTTP %s" % (title, r.status))
            return
        root = textify.parse_html(r.text)
        pages = root.find(lambda n: n.attrs.get("id") == "mw-pages")
        subcats = root.find(lambda n: n.attrs.get("id") == "mw-subcategories")
        if pages is not None:
            more = False
            for a in pages.find_all(lambda n: n.tag == "a" and n.attrs.get("href")):
                href = a.attrs["href"]
                if "?" in href:  # "next page" (?pagefrom=...): robots.txt disallows those listings
                    more = more or "pagefrom" in href
                    continue
                t = a.attrs.get("title") or self.title_of(urllib.parse.urljoin(self.base, href))
                if t:
                    yield self._item(t)
            if more:
                log("  %s lists more than one page of members; its next pages are off-limits (robots.txt), so "
                    "only the first page is taken. Crawl its subcategories, or --all with the sitemap." % title)
        if subcats is not None and depth > 0:
            for a in subcats.find_all(lambda n: n.tag == "a" and n.attrs.get("href")):
                t = a.attrs.get("title") or ""
                if t.startswith("Category:") and "?" not in a.attrs["href"]:
                    yield from self._html_category(fetcher, t, depth - 1, log, visited)

    def _sitemap_all(self, fetcher, log):
        for url, lm in sorted(self.lastmods(fetcher, log).items()):
            t = self.title_of(url)
            if t:
                yield Item(t, t, url, "lastmod:" + lm if lm else None)

    def _api(self, fetcher, **params):
        params.update({"format": "json", "formatversion": "2", "maxlag": "5"})
        url = self.api + "?" + urllib.parse.urlencode(params)
        for _ in range(4):
            r = fetcher.get(url, revalidate=True)
            data = r.json()
            err = data.get("error") or {}
            if err.get("code") == "maxlag":  # the wiki is busy: come back later
                fetcher.sleep(5)
                fetcher.drop(url)
                continue
            return data
        raise RuntimeError("%s stays busy (maxlag)" % self.base)

    def _api_pages(self, fetcher, **params):
        cont = {}
        while True:
            data = self._api(fetcher, **dict(params, **cont))
            for p in (data.get("query") or {}).get("pages", []):
                yield p
            if "continue" not in data:
                return
            cont = data["continue"]

    def _api_titles(self, fetcher, titles):
        titles = [t.strip() for t in titles if t.strip()]
        for i in range(0, len(titles), 50):
            for p in self._api_pages(fetcher, action="query", prop="info", titles="|".join(titles[i:i + 50]),
                                     redirects="1"):
                if not p.get("missing"):
                    yield self._item(p["title"], "rev:%s" % p.get("lastrevid"))

    def _api_category(self, fetcher, cat, depth, log, visited=None):
        visited = visited if visited is not None else set()
        title = cat if cat.lower().startswith("category:") else "Category:" + cat
        if title in visited:
            return
        visited.add(title)
        subcats = []
        for p in self._api_pages(fetcher, action="query", generator="categorymembers", gcmtitle=title,
                                 gcmlimit="500", gcmtype="page|subcat", prop="info"):
            if p.get("ns") == 14:
                subcats.append(p["title"])
            else:
                yield self._item(p["title"], "rev:%s" % p.get("lastrevid"))
        if depth > 0:
            for s in subcats:
                yield from self._api_category(fetcher, s, depth - 1, log, visited)

    def _api_all(self, fetcher):
        for p in self._api_pages(fetcher, action="query", generator="allpages", gapnamespace="0",
                                 gapfilterredir="nonredirects", gaplimit="500", prop="info"):
            yield self._item(p["title"], "rev:%s" % p.get("lastrevid"))

    # ---- fetching one page
    def fetch(self, fetcher, item, offline=False):
        if not offline and self.use_api(fetcher):
            data = self._api(fetcher, action="parse", page=item.title, prop="text|revid|categories|displaytitle",
                             redirects="1", disableeditsection="1")
            err = data.get("error") or {}
            if err.get("code") in ("missingtitle", "invalidtitle"):
                return GONE
            if err:
                raise RuntimeError("%s: %s" % (item.title, err.get("info") or err.get("code")))
            p = data["parse"]
            html = p["text"] if isinstance(p["text"], str) else p["text"].get("*", "")
            meta = {"revid": p.get("revid"), "categories": [c.get("category", "").replace("_", " ")
                                                            for c in p.get("categories", [])]}
            title = p.get("title") or item.title
            token = "rev:%s" % p.get("revid")
        else:
            r = fetcher.get(item.url, offline=offline)
            if r.status in (404, 410):
                return GONE
            if r.status != 200:
                raise RuntimeError("HTTP %s" % r.status)
            html = r.text
            meta = textify.wiki_meta(html)
            title = meta.get("title") or meta.get("page", "").replace("_", " ") or item.title
            lm = (self._lastmods or {}).get(item.url)
            token = item.token or ("lastmod:" + lm if lm else None)
            if r.headers.get("last-modified"):
                meta["last_modified"] = r.headers["last-modified"]
        edition = self.config.get("edition_filter")
        sections, data = textify.wiki_sections(html, skip=self.skip_sections, edition=edition)
        url = meta.pop("canonical", None) or self.url_of(title)
        meta["edition"] = self.edition
        meta.pop("page", None)
        since = textify.wiki_since(html)
        if since:
            meta["since_java"] = since
        meta["links"] = [t for t in textify.wiki_links(html, self.article_path) if self.wanted(t)][:400]
        aliases = [a for a in textify.wiki_aliases(html) if a != title.lower()]
        if aliases:
            meta["aliases"] = aliases
        lead = sections[0]["text"] if sections and sections[0]["path"] != "Facts" else (
            sections[1]["text"] if len(sections) > 1 else "")
        meta["status"] = textify.wiki_status(meta, title, lead, self.config.get("game_version"), edition)
        if self.config.get("game_version"):
            meta["game_version"] = self.config["game_version"]
        return Document(title, title, url, sections, data, meta, token)

    def skip_status(self):
        """Pages not worth keeping at all (April Fools, spin-off games), by their status."""
        return set(self.config.get("skip_status", ("joke", "spin-off", "meta")))


# ---------------------------------------------------------------- any website

class WebSource(Source):
    """config: urls [..], sitemap "https://site/sitemap.xml", allow ["https://site/guides/"] (URL
    prefixes to keep from the sitemap), deny [regex], license, license_url, attribution."""
    kind = "web"

    def params(self, opts):
        return {"pages": opts["pages"]} if opts.get("pages") else {}

    def _keep(self, url):
        allow = self.config.get("allow") or []
        if allow and not any(url.startswith(a) for a in allow):
            return False
        return not any(re.search(d, url) for d in self.config.get("deny") or [])

    def discover(self, fetcher, opts, log):
        seen = set()
        urls = list(opts.get("pages") or []) or list(self.config.get("urls") or [])
        for u in urls:
            if u not in seen:
                seen.add(u)
                yield Item(u, "", u, None)
        if not opts.get("pages") and self.config.get("sitemap"):
            for u, lm in read_sitemap(fetcher, self.config["sitemap"], log, offline=opts.get("offline")).items():
                if u not in seen and self._keep(u):
                    seen.add(u)
                    yield Item(u, "", u, "lastmod:" + lm if lm else None)

    def fetch(self, fetcher, item, offline=False):
        r = fetcher.get(item.url, offline=offline)
        if r.status in (404, 410):
            return GONE
        if r.status != 200:
            raise RuntimeError("HTTP %s" % r.status)
        ctype = r.headers.get("content-type", "text/html")
        if "html" in ctype:
            title, sections = textify.web_sections(r.text)
        elif ctype.startswith("text/"):
            title, sections = textify.markdown_sections(r.text)
        else:
            raise RuntimeError("not a text page (%s)" % ctype)
        meta = {k: r.headers[k] for k in ("etag", "last-modified") if k in r.headers}
        return Document(item.key, title or item.url, r.url or item.url, sections, {}, meta, item.token)


# ---------------------------------------------------------------- the player's own files

class LocalSource(Source):
    """Markdown and text files in a folder: a player's own build guides, farm designs, notes."""
    kind = "local"
    EXTS = (".md", ".markdown", ".txt")

    def folder(self):
        return os.path.expanduser(self.config.get("path") or "")

    def discover(self, fetcher, opts, log):
        root = self.folder()
        if not os.path.isdir(root):
            os.makedirs(root, exist_ok=True)
            log("  created %s: put .md or .txt files there (your build guides, notes)" % root)
            return
        for d, dirs, files in os.walk(root):
            dirs[:] = sorted(x for x in dirs if not x.startswith("."))
            for f in sorted(files):
                if f.lower().endswith(self.EXTS) and not f.startswith("."):
                    p = os.path.join(d, f)
                    st = os.stat(p)
                    rel = os.path.relpath(p, root)
                    yield Item(rel, os.path.splitext(f)[0], "file://" + urllib.parse.quote(p),
                               "mtime:%d:%d" % (st.st_mtime_ns, st.st_size))

    def fetch(self, fetcher, item, offline=False):
        p = os.path.join(self.folder(), item.key)
        if not os.path.exists(p):
            return GONE
        with open(p, encoding="utf-8", errors="replace") as f:
            text = f.read()
        fallback = os.path.splitext(os.path.basename(p))[0].replace("_", " ").replace("-", " ")
        title, sections = textify.markdown_sections(text, fallback_title=fallback)
        st = os.stat(p)
        return Document(item.key, title, item.url, sections, {}, {"path": p},
                        "mtime:%d:%d" % (st.st_mtime_ns, st.st_size))


# ---------------------------------------------------------------- minecraft-data (exact game data)

class MinecraftDataSource(Source):
    """PrismarineJS/minecraft-data: the game's own numbers for one version (Java 1.21.1 by default),
    as JSON: every crafting recipe, food values, what tool a block needs and what it drops. Six
    small files (~1.3 MB, six requests); each item becomes a short page, "Piston (Java 1.21.1 data)",
    whose recipe reads like the wiki's ("[Crafting recipe for 1 Piston: top row: ...]").
    The wiki says how and why; this says exactly what, for the player's version."""
    kind = "minecraft-data"
    FILES = ("items", "recipes", "blocks", "foods")
    TIERS = ("wooden", "stone", "golden", "iron", "diamond", "netherite")

    def __init__(self, name, config):
        super().__init__(name, config)
        self.base = config.get("base", "https://raw.githubusercontent.com/PrismarineJS/minecraft-data/master/data")
        self.version = config.get("version", "1.21.1")
        self._data = None

    def _load(self, fetcher, log, offline=False):
        if self._data is not None:
            return self._data
        r = fetcher.get(self.base + "/dataPaths.json", offline=offline)
        if r.status != 200:
            raise RuntimeError("dataPaths.json: HTTP %s" % r.status)
        paths = r.json()["pc"].get(self.version)
        if not paths:
            raise RuntimeError("minecraft-data has no Java %s" % self.version)
        data, tokens = {}, []
        for f in self.FILES:
            url = "%s/%s/%s.json" % (self.base, paths.get(f, "pc/" + self.version), f)
            r = fetcher.get(url, offline=offline)
            if r.status != 200:
                raise RuntimeError("%s: HTTP %s" % (url, r.status))
            data[f] = r.json()
            tokens.append(hashlib.sha1(r.body).hexdigest()[:8])
        data["token"] = "mcdata:%s:%s" % (self.version, "".join(tokens))
        self._data = data
        return data

    def _pages(self, d):
        items = {i["id"]: i for i in d["items"]}
        name = lambda i: items[i]["displayName"] if i in items else "?"
        recipes = {int(k): v for k, v in d["recipes"].items()}
        used_in = {}
        for out, rs in recipes.items():
            for rec in rs:
                for i in set(_ingredient_ids(rec)):
                    used_in.setdefault(i, set()).add(out)
        foods = {f["id"]: f for f in d["foods"]}
        blocks = {b["name"]: b for b in d["blocks"]}
        pages = {}
        for iid, it in items.items():
            sections = []
            rs = recipes.get(iid) or []
            texts, recs = [], []
            for group in _group_recipes(rs):
                text, rec = _recipe_text(group, name, it["displayName"])
                if text:
                    texts.append(text)
                    recs.append(rec)
            if texts:
                sections.append({"path": "Crafting", "text": "\n".join(texts), "data": {"recipes": recs}})
            f = foods.get(iid)
            if f:
                sections.append({"path": "Food", "text": "%s restores %s hunger (%s drumsticks) and %s saturation." % (
                    it["displayName"], _num(f["foodPoints"]), _num(f["foodPoints"] / 2), _num(f["saturation"]))})
            b = blocks.get(it["name"])
            if b and b.get("diggable"):
                tools = [name(int(t)) for t in (b.get("harvestTools") or {})]
                line = "%s: hardness %s." % (it["displayName"], _num(b.get("hardness")))
                if tools:
                    tier = min((t for t in tools if "Pickaxe" in t), default=None,
                               key=lambda t: next((n for n, x in enumerate(self.TIERS) if t.lower().startswith(x)), 9))
                    line += (" It needs at least %s %s to drop anything." % ("an" if tier[0] in "AEIOU" else "a", tier)
                             ) if tier else \
                        (" It needs a %s to drop anything." % " or ".join(tools[:3]))
                drops = [name(x) for x in (b.get("drops") or [])]
                if drops and drops != [it["displayName"]]:
                    line += " Mined, it drops %s." % ", ".join(dict.fromkeys(drops))
                sections.append({"path": "Mining", "text": line})
            uses = sorted({name(o) for o in used_in.get(iid, ())})
            if uses:
                sections.append({"path": "Used to make", "text": "%s is used to make: %s." % (
                    it["displayName"], ", ".join(uses[:40]) + (", and more" if len(uses) > 40 else ""))})
            if not sections:
                continue
            sections.append({"path": "Facts", "text": "%s stacks up to %d. (Java Edition %s)" % (
                it["displayName"], it.get("stackSize", 64), self.version)})
            pages[it["name"]] = (it["displayName"], sections)
        return pages

    def url_of(self, key):
        return "https://github.com/PrismarineJS/minecraft-data/tree/master/data/pc/%s#%s" % (self.version, key)

    def discover(self, fetcher, opts, log):
        d = self._load(fetcher, log, offline=opts.get("offline"))
        self._built = self._pages(d)
        for key, (title, _) in sorted(self._built.items()):
            yield Item(key, "%s (Java %s data)" % (title, self.version), self.url_of(key), d["token"])

    def fetch(self, fetcher, item, offline=False):
        d = self._load(fetcher, print, offline=offline)
        built = getattr(self, "_built", None) or self._pages(d)
        self._built = built
        if item.key not in built:
            return GONE
        title, sections = built[item.key]
        recipes = [r for s in sections for r in ((s.get("data") or {}).get("recipes") or [])]
        return Document(item.key, "%s (Java %s data)" % (title, self.version), self.url_of(item.key), sections,
                        {"recipes": recipes} if recipes else {}, {"status": "current", "game_version": self.version},
                        d["token"])


def _num(x):
    return ("%.1f" % x).rstrip("0").rstrip(".") if isinstance(x, float) else str(x)


def _ingredient_ids(rec):
    if rec.get("inShape"):
        return [i for row in rec["inShape"] for i in row if i is not None]
    return [i for i in rec.get("ingredients") or [] if i is not None]


def _group_recipes(rs):
    """Recipes that differ only by which wood (or wool...) goes where -> one group."""
    groups = {}
    for rec in rs:
        shape = rec.get("inShape")
        if shape:
            sig = ("shaped", tuple(tuple(i is None for i in row) for row in shape), rec["result"]["count"])
        else:
            sig = ("shapeless", len(rec.get("ingredients") or []), rec["result"]["count"])
        groups.setdefault(sig, []).append(rec)
    return list(groups.values())


def _any(names):
    names = list(dict.fromkeys(names))
    if len(names) == 1:
        return names[0]
    words = [n.split() for n in names]
    tail = []
    while all(len(w) > len(tail) for w in words) and len({tuple(w[len(w) - len(tail) - 1:]) for w in words}) == 1:
        tail = words[0][len(words[0]) - len(tail) - 1:]
    return "any " + " ".join(tail) if tail else "any of " + ", ".join(names[:4]) + (", ..." if len(names) > 4 else "")


def _recipe_text(group, name, output):
    first = group[0]
    count = first["result"]["count"]
    makes = "%d %s" % (count, output)
    if first.get("inShape"):
        rows = []
        for r, row in enumerate(first["inShape"]):
            rows.append([_any([name(g["inShape"][r][c]) for g in group]) if x is not None else ""
                         for c, x in enumerate(row)])
        have = {}
        for row in rows:
            for n in row:
                if n:
                    have[n] = have.get(n, 0) + 1
        label = {1: ["in one row"], 2: ["top row", "bottom row"], 3: ["top row", "middle row", "bottom row"]}.get(
            len(rows), ["row %d" % (i + 1) for i in range(len(rows))])
        grid = "; ".join("%s: %s" % (label[i], ", ".join(x or "empty" for x in r)) for i, r in enumerate(rows))
        text = "[Crafting recipe for %s: %s. Uses %s.]" % (makes, grid, ", ".join("%d %s" % (n, k) for k, n in have.items()))
        rec = {"station": "crafting", "grid": rows, "output": output, "count": count, "shapeless": False,
               "ingredients": have}
    else:
        n_ing = len(first.get("ingredients") or [])
        names = [_any([name(g["ingredients"][i]) for g in group if len(g.get("ingredients") or []) > i])
                 for i in range(n_ing)]
        have = {}
        for n in names:
            have[n] = have.get(n, 0) + 1
        text = "[Crafting recipe (shapeless): %s -> %s]" % (", ".join("%d %s" % (n, k) for k, n in have.items()), makes)
        rec = {"station": "crafting", "grid": [], "output": output, "count": count, "shapeless": True,
               "ingredients": have}
    return text, rec


KINDS = {"mediawiki": MediaWikiSource, "web": WebSource, "local": LocalSource, "minecraft-data": MinecraftDataSource}

# what a survival player asks about most: the starting set of `kb.py crawl minecraft-wiki --core`, which
# then grows along the links these pages share (crawler.linked_titles)
CORE_PAGES = [
    "Crafting Table", "Crafting", "Furnace", "Blast Furnace", "Smoker", "Smelting", "Chest", "Barrel",
    "Ender Chest", "Shulker Box", "Bed", "Torch", "Lantern", "Campfire", "Ladder", "Door", "Trapdoor", "Fence",
    "Fence Gate", "Glass", "Stone", "Cobblestone", "Deepslate", "Dirt", "Sand", "Gravel", "Clay", "Obsidian",
    "Crying Obsidian", "Wood", "Log", "Planks", "Stick", "Coal", "Charcoal", "Iron Ingot", "Iron Ore", "Raw Iron",
    "Gold Ingot", "Gold Ore", "Copper Ingot", "Copper Ore", "Diamond", "Diamond Ore", "Emerald", "Emerald Ore",
    "Lapis Lazuli", "Lapis Lazuli Ore", "Redstone Ore", "Nether Quartz", "Ancient Debris", "Netherite Ingot",
    "Netherite Scrap", "Amethyst Shard", "Ore", "Altitude", "Pickaxe", "Axe", "Shovel", "Hoe", "Sword", "Bow",
    "Crossbow", "Arrow", "Trident", "Mace", "Shield", "Armor", "Helmet", "Chestplate", "Leggings", "Boots",
    "Turtle Shell", "Elytra", "Firework Rocket", "Totem of Undying", "Fishing Rod", "Shears", "Flint and Steel",
    "Bucket", "Water Bucket", "Lava Bucket", "Milk Bucket", "Lead", "Name Tag", "Saddle", "Compass",
    "Recovery Compass", "Lodestone", "Clock", "Map", "Spyglass", "Bundle", "Brush", "Smithing Table",
    "Smithing Template", "Netherite Upgrade", "Smithing", "Anvil", "Grindstone", "Enchanting Table",
    "Enchanting table mechanics", "Enchantment", "Enchanted Book", "Bookshelf", "Experience", "Mending",
    "Unbreaking", "Efficiency", "Fortune", "Silk Touch", "Looting", "Sharpness", "Protection", "Feather Falling",
    "Brewing", "Brewing Stand", "Potion", "Splash Potion", "Blaze Powder", "Nether Wart", "Fermented Spider Eye",
    "Glowstone Dust", "Potion of Night Vision", "Potion of Fire Resistance", "Potion of Healing",
    "Potion of Strength", "Potion of Swiftness", "Potion of Water Breathing", "Potion of Invisibility",
    "Potion of Regeneration", "Potion of Slow Falling", "Food", "Hunger (effect)", "Bread", "Steak",
    "Golden Carrot", "Golden Apple", "Enchanted Golden Apple", "Wheat", "Wheat Seeds", "Carrot", "Potato",
    "Beetroot", "Pumpkin", "Melon", "Sugar Cane", "Bamboo", "Cactus", "Cocoa Beans", "Sweet Berries", "Kelp",
    "Bone Meal", "Composter", "Farmland", "Sapling", "Tree", "Redstone Dust", "Redstone Torch",
    "Redstone Repeater", "Redstone Comparator", "Redstone circuits", "Redstone circuits/Clock", "Piston",
    "Sticky Piston", "Observer", "Hopper", "Dropper", "Dispenser", "Lever", "Button", "Pressure Plate",
    "Tripwire Hook", "Daylight Detector", "Target", "Note Block", "Rail", "Powered Rail", "Minecart", "Crafter",
    "Copper Bulb", "Trading", "Villager", "Zombie Villager", "Wandering Trader", "Iron Golem", "Village", "Raid",
    "Bad Omen", "Pillager Outpost", "Mob", "Spawn", "Light", "Zombie", "Skeleton", "Creeper", "Spider", "Enderman",
    "Witch", "Slime", "Phantom", "Drowned", "Pillager", "Evoker", "Ravager", "Blaze", "Ghast", "Piglin",
    "Wither Skeleton", "Wither", "Ender Dragon", "Warden", "Breeze", "Wolf", "Cat", "Horse", "Donkey", "Llama",
    "Parrot", "Axolotl", "Bee", "Fox", "Allay", "Sniffer", "Armadillo", "Camel", "Cow", "Sheep", "Pig", "Chicken",
    "Breeding", "Taming", "Overworld", "The Nether", "The End", "Nether Portal", "End portal", "Eye of Ender",
    "Stronghold", "Nether Fortress", "Bastion Remnant", "End City", "Ocean Monument", "Woodland Mansion",
    "Ancient City", "Trial Chambers", "Trial Spawner", "Vault", "Ominous Vault", "Trial Key", "Ominous Trial Key",
    "Wind Charge", "Heavy Core", "Mineshaft", "Dungeon", "Desert Pyramid", "Jungle Pyramid", "Shipwreck",
    "Buried Treasure", "Ruined Portal", "Trail Ruins", "Biome", "Plains", "Forest", "Desert", "Taiga", "Jungle",
    "Swamp", "Mushroom Fields", "Deep Dark", "Lush Caves", "Health", "Damage", "Death", "Daylight cycle",
    "Weather", "Difficulty", "Effect", "Beacon", "Conduit", "Respawn Anchor", "Bartering", "Fishing",
    "Tutorial:Beginner's guide", "Tutorial:Mining", "Tutorial:Mining/Diamonds", "Tutorial:Mining/Ancient debris",
    "Tutorial:Ore guide", "Tutorial:Crop farming", "Tutorial:Sugar cane farming", "Tutorial:Tree farming",
    "Tutorial:Pumpkin and melon farming", "Tutorial:Animal farming", "Tutorial:Mob farm", "Tutorial:Mob grinder",
    "Tutorial:Experience farming", "Tutorial:Iron golem farming", "Tutorial:Creeper farming",
    "Tutorial:Villager farming", "Tutorial:Villager trading hall", "Tutorial:Trading",
    "Tutorial:Curing a zombie villager", "Tutorial:Best enchantments guide", "Tutorial:Automatic smelting",
    "Tutorial:Hopper", "Tutorial:Redstone", "Tutorial:Redstone tips", "Tutorial:Secret door",
    "Tutorial:Automatic double doors", "Tutorial:Piston uses/2×3 piston door", "Tutorial:Hourly clock",
    "Tutorial:Nether portals", "Tutorial:Nether survival", "Tutorial:Nether hub",
    "Tutorial:Exploring a Nether fortress", "Tutorial:Defeating the ender dragon", "Tutorial:Defeating the wither",
    "Tutorial:Defeating a village raid", "Tutorial:Defeating trial chambers",
    "Tutorial:Exploring the deep dark and ancient city", "Tutorial:Exploring an End city",
    "Tutorial:Conquering an ocean monument", "Tutorial:Combat", "Tutorial:Defense", "Tutorial:Hunger management",
    "Tutorial:Gathering food", "Tutorial:Horses", "Tutorial:Shelters", "Tutorial:Shelter types",
    "Tutorial:Fish farming", "Tutorial:Wool farming", "Tutorial:Bamboo farming", "Tutorial:Cactus farming",
    "Tutorial:Honey farming", "Tutorial:Raid farming", "Tutorial:Guardian farming", "Tutorial:Blaze farming",
    "Tutorial:Enderman farming", "Tutorial:Slime farming", "Tutorial:Potion farming"
]


MINECRAFT_WIKI = {
    "kind": "mediawiki",
    "title": "Minecraft Wiki",
    "base": "https://minecraft.wiki",
    "license": "CC BY-NC-SA 3.0",
    "license_url": "https://creativecommons.org/licenses/by-nc-sa/3.0/",
    "attribution": "Minecraft Wiki contributors (minecraft.wiki)",
    "terms": "https://meta.weirdgloop.org/w/Meta:Copyrights",
    "edition": "Java Edition (what the wiki marks as Bedrock-only or upcoming is left out)",
    # the player's game: Kindred Spirit runs on Java 1.21.1. Facts marked for another edition or
    # as upcoming are left out; pages added in a later version are kept but marked "future"
    "edition_filter": "java",
    "game_version": "1.21.1",
    # articles (namespace 0) and tutorials (namespace 10010: farms, redstone builds, mechanisms)
    "sitemaps": ["/images/sitemaps/NS_0-0.xml.gz", "/images/sitemaps/NS_10010-0.xml.gz"],
    "namespaces": ["", "Tutorial"],
    # version-history pages, renders and data pages: lots of text, little use to a companion
    "skip_titles": [r"^(Java|Bedrock|Pocket|Legacy Console|Education|Pi|New Nintendo 3DS|Xbox|PlayStation|Wii U|"
                    r"Switch|Console|Minecraft Education)( Edition)? [0-9]", r"^[0-9]+(\.[0-9]+)+",
                    # editions and their versions, betas, patches, previews and file formats
                    r"^(Java|Bedrock|Pocket|Legacy Console|Education|Pi|New Nintendo 3DS|Xbox( 360| One)?|"
                    r"PlayStation( 3| 4| Vita)?|Wii U|(Nintendo )?Switch|Console|Minecraft Education|Minecraft: Pi) Edition\b",
                    r"^(Minecraft Education|Minecraft Earth|Minecraft Dungeons|Minecraft Legends|Minecraft Story Mode|"
                    r"Minecraft: Story Mode|Lego Minecraft|A Minecraft Movie|Minecraft Live|Minecraft\.net|Minecraft)$",
                    r"(?i)\b(version history|data values|level format|item format|entity format|chunk format|"
                    r"(block|item|entity|entity type|fluid|biome|damage type) tags?)\b", r"^Commands(/|$)",
                    r"^Planned versions$", r"(?i)^lego minecraft$", r"\bDrop \d{4}$",
                    r"^[0-9.]+[a-z]?$", r"^Tutorials$", r"/(Renders|Structure|DV|BS|ED|Data|Asset history|Gallery)\b",
                    r"^(Tutorial:)?(Programs and editors|Mods)\b", r"\(disambiguation\)",
                    # how to run, mod, script or host the game: nothing a companion in the world needs
                    r"^Tutorial:(Creating (a data pack|a resource pack|Forge mods|a challenge map)|Custom (texture packs|"
                    r"world generation|Minecraft directory|structures|maps)|Command|Adding (custom|a new dimension|"
                    r"packs|profiles)|Hamachi|Hide multiplayer|Create a Mac|FreeBSD|Saved data|Importing and exporting|"
                    r"Downgrading|Changing item default|Bedrock Edition development|Setting up a|Running|Updating|"
                    r"Installing|Crossplay|Bedwars|Civilization SMP|Beating a (CTM|challenge) map|Craftmine|"
                    r"Version overviews|Achievement guide/)", r"\b([Ss]tartup|[Ss]erver|[Ll]auncher|daemon|Xbox|PlayStation)\b",
                    # one circuit design among dozens ("Redstone circuits/Memory/TFF Z3"); the overviews stay
                    r"^Redstone circuits/[^/]+/"],
    "default_categories": ["Mobs", "Biomes", "Tutorials", "Redstone", "Food", "Plants", "Enchantments", "Ores",
                           "Structures", "Utility blocks", "Mechanisms", "Tools", "Weapons", "Armor",
                           "Gameplay"],
    "depth": 1,
    "core_pages": CORE_PAGES,
}


MINECRAFT_DATA = {
    "kind": "minecraft-data",
    "title": "minecraft-data (Java 1.21.1 recipes, foods, mining)",
    "version": "1.21.1",
    "license": "MIT (PrismarineJS/minecraft-data); the game data in it is Mojang's",
    "license_url": "https://github.com/PrismarineJS/minecraft-data/blob/master/LICENSE",
    "attribution": "PrismarineJS minecraft-data contributors",
    "terms": "https://github.com/PrismarineJS/minecraft-data#readme",
    "edition": "Java Edition 1.21.1",
}


def knowledge_dir():
    d = os.environ.get("KINDRED_KNOWLEDGE")
    if d:
        return os.path.expanduser(d)
    home = os.environ.get("KINDRED_HOME") or os.path.join(os.path.expanduser("~"), ".kindred-spirit")
    return os.path.join(home, "knowledge")


def builtin_sources(kdir=None):
    kdir = kdir or knowledge_dir()
    return {
        "minecraft-wiki": MINECRAFT_WIKI,
        "local": {"kind": "local", "title": "Your own notes and build guides", "path": os.path.join(kdir, "local"),
                  "license": "yours (local files, never shared)", "attribution": "your notes"},
        "minecraft-data": MINECRAFT_DATA,
    }


def sources_file(kdir=None):
    return os.path.join(kdir or knowledge_dir(), "sources.json")


def load_configs(kdir=None):
    configs = builtin_sources(kdir)
    p = sources_file(kdir)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for name, cfg in (json.load(f) or {}).items():
                configs[name] = dict(configs.get(name, {}), **cfg)
    return configs


def save_config(name, cfg, kdir=None):
    p = sources_file(kdir)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    cur = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            cur = json.load(f) or {}
    cur[name] = cfg
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2)
    os.replace(p + ".tmp", p)


def make(name, configs=None):
    configs = configs if configs is not None else load_configs()
    if name not in configs:
        raise KeyError("no source called %r (kb.py sources lists them)" % name)
    cfg = configs[name]
    kind = KINDS.get(cfg.get("kind"))
    if not kind:
        raise KeyError("source %r has an unknown kind %r" % (name, cfg.get("kind")))
    return kind(name, cfg)
