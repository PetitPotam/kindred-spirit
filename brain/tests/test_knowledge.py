"""The knowledge base (services/knowledge): robots.txt, politeness, wiki parsing, chunking,
incremental refresh, resuming, search ranking, the gateway route.

No network: every response below is recorded by hand. The pages imitate the *markup* of
minecraft.wiki (infobox, crafting grid, headings, navboxes) with our own made-up text, so no
wiki content (CC BY-NC-SA) is copied into this repository.
"""
import gzip
import json
import os
import tempfile

import gateway_stub  # noqa: F401  (puts services/ on the path)
from knowledge import api, crawler, sources, textify
from knowledge.fetcher import Blocked, Fetcher
from knowledge.robots import Robots
from knowledge.store import KnowledgeStore

WIKI = "https://wiki.example"

ROBOTS_LIKE_MINECRAFT_WIKI = """
User-Agent: *
Disallow: /w/Special:
Disallow: /*api.php
Disallow: /*?action=
Disallow: /*?*&action=
Disallow: /*?pagefrom=

User-agent: ClaudeBot
Disallow: /
"""


# ---------------------------------------------------------------- a recorded little web

class FakeWeb:
    """transport(method, url, headers, timeout) answering from a dict; records every request."""

    def __init__(self, routes):
        self.routes = routes
        self.log = []

    def __call__(self, method, url, headers, timeout):
        self.log.append((url, dict(headers)))
        r = self.routes.get(url)
        if callable(r):
            r = r(headers)
        if r is None:
            return 404, {"Content-Type": "text/html"}, b"not found"
        status, hdrs, body = r
        return status, hdrs, body.encode("utf-8") if isinstance(body, str) else body

    def urls(self):
        return [u for u, _ in self.log]


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(round(s, 3))
        self.t += s


def fetcher(web, delay=1.0, cache=True):
    clock = Clock()
    f = Fetcher(cache_dir=os.path.join(tempfile.mkdtemp(), "cache") if cache else None, delay=delay, transport=web,
                clock=clock, sleep=clock.sleep)
    f.test_clock = clock
    return f


def html(status=200, body="", last_modified=None, etag=None):
    h = {"Content-Type": "text/html; charset=UTF-8"}
    if last_modified:
        h["Last-Modified"] = last_modified
    if etag:
        h["ETag"] = etag
    return status, h, body


def grid(rows, output, count=None):
    def slot(names):
        if not names:
            return '<span class="invslot"></span>'
        items = "".join('<span class="invslot-item invslot-item-image"><a href="/w/%s" title="%s"><img alt="x"/></a>'
                        '</span>' % (n.replace(" ", "_"), n) for n in names)
        return '<span class="invslot%s">%s</span>' % (" animated" if len(names) > 1 else "", items)
    rows_html = "".join('<span class="mcui-row">%s</span>' % "".join(slot(s) for s in r) for r in rows)
    stack = '<span class="invslot-stacksize">%d</span>' % count if count else ""
    out = ('<span class="invslot"><span class="invslot-item invslot-item-image"><a href="/w/%s" title="%s"></a>%s</span>'
           '</span>' % (output, output, stack))
    return ('<span class="mcui mcui-Crafting&#95;Table pixel-image"><span class="mcui-input">%s</span>'
            '<span class="mcui-arrow"><br/></span><span class="mcui-output">%s</span></span>' % (rows_html, out))


def wiki_page(title, revid, body, categories=("Blocks",)):
    return """<!DOCTYPE html><html><head><title>%(t)s - Example Wiki</title>
<link rel="canonical" href="%(w)s/w/%(u)s"/>
<script>RLCONF={"wgPageName":"%(u)s","wgRevisionId":%(r)d,"wgCategories":%(c)s};</script></head>
<body><div id="mw-navigation">Main page Random page Recent changes</div>
<h1 id="firstHeading" class="firstHeading"><span class="mw-page-title-main">%(t)s</span></h1>
<div class="mw-indicators"><div class="mw-parser-output"><a href="/w/Featured" title="A featured article">*</a></div></div>
<div id="mw-content-text"><div class="mw-parser-output">%(b)s
<div class="navbox"><a href="/w/Other">Every block in the game</a></div></div></div>
<div id="catlinks" class="catlinks">Categories: Blocks</div></body></html>""" % {
        "t": title, "u": title.replace(" ", "_"), "r": revid, "c": json.dumps(list(categories)), "b": body, "w": WIKI}


def heading(level, text):
    return ('<div class="mw-heading mw-heading%d"><h%d id="%s">%s</h%d><span class="mw-editsection">[edit]</span>'
            '</div>' % (level, level, text.replace(" ", "_"), text, level))


GLOW_LAMP = wiki_page("Glow Lamp", 501, (
    '<div class="hatnote">For the decorative block, see Fancy Lamp.</div>'
    '<div class="infobox notaninfobox"><div class="mcwiki-header infobox-title">Glow Lamp</div>'
    '<div class="infobox-imagearea"><img alt="lamp"/></div><table class="infobox-rows"><tbody>'
    '<tr><th>Renewable</th><td><p>Yes</p></td></tr><tr><th>Stackable</th><td><p>Yes (64)</p></td></tr>'
    '<tr><th>Light level</th><td><p>13</p></td></tr></tbody></table></div>'
    '<p>A <b>glow lamp</b> is a made-up light block used only in these tests.<sup class="reference">[1]</sup></p>'
    + heading(2, "Obtaining") + heading(3, "Crafting")
    + '<table class="wikitable"><tbody><tr><th>Ingredients</th><th>Crafting recipe</th></tr><tr><td>Any Planks&#160;+<br/>'
      'Torch</td><td>' + grid([[["Oak Planks", "Birch Planks"], ["Torch"], ["Oak Planks", "Birch Planks"]],
                               [[], [], []], [[], [], []]], "Glow Lamp", 2) + '</td></tr></tbody></table>'
    + heading(2, "Usage")
    + '<p>Place it on any solid block. It gives off light and melts snow nearby.</p>'
    + '<ul><li>It can be waterlogged.</li><li>It can hang from a chain.</li></ul>'
    + heading(2, "History") + '<p>Added in a long forgotten snapshot with a different texture.</p>'
    + heading(3, "Java Edition") + '<p>Old details nobody needs.</p>'
    + heading(2, "Gallery") + '<ul class="gallery"><li>picture</li></ul>'
    + heading(2, "Trivia") + '<p>A trivia line.</p>'))

