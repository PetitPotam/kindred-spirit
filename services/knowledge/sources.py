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
        sections, data = textify.wiki_sections(html, skip=self.skip_sections)
        url = meta.pop("canonical", None) or self.url_of(title)
        meta["edition"] = self.edition
        meta.pop("page", None)
        return Document(title, title, url, sections, data, meta, token)


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


KINDS = {"mediawiki": MediaWikiSource, "web": WebSource, "local": LocalSource}

MINECRAFT_WIKI = {
    "kind": "mediawiki",
    "title": "Minecraft Wiki",
    "base": "https://minecraft.wiki",
    "license": "CC BY-NC-SA 3.0",
    "license_url": "https://creativecommons.org/licenses/by-nc-sa/3.0/",
    "attribution": "Minecraft Wiki contributors (minecraft.wiki)",
    "terms": "https://meta.weirdgloop.org/w/Meta:Copyrights",
    "edition": "Java and Bedrock, latest versions (the wiki marks what differs between editions and versions)",
    # articles (namespace 0) and tutorials (namespace 10010: farms, redstone builds, mechanisms)
    "sitemaps": ["/images/sitemaps/NS_0-0.xml.gz", "/images/sitemaps/NS_10010-0.xml.gz"],
    "namespaces": ["", "Tutorial"],
    # version-history pages, renders and data pages: lots of text, little use to a companion
    "skip_titles": [r"^(Java|Bedrock|Pocket|Legacy Console|Education|Pi|New Nintendo 3DS|Xbox|PlayStation|Wii U|"
                    r"Switch|Console|Minecraft Education)( Edition)? [0-9]", r"^[0-9]+(\.[0-9]+)+",
                    r"^[0-9.]+[a-z]?$", r"/(Renders|Structure|DV|BS|ED|Data|Asset history|Gallery)\b",
                    r"^(Tutorial:)?(Programs and editors|Mods)\b", r"\(disambiguation\)"],
    "default_categories": ["Mobs", "Biomes", "Tutorials", "Redstone", "Food", "Plants", "Enchantments", "Ores",
                           "Structures", "Utility blocks", "Mechanisms", "Tools", "Weapons", "Armor",
                           "Gameplay"],
    "depth": 1,
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