ZOMBOID = wiki_page("Zomboid", 777, (
    '<div class="infobox"><div class="infobox-title">Zomboid</div><table class="infobox-rows">'
    '<tr><th>Health points</th><td>20HP × 10</td></tr><tr><th>Behavior</th><td>Hostile</td></tr></table></div>'
    '<p>A zomboid is an imaginary undead mob that shuffles around at night.</p>'
    + heading(2, "Spawning") + '<p>Zomboids spawn in darkness at light level 0 on solid blocks.</p>'
    + heading(2, "Behavior") + '<p>Zomboids chase villagers and the player. A zomboid that walks into water slowly '
    'turns into a soggy zomboid and keeps chasing with full health.</p>'
    + heading(2, "Drops") + '<p>Zomboids drop rotten scraps when killed.</p>'), categories=("Mobs",))

LAMP_FARM = wiki_page("Tutorial:Lamp farm", 900, (
    '<p>This tutorial explains how to build an automatic glow lamp farm.</p>'
    + heading(2, "Design") + '<p>Build a 5x5 platform, put hoppers under it and run water across the top.</p>'
    + heading(2, "Steps") + '<ol><li>Dig a 5x5 hole.</li><li>Place hoppers into a chest.</li></ol>'),
    categories=("Tutorials",))

CATEGORY_BLOCKS = """<html><body><div id="mw-subcategories"><a href="/w/Category:Light_sources"
 title="Category:Light sources">Light sources</a></div>
<div id="mw-pages"><a href="/w/Category:Blocks?pagefrom=Z" title="Category:Blocks">next page</a>
<div class="mw-category"><ul><li><a href="/w/Glow_Lamp" title="Glow Lamp">Glow Lamp</a></li>
<li><a href="/w/Java_Edition_1.2" title="Java Edition 1.2">Java Edition 1.2</a></li>
<li><a href="/w/User:Someone" title="User:Someone">User:Someone</a></li></ul></div></div></body></html>"""

CATEGORY_LIGHT = """<html><body><div id="mw-pages"><ul><li><a href="/w/Glow_Lamp" title="Glow Lamp">Glow Lamp</a></li>
<li><a href="/w/Tutorial:Lamp_farm" title="Tutorial:Lamp farm">Tutorial:Lamp farm</a></li></ul></div></body></html>"""


def sitemap(entries):
    body = '<?xml version="1.0"?><urlset>' + "".join(
        "<url><loc>%s/w/%s</loc><lastmod>%s</lastmod></url>" % (WIKI, t, lm) for t, lm in entries) + "</urlset>"
    return 200, {"Content-Type": "application/x-gzip"}, gzip.compress(body.encode())


def wiki_source(**extra):
    cfg = dict(sources.MINECRAFT_WIKI, base=WIKI, sitemaps=["/sitemap.xml.gz"], default_categories=["Blocks"],
               license="CC BY-NC-SA 3.0")
    cfg.update(extra)
    return sources.make("test-wiki", {"test-wiki": cfg})


def store(embed=None, model=""):
    return KnowledgeStore(os.path.join(tempfile.mkdtemp(), "k.db"), embed=embed, model_name=model)


def quiet(*a):
    pass


def wiki_routes(lamp_lastmod="2026-01-01T00:00:00Z"):
    return {
        WIKI + "/robots.txt": (200, {}, ROBOTS_LIKE_MINECRAFT_WIKI),
        WIKI + "/sitemap.xml.gz": sitemap([("Glow_Lamp", lamp_lastmod), ("Zomboid", "2026-01-02T00:00:00Z")]),
        WIKI + "/w/Category:Blocks": html(body=CATEGORY_BLOCKS),
        WIKI + "/w/Category:Light_sources": html(body=CATEGORY_LIGHT),
        WIKI + "/w/Glow_Lamp": html(body=GLOW_LAMP, last_modified="Thu, 01 Jan 2026 00:00:00 GMT"),
        WIKI + "/w/Zomboid": html(body=ZOMBOID),
        WIKI + "/w/Tutorial:Lamp_farm": lambda h: ((304, {}, "") if h.get("If-Modified-Since") else
                                                   html(body=LAMP_FARM, last_modified="Thu, 01 Jan 2026 00:00:00 GMT")),
    }


# ---------------------------------------------------------------- robots.txt

def test_robots_wildcards_like_minecraft_wiki():
    r = Robots(ROBOTS_LIKE_MINECRAFT_WIKI)
    agent = "KindredSpiritKnowledge"
    assert r.allowed("https://minecraft.wiki/w/Piston", agent)
    assert r.allowed("https://minecraft.wiki/w/Category:Mobs", agent)
    assert not r.allowed("https://minecraft.wiki/api.php?action=parse&page=Piston", agent)
    assert not r.allowed("https://minecraft.wiki/w/Piston?action=raw", agent)
    assert not r.allowed("https://minecraft.wiki/w/Piston?useskin=x&action=raw", agent)
    assert not r.allowed("https://minecraft.wiki/w/Special:Random", agent)
    assert not r.allowed("https://minecraft.wiki/w/Category:Blocks?pagefrom=Z", agent)
    assert not r.allowed("https://minecraft.wiki/w/Piston", "ClaudeBot/1.0"), "a named bot gets its own group"


def test_robots_longest_rule_wins_and_dollar_and_crawl_delay():
    r = Robots("User-agent: *\nDisallow: /guides/\nAllow: /guides/public/\nDisallow: /*.pdf$\nCrawl-delay: 5\n")
    assert not r.allowed("https://x.example/guides/secret", "bot")
    assert r.allowed("https://x.example/guides/public/house", "bot")
    assert not r.allowed("https://x.example/a/b.pdf", "bot")
    assert r.allowed("https://x.example/a/b.pdf?page=2", "bot")
    assert r.crawl_delay("bot") == 5
    assert Robots("").allowed("https://x.example/anything")


def test_fetcher_never_requests_what_robots_forbids():
    web = FakeWeb({WIKI + "/robots.txt": (200, {}, ROBOTS_LIKE_MINECRAFT_WIKI)})
    f = fetcher(web)
    try:
        f.get(WIKI + "/api.php?action=query")
        raise AssertionError("should have been blocked")
    except Blocked:
        pass
    assert web.urls() == [WIKI + "/robots.txt"]


def test_fetcher_refuses_a_redirect_into_a_forbidden_place():
    web = FakeWeb({WIKI + "/robots.txt": (200, {}, ROBOTS_LIKE_MINECRAFT_WIKI),
                   WIKI + "/go": (302, {"Location": "/w/Special:Secret"}, "")})
    try:
        fetcher(web).get(WIKI + "/go")
        raise AssertionError("should have been blocked")
    except Blocked:
        pass
    assert WIKI + "/w/Special:Secret" not in web.urls()


# ---------------------------------------------------------------- politeness: rate limit, retries, cache

def test_one_request_per_second_and_retry_after():
    calls = {"n": 0}

    def busy(headers):
        calls["n"] += 1
        return (429, {"Retry-After": "7"}, "") if calls["n"] == 1 else html(body="<p>ok</p>")
    web = FakeWeb({WIKI + "/robots.txt": (200, {}, ""), WIKI + "/a": html(body="<p>a</p>"), WIKI + "/b": busy})
    f = fetcher(web, delay=1.0)
    f.get(WIKI + "/a")
    f.get(WIKI + "/b")
    clock = f.test_clock
    assert 7 in clock.slept, "Retry-After is honoured"
    assert clock.slept.count(1.0) >= 2, "requests to one site are spaced by the delay"
    assert f.get(WIKI + "/b").text == "<p>ok</p>"


def test_crawl_delay_slower_than_ours_is_respected():
    web = FakeWeb({WIKI + "/robots.txt": (200, {}, "User-agent: *\nCrawl-delay: 4\n"), WIKI + "/a": html(body="a"),
                   WIKI + "/b": html(body="b")})
    f = fetcher(web, delay=1.0)
    f.get(WIKI + "/a")
    f.get(WIKI + "/b")
    assert 4.0 in f.test_clock.slept


def test_cache_and_conditional_requests():
    def page(headers):
        if headers.get("If-None-Match") == '"v1"':
            return 304, {}, ""
        return html(body="<p>hello</p>", etag='"v1"')
    web = FakeWeb({WIKI + "/robots.txt": (200, {}, ""), WIKI + "/p": page})
    f = fetcher(web)
    first = f.get(WIKI + "/p")
    again = f.get(WIKI + "/p")
    assert first.text == again.text == "<p>hello</p>"
    assert again.not_modified and f.not_modified == 1
    assert web.log[-1][1].get("If-None-Match") == '"v1"'
    n = len(web.log)
    assert f.get(WIKI + "/p", offline=True).text == "<p>hello</p>" and len(web.log) == n, "offline reads the cache"


def test_user_agent_is_generic():
    web = FakeWeb({WIKI + "/robots.txt": (200, {}, "")})
    fetcher(web).robots(WIKI + "/x")
    ua = web.log[0][1]["User-Agent"]
    assert ua.startswith("KindredSpiritKnowledge/") and "@" not in ua


# ---------------------------------------------------------------- parsing a wiki page

def test_parsing_a_wiki_page():
    secs, data = textify.wiki_sections(GLOW_LAMP)
    paths = [s["path"] for s in secs]
    assert paths[0] == "Facts" and "Light level: 13" in secs[0]["text"]
    assert data["infobox"]["fields"]["Stackable"] == "Yes (64)"
    assert "Summary" in paths and "Obtaining > Crafting" in paths and "Usage" in paths
    assert not any(p.startswith(("History", "Gallery", "Trivia")) for p in paths), "history and gallery are dropped"
    text = "\n".join(s["text"] for s in secs)
    assert "[edit]" not in text and "Every block in the game" not in text and "[1]" not in text
    assert "For the decorative block" not in text, "hatnotes are dropped"
    assert "Old details" not in text, "subsections of a dropped section go too"
    crafting = secs[paths.index("Obtaining > Crafting")]
    assert "Any Planks + Torch" in crafting["text"]
    assert "Crafting Table recipe for 2 Glow Lamp: in one row: any Planks, Torch, any Planks" in crafting["text"]
    (recipe,) = data["recipes"]
    assert recipe["output"] == "Glow Lamp" and recipe["count"] == 2
    assert recipe["grid"] == [["any Planks", "Torch", "any Planks"]], "empty rows are trimmed: the shape is what counts"
    assert recipe["ingredients"] == {"any Planks": 2, "Torch": 1}
    assert "- It can be waterlogged." in text


def test_wiki_meta_and_icons():
    meta = textify.wiki_meta(GLOW_LAMP)
    assert meta["revid"] == 501 and meta["categories"] == ["Blocks"] and meta["title"] == "Glow Lamp"
    assert meta["canonical"] == WIKI + "/w/Glow_Lamp"
    secs, _ = textify.wiki_sections(ZOMBOID)
    assert "Health points: 20 HP (10 hearts)" in secs[0]["text"]


def test_web_page_keeps_the_article_and_drops_the_menus():
    page = """<html><head><title>Starter base guide</title></head><body>
<nav class="menu">Home Shop Login</nav><header class="site-header">Big Logo</header>
<main><h1>Starter base guide</h1><p>Dig into a hill for your first night.</p>
<h2>Walls</h2><p>Use cobblestone, it does not burn.</p><div class="share-buttons social">Share this</div></main>
<footer>(c) somebody</footer><script>var x = 1;</script></body></html>"""
    title, secs = textify.web_sections(page)
    assert title == "Starter base guide"
    assert [s["path"] for s in secs] == ["Introduction", "Walls"]
    joined = " ".join(s["text"] for s in secs)
    assert "cobblestone" in joined and "Home Shop" not in joined and "Share this" not in joined
    assert "somebody" not in joined and "var x" not in joined


def test_markdown_build_guide():
    title, secs = textify.markdown_sections("# Cozy cabin\n\nA small **oak** cabin.\n\n## Materials\n\n- 64 [oak planks](x)\n"
                                            "\n## Steps\n\n1. Floor\n2. Walls\n")
    assert title == "Cozy cabin"
    assert [s["path"] for s in secs] == ["Introduction", "Materials", "Steps"]
    assert secs[0]["text"] == "A small oak cabin." and secs[1]["text"] == "- 64 oak planks"


# ---------------------------------------------------------------- chunking

def test_chunking_respects_size_sections_and_tables():
    long_para = " ".join("Sentence number %d is here." % i for i in range(200))
    table = "Biome | Weight\n" + "\n".join("Biome %d | %d" % (i, i) for i in range(150))
    chunks = textify.chunk([{"path": "Lore", "text": long_para}, {"path": "Spawning", "text": table}], max_chars=500)
    assert all(len(c["text"]) <= 500 for c in chunks)
    lore = [c for c in chunks if c["section"] == "Lore"]
    assert len(lore) > 3 and all(c["text"].endswith(".") for c in lore), "cut between sentences"
    spawning = [c for c in chunks if c["section"] == "Spawning"]
    assert len(spawning) > 2 and all(c["text"].startswith("Biome | Weight") for c in spawning), "header row repeats"
    assert " ".join(c["text"] for c in lore).split() == long_para.split(), "nothing lost"
    huge_row = textify.chunk([{"path": "T", "text": "Name | Value\nRow | " + "word " * 800 + "\nB | 2"}], max_chars=300)
    assert all(len(c["text"]) <= 300 for c in huge_row), "one enormous table row is cut too, without looping"


def test_recipe_data_stays_with_its_chunk():
    secs, _ = textify.wiki_sections(GLOW_LAMP)
    chunks = textify.chunk(secs)
    with_recipe = [c for c in chunks if c["data"] and c["data"].get("recipes")]
    assert len(with_recipe) == 1 and with_recipe[0]["section"] == "Obtaining > Crafting"


# ---------------------------------------------------------------- crawling: html mode, incremental, resume

def test_crawl_through_pages_when_robots_forbids_the_api():
    web = FakeWeb(wiki_routes())
    s, src, f = store(), wiki_source(), fetcher(web)
    logs = []
    summary = crawler.crawl(s, src, f, {}, log=logs.append)
    assert not any("api.php" in u for u in web.urls()[1:]), "the API is never touched"
    assert any("disallows api.php" in m for m in logs)
    assert any("next pages are off-limits" in m for m in logs), "the ?pagefrom= listing is not followed"
    assert summary["new"] == 2 and summary["errors"] == 0
    titles = {r[0] for r in s.db.execute("select title from pages")}
    assert titles == {"Glow Lamp", "Tutorial:Lamp farm"}, "version pages and User: pages are skipped"
    lamp = s.page("test-wiki", "Glow Lamp")
    assert lamp["token"] == "lastmod:2026-01-01T00:00:00Z" and json.loads(lamp["meta"])["revid"] == 501
    assert lamp["url"] == WIKI + "/w/Glow_Lamp"


def test_incremental_refresh_fetches_only_what_changed():
    web = FakeWeb(wiki_routes())
    s, src, f = store(), wiki_source(), fetcher(web)
    crawler.crawl(s, src, f, {}, log=quiet)
    first_chunks = {r[0] for r in s.db.execute("select id from chunks where title = 'Glow Lamp'")}

    # nothing changed: the lamp is not asked for at all (sitemap lastmod), the tutorial (not in the
    # sitemap) is asked with If-Modified-Since and answers 304
    web.log.clear()
    src = wiki_source()
    summary = crawler.crawl(s, src, f, {}, log=quiet, refresh=True)
    assert WIKI + "/w/Glow_Lamp" not in web.urls()
    assert summary["unchanged"] == 1 and summary["same"] == 1 and summary["new"] == summary["changed"] == 0
    tut = [h for u, h in web.log if u.endswith("Tutorial:Lamp_farm")]
    assert tut and "If-Modified-Since" in tut[0]

    # the lamp page is edited: the sitemap says so and only it is fetched again
    routes = wiki_routes(lamp_lastmod="2026-03-01T00:00:00Z")
    routes[WIKI + "/w/Glow_Lamp"] = html(body=GLOW_LAMP.replace("melts snow nearby", "attracts moths"))
    web.routes = routes
    web.log.clear()
    f = fetcher(web)  # a new run (fresh sitemap read)
    summary = crawler.crawl(s, wiki_source(), f, {}, log=quiet, refresh=True)
    assert summary["changed"] == 1
    assert web.urls().count(WIKI + "/w/Glow_Lamp") == 1
    assert s.page("test-wiki", "Glow Lamp")["token"] == "lastmod:2026-03-01T00:00:00Z"
    assert "moths" in " ".join(r[0] for r in s.db.execute("select text from chunks where title = 'Glow Lamp'"))
    assert {r[0] for r in s.db.execute("select id from chunks where title = 'Glow Lamp'")} != first_chunks


def test_unchanged_chunks_keep_their_vectors():
    calls = []

    def embed(texts, query=False):
        calls.extend(texts)
        return [[1.0, float(len(t) % 7), 0.5] for t in texts]
    s = store(embed, "test")
    src = sources.make("local", {"local": {"kind": "local", "path": tempfile.mkdtemp()}})
    doc = sources.Document("g", "Guide", "file://g", [{"path": "A", "text": "alpha text"}, {"path": "B", "text": "beta"}])
    s.put_document(src, doc)
    assert len(calls) == 2
    doc2 = sources.Document("g", "Guide", "file://g", [{"path": "A", "text": "alpha text"}, {"path": "B", "text": "gamma"}])
    assert s.put_document(src, doc2)[0] == "changed"
    assert len(calls) == 3, "only the edited chunk is embedded again"
    assert s.put_document(src, doc2)[0] == "same"


def test_a_stopped_crawl_resumes_where_it_was():
    web = FakeWeb(wiki_routes())
    s, f = store(), fetcher(web)
    first = crawler.crawl(s, wiki_source(), f, {}, limit=1, log=quiet)
    assert first["processed"] == 1 and first["left"] == 1
    web.log.clear()
    second = crawler.crawl(s, wiki_source(), f, {}, log=quiet)
    assert second["processed"] == 1 and second["left"] == 0
    assert s.db.execute("select count(*) from pages").fetchone()[0] == 2
    page_requests = [u for u in web.urls() if "/w/" in u and "Category" not in u]
    assert len(page_requests) == 1, "the page done the first time is not fetched again"
    assert not any("Category" in u for u in web.urls()), "a bare crawl after a stop resumes, it doesn't look for more"
    assert json.loads(s.source_row("test-wiki")["params"]) == {"categories": ["Blocks"]}, "refresh will ask again"


def test_pages_that_disappear_are_removed():
    web = FakeWeb(wiki_routes())
    s, f = store(), fetcher(web)
    crawler.crawl(s, wiki_source(), f, {}, log=quiet)
    web.routes[WIKI + "/w/Tutorial:Lamp_farm"] = html(404, "gone")
    summary = crawler.crawl(s, wiki_source(), fetcher(web), {}, log=quiet, refresh=True)
    assert summary["gone"] == 1 and s.page("test-wiki", "Tutorial:Lamp farm") is None


def test_api_mode_when_the_wiki_allows_it():
    api_base = WIKI + "/api.php?"

    def q(**params):
        import urllib.parse
        params.update({"format": "json", "formatversion": "2", "maxlag": "5"})
        return api_base + urllib.parse.urlencode(params)
    members = {"batchcomplete": True, "query": {"pages": [
        {"ns": 0, "title": "Zomboid", "lastrevid": 777}, {"ns": 14, "title": "Category:Undead"}]}}
    undead = {"query": {"pages": [{"ns": 0, "title": "Zomboid", "lastrevid": 777}]}}
    parse = {"parse": {"title": "Zomboid", "revid": 777, "text": ZOMBOID, "categories": [{"category": "Mobs"}]}}
    routes = {
        WIKI + "/robots.txt": (200, {}, "User-agent: *\nDisallow: /w/Special:\n"),
        q(action="query", generator="categorymembers", gcmtitle="Category:Mobs", gcmlimit="500",
          gcmtype="page|subcat", prop="info"): (200, {}, json.dumps(members)),
        q(action="query", generator="categorymembers", gcmtitle="Category:Undead", gcmlimit="500",
          gcmtype="page|subcat", prop="info"): (200, {}, json.dumps(undead)),
        q(action="parse", page="Zomboid", prop="text|revid|categories|displaytitle", redirects="1",
          disableeditsection="1"): (200, {}, json.dumps(parse)),
    }
    web = FakeWeb(routes)
    s, f = store(), fetcher(web)
    summary = crawler.crawl(s, wiki_source(sitemaps=[]), f, {"categories": ["Mobs"]}, log=quiet)
    assert summary["new"] == 1 and summary["errors"] == 0, summary
    assert s.page("test-wiki", "Zomboid")["token"] == "rev:777"
    web.log.clear()
    again = crawler.crawl(s, wiki_source(sitemaps=[]), fetcher(web), {"categories": ["Mobs"]}, log=quiet)
    assert again["unchanged"] == 1 and not any("action=parse" in u for u in web.urls()), "same revision: not fetched"


def test_web_source_obeys_robots_and_reads_a_sitemap():
    site = "https://guides.example"
    routes = {
        site + "/robots.txt": (200, {}, "User-agent: *\nDisallow: /members/\n"),
        site + "/sitemap.xml": (200, {}, '<urlset><url><loc>%s/guides/house</loc><lastmod>2026-01-01</lastmod></url>'
                                         '<url><loc>%s/members/secret</loc></url><url><loc>%s/shop/item</loc></url>'
                                         '</urlset>' % (site, site, site)),
        site + "/guides/house": html(body="<html><title>House</title><main><p>Four walls and a roof.</p></main></html>"),
    }
    cfg = {"kind": "web", "sitemap": site + "/sitemap.xml", "allow": [site + "/guides/", site + "/members/"],
           "license": "CC BY 4.0"}
    web = FakeWeb(routes)
    s = store()
    summary = crawler.crawl(s, sources.make("guides", {"guides": cfg}), fetcher(web), {}, log=quiet)
    assert summary["new"] == 1 and summary["blocked"] == 1
    assert site + "/members/secret" not in web.urls() and site + "/shop/item" not in web.urls()
    assert s.search("roof")[0]["license"] == "CC BY 4.0"


def test_local_files_are_added_updated_and_removed():
    folder = tempfile.mkdtemp()
    p = os.path.join(folder, "farm.md")
    with open(p, "w") as fh:
        fh.write("# Sugar cane farm\n\nPlant cane next to water. Pistons harvest it.\n")
    src = sources.make("local", {"local": {"kind": "local", "path": folder, "license": "mine"}})
    s = store()
    assert crawler.crawl(s, src, fetcher(FakeWeb({})), {}, log=quiet)["new"] == 1
    assert crawler.crawl(s, src, fetcher(FakeWeb({})), {}, log=quiet)["unchanged"] == 1
    with open(p, "w") as fh:
        fh.write("# Sugar cane farm\n\nPlant cane next to water. Observers and pistons harvest it.\n")
    os.utime(p, (2_000_000_000, 2_000_000_000))
    assert crawler.crawl(s, src, fetcher(FakeWeb({})), {}, log=quiet)["changed"] == 1
    os.remove(p)
    assert crawler.crawl(s, src, fetcher(FakeWeb({})), {}, log=quiet, refresh=True)["gone"] == 1
    assert s.search("sugar cane") == []


# ---------------------------------------------------------------- search ranking

def _filled_store(embed=None, model=""):
    s = store(embed, model)
    src = wiki_source()
    for page in (GLOW_LAMP, ZOMBOID, LAMP_FARM):
        meta = textify.wiki_meta(page)
        secs, data = textify.wiki_sections(page)
        doc = sources.Document(meta["title"], meta["title"], meta["canonical"], secs, data, {"edition": "Java"}, "t")
        s.upsert_source(src)
        s.put_document(src, doc)
    return s


def test_search_finds_the_recipe_for_a_how_do_i_make_question():
    s = _filled_store()
    top = s.search("how do I make a glow lamp?", k=3)[0]
    assert top["title"] == "Glow Lamp" and top["section"] == "Obtaining > Crafting"
    assert top["data"]["recipes"][0]["ingredients"] == {"any Planks": 2, "Torch": 1}
    assert top["url"] == WIKI + "/w/Glow_Lamp" and top["license"] == "CC BY-NC-SA 3.0"
    assert top["attribution"].startswith("Minecraft Wiki contributors")


def test_search_answers_by_kind_of_question():
    s = _filled_store()
    assert s.search("where do zomboids spawn", k=1)[0]["section"] == "Spawning"
    assert s.search("how much health does a zomboid have", k=1)[0]["section"] == "Facts"
    assert s.search("what do zomboids drop", k=1)[0]["section"] == "Drops"
    assert s.search("how do I build a lamp farm", k=1)[0]["title"] == "Tutorial:Lamp farm"
    assert s.search("zzzz qqqq") == []
    other = s.search("how do I make a diamond pickaxe", k=3)
    assert not any(r["about"] and r["section"] == "Obtaining > Crafting" for r in other), \
        "a recipe for something else is not presented as the answer"


def test_search_limits_chunks_per_page_and_by_source():
    s = _filled_store()
    res = s.search("zomboid", k=10)
    assert sum(1 for r in res if r["title"] == "Zomboid") == 2
    assert s.search("zomboid", sources=["somewhere-else"]) == []


def test_meaning_helps_when_the_words_differ():
    vocab = ["light", "undead", "farm", "hopper", "lamp"]

    def embed(texts, query=False):
        out = []
        for t in texts:
            t = t.lower()
            v = [float(t.count(w)) for w in vocab]
            if "glow" in t or "bright" in t:  # "bright" means a lamp, for this stand-in model
                v[4] += 2
            out.append([x + 0.01 for x in v])
        return out
    s = _filled_store(embed, "test")
    assert s.db.execute("select count(*) from chunks where emb is null").fetchone()[0] == 0
    top = s.search("something bright to put on my wall", k=1)[0]
    assert top["title"] == "Glow Lamp" and top["similarity"] > 0


def test_search_without_embedder_after_embeddings_fail():
    def broken(texts, query=False):
        raise OSError("gateway down")
    s = _filled_store(broken, "test")
    assert s.embed_errors > 0
    assert s.search("glow lamp", k=1)[0]["title"] == "Glow Lamp", "keyword search still works"


# ---------------------------------------------------------------- the gateway route and the CLI

def test_gateway_knowledge_route(monkeypatch=None):
    import kindred_gateway
    kdir = tempfile.mkdtemp()
    os.environ["KINDRED_KNOWLEDGE"] = kdir
    try:
        s = KnowledgeStore(os.path.join(kdir, "knowledge.db"))
        src = wiki_source()
        s.upsert_source(src)
        secs, data = textify.wiki_sections(ZOMBOID)
        s.put_document(src, sources.Document("Zomboid", "Zomboid", WIKI + "/w/Zomboid", secs, data, {}, "t"))
        state = kindred_gateway.deep_merge(kindred_gateway.DEFAULT_STATE, {"embeddings": {"use": "none"}})
        out = kindred_gateway.knowledge_call(state, "search", {"query": "where do zomboids spawn", "k": 2,
                                                              "max_chars": 40})
        assert out["count"] == 2 and out["results"][0]["section"] == "Spawning"
        assert out["results"][0]["url"] == WIKI + "/w/Zomboid" and len(out["results"][0]["text"]) <= 44
        assert kindred_gateway.knowledge_call(state, "stats", {})["pages"] == 1
        try:
            kindred_gateway.knowledge_call(state, "crawl", {})
            raise AssertionError("crawling is not offered over HTTP")
        except LookupError:
            pass
    finally:
        os.environ.pop("KINDRED_KNOWLEDGE", None)
        api._stores.clear()


def test_cli_crawls_local_files_and_searches(capsys):
    from knowledge import kb
    kdir = tempfile.mkdtemp()
    os.makedirs(os.path.join(kdir, "local"))
    with open(os.path.join(kdir, "local", "bridge.md"), "w") as fh:
        fh.write("# Nether bridge\n\nUse cobblestone: ghasts cannot blow it up.\n")
    assert kb.main(["--dir", kdir, "--no-embed", "crawl", "local"]) == 0
    assert kb.main(["--dir", kdir, "--no-embed", "search", "what should my nether bridge be made of"]) == 0
    out = capsys.readouterr().out
    assert "Nether bridge" in out and "ghasts" in out
    assert kb.main(["--dir", kdir, "--no-embed", "remove", "local"]) == 0
    assert KnowledgeStore(os.path.join(kdir, "knowledge.db")).stats()["pages"] == 0


# ---------------------------------------------------------------- confidence and learning on demand

from knowledge import learn  # noqa: E402
from knowledge.sources import Item  # noqa: E402


def test_coverage_says_when_the_answer_is_really_there():
    s = _filled_store()
    assert s.ask("how do I make a glow lamp")["covered"]
    assert s.ask("where do zomboids spawn")["covered"]
    miss = s.ask("how do I make a diamond pickaxe")
    assert not miss["covered"] and miss["threshold"] == 0.55
    assert not s.ask("how do I tame a parrot")["covered"]
    assert s.ask("how do I build a lamp farm")["covered"], "a tutorial answers a build question"


def test_a_build_question_needs_a_guide():
    s = store()
    src = wiki_source()
    s.upsert_source(src)
    secs, data = textify.wiki_sections(GLOW_LAMP)
    s.put_document(src, sources.Document("Glow Lamp", "Glow Lamp", WIKI + "/w/Glow_Lamp", secs, data, {}, "t"))
    assert not s.ask("how do I build a glow lamp farm")["covered"], "the item page is not a farm design"


def test_rank_titles_picks_the_pages_about_the_question():
    items = [Item(t, t, WIKI + "/w/" + t.replace(" ", "_")) for t in (
        "Iron Golem", "Iron Ingot", "Iron", "Tutorial:Iron golem farming", "Tutorial:Mob farm", "Zombie",
        "Zombie Villager", "Spawn", "Tutorial:Iron golem farming/Old designs", "Java Edition 1.2")]
    top = [i.title for i in learn.rank_titles("how do I build an iron farm?", items)]
    assert top[0] == "Tutorial:Iron golem farming"
    assert [i.title for i in learn.rank_titles("where do zombies spawn", items)][0] == "Zombie"
    assert [i.title for i in learn.rank_titles("how do I build a mob farm", items)][0] == "Tutorial:Mob farm"
    assert learn.rank_titles("what is love", items) == []


TUTORIAL_SITEMAP = ("/tutorials.xml.gz", [("Tutorial:Lamp_farm", "2026-01-05T00:00:00Z")])


def learn_routes():
    routes = wiki_routes()
    routes[WIKI + "/tutorials.xml.gz"] = sitemap(TUTORIAL_SITEMAP[1])
    return routes


def learn_source():
    return wiki_source(sitemaps=["/sitemap.xml.gz", "/tutorials.xml.gz"])


def test_learning_makes_an_uncovered_question_covered():
    kdir = tempfile.mkdtemp()
    web = FakeWeb(learn_routes())
    s, f = store(), fetcher(web)
    q = "how do I build a lamp farm?"
    assert not s.ask(q)["covered"]
    out = learn.learn(s, learn_source(), f, q, kdir)
    assert out["status"] == "learned", out
    assert out["added"][0]["title"] == "Tutorial:Lamp farm" and out["added"][0]["chunks"] > 0
    assert not any("api.php" in u or "Special:" in u for u in web.urls()), "robots.txt still rules"
    assert out["requests"] <= 1 + 2 + learn.DEFAULTS["pages_per_learn"]
    after = s.ask(q)
    assert after["covered"] and after["results"][0]["title"] == "Tutorial:Lamp farm"
    assert after["results"][0]["url"] == WIKI + "/w/Tutorial:Lamp_farm" and after["results"][0]["license"]
    again = learn.learn(s, learn_source(), f, "lamp farm: how to build one", kdir)
    assert again["status"] == "recent", "the same question (in other words) is not looked up again for a day"


def test_learning_skips_pages_already_fresh():
    kdir = tempfile.mkdtemp()
    web = FakeWeb(learn_routes())
    s, f = store(), fetcher(web)
    crawler.crawl(s, learn_source(), f, {"pages": ["Glow Lamp"]}, log=quiet)
    web.log.clear()
    out = learn.learn(s, learn_source(), f, "how do I make a glow lamp", kdir)
    assert out["status"] == "known" and out["added"][0]["status"] == "fresh"
    assert WIKI + "/w/Glow_Lamp" not in web.urls()


def test_learning_caps():
    kdir = tempfile.mkdtemp()
    web = FakeWeb(learn_routes())
    s, f = store(), fetcher(web)
    learn.save_settings(kdir, max_per_hour=1)
    assert learn.learn(s, learn_source(), f, "how do I build a lamp farm", kdir)["status"] == "learned"
    capped = learn.learn(s, learn_source(), f, "where do zomboids spawn", kdir)
    assert capped["status"] == "capped" and capped["added"] == []
    later = learn.learn(s, learn_source(), f, "where do zomboids spawn", kdir, now=time_in(2))
    assert later["status"] == "learned", "an hour later it may look again"

    web.log.clear()
    learn.save_settings(kdir, enabled=False)
    assert learn.learn(s, learn_source(), f, "glow lamp", kdir)["status"] == "off" and web.log == []
    learn.save_settings(kdir, enabled=True, max_total_mb=0.000001)
    assert learn.learn(s, learn_source(), f, "glow lamp", kdir, now=time_in(4))["status"] == "full"
    os.environ["KINDRED_KNOWLEDGE_LEARN"] = "0"
    try:
        assert not learn.settings(kdir)["enabled"]
    finally:
        os.environ.pop("KINDRED_KNOWLEDGE_LEARN")


def time_in(hours):
    import time
    return time.time() + hours * 3600


def test_learning_uses_the_wiki_search_when_the_api_is_allowed():
    import urllib.parse

    def q(**params):
        params.update({"format": "json", "formatversion": "2", "maxlag": "5"})
        return WIKI + "/api.php?" + urllib.parse.urlencode(params)
    routes = {
        WIKI + "/robots.txt": (200, {}, "User-agent: *\nDisallow: /w/Special:\n"),
        q(action="query", list="search", srsearch="where do zomboids spawn", srlimit="10", srnamespace="0",
          srwhat="text"): (200, {}, json.dumps({"query": {"search": [{"title": "Zomboid"}]}})),
        q(action="query", prop="info", titles="Zomboid", redirects="1"):
            (200, {}, json.dumps({"query": {"pages": [{"title": "Zomboid", "lastrevid": 777}]}})),
        q(action="parse", page="Zomboid", prop="text|revid|categories|displaytitle", redirects="1",
          disableeditsection="1"): (200, {}, json.dumps({"parse": {"title": "Zomboid", "revid": 777, "text": ZOMBOID}})),
    }
    s = store()
    out = learn.learn(s, wiki_source(sitemaps=[]), fetcher(FakeWeb(routes)), "where do zomboids spawn",
                      tempfile.mkdtemp())
    assert out["status"] == "learned" and out["added"][0]["title"] == "Zomboid"
    assert s.ask("where do zomboids spawn")["covered"]


def test_gateway_learn_and_search_with_confidence():
    import kindred_gateway
    kdir = tempfile.mkdtemp()
    sources.save_config("test-wiki", dict(learn_source().config), kdir)
    learn.save_settings(kdir, source="test-wiki")
    api._fetchers[kdir] = fetcher(FakeWeb(learn_routes()))
    os.environ["KINDRED_KNOWLEDGE"] = kdir
    try:
        state = kindred_gateway.deep_merge(kindred_gateway.DEFAULT_STATE, {"embeddings": {"use": "none"}})
        q = {"query": "how do I build a lamp farm", "k": 3}
        before = kindred_gateway.knowledge_call(state, "search", q)
        assert before["covered"] is False and before["count"] == 0
        out = kindred_gateway.knowledge_call(state, "learn", q)
        assert out["status"] == "learned" and out["covered"] is True
        assert out["results"][0]["title"] == "Tutorial:Lamp farm"
        after = kindred_gateway.knowledge_call(state, "search", q)
        assert after["covered"] and after["best"] >= after["threshold"]
    finally:
        os.environ.pop("KINDRED_KNOWLEDGE", None)
        api._stores.clear()
        api._fetchers.clear()
        api._sources.clear()


def test_reindex_rebuilds_from_the_cache_without_network():
    web = FakeWeb(wiki_routes())
    s, f = store(), fetcher(web)
    crawler.crawl(s, wiki_source(), f, {}, log=quiet)
    s.db.execute("delete from chunks where title = 'Glow Lamp'")  # as if an older parser had lost them
    s.db.execute("update pages set hash = 'old' where title = 'Glow Lamp'")
    s.db.commit()
    web.log.clear()
    counts = crawler.reindex(s, wiki_source(), f, log=quiet)
    assert counts["changed"] == 1 and counts["same"] == 1 and web.log == []
    assert s.ask("how do I make a glow lamp")["covered"]


def test_a_similar_name_is_not_an_answer():
    s = _filled_store()
    src = wiki_source()
    page = ZOMBOID.replace("Zomboid", "Smiling Zomboid").replace("zomboid", "smiling zomboid")
    secs, data = textify.wiki_sections(page)
    s.db.execute("delete from chunks where title = 'Zomboid'")
    s.db.commit()
    s.put_document(src, sources.Document("Smiling Zomboid", "Smiling Zomboid", WIKI + "/w/Smiling_Zomboid", secs, data,
                                         {}, "t"))
    ans = s.ask("where do zomboids spawn")
    assert ans["results"][0]["title"] == "Smiling Zomboid" and not ans["covered"]


def _guide(s, title, sections, categories=("Tutorials",)):
    src = wiki_source()
    s.upsert_source(src)
    s.put_document(src, sources.Document(title, title, WIKI + "/w/" + title.replace(" ", "_"),
                                         [{"path": p, "text": t} for p, t in sections], {},
                                         {"categories": list(categories)}, "t"))


def test_current_guides_come_before_outdated_ones():
    old_only = store()
    _guide(old_only, "Tutorial:Door-based lamp farming",
           [("Basics", "This tutorial describes lamp farming as it formerly worked prior to Java Edition 1.14. "
                       "Build a lamp farm with doors and villagers.")], ("Outdated tutorials", "Tutorials"))
    ans = old_only.ask("how do I build a lamp farm")
    assert ans["results"][0]["outdated"] and not ans["covered"], "an old version alone is not an answer: learn the current one"
    _guide(old_only, "Tutorial:Lamp farming", [("Basics", "Build a lamp farm with beds, workstations and villagers.")])
    ans = old_only.ask("how do I build a lamp farm")
    assert ans["results"][0]["title"] == "Tutorial:Lamp farming" and ans["covered"]


def test_a_whole_section_in_order_and_where_it_goes_on():
    s = store()
    steps = ["Step %d. " % i + ("Place cobblestone in a ring around the lamps. " * 30) for i in range(1, 5)]
    _guide(s, "Tutorial:Lamp farming", [("Basics", "A lamp farm needs lamps."), ("Tower design", "\n\n".join(steps)),
                                        ("Collection", "Hoppers into a chest.")])
    first = s.search("tower design lamp farm cobblestone", k=1)[0]
    sec = s.section(chunk_id=first["id"], max_chars=2000)
    assert sec["section"] == "Tower design" and sec["text"].startswith("Step 1.") and sec["more"]
    assert sec["outline"] == ["Basics", "Tower design", "Collection"] and sec["next_section"] == "Collection"
    rest = s.section(page="Tutorial:Lamp farming", name="tower", start=sec["next_start"], max_chars=100000)
    assert "Step 4." in rest["text"] and not rest["more"]
    assert s.section(page="Tutorial:Lamp farming", name="collect")["text"] == "Hoppers into a chest."
