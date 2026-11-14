"""The knowledge base over HTTP, mounted by the gateway (services/kindred_gateway.py):

    POST /v1/knowledge/search   {"query": "how do I make a piston", "k": 5, "sources": ["minecraft-wiki"],
                                 "max_chars": 1200}
        -> {"results": [{title, section, text, url, source, license, license_url, attribution, edition,
                         score, data, status, since}], "count": n}
        status: "current", or why the page isn't about the player's game ("future" with since
        "1.21.6", "outdated", "removed", "other-edition", "other-version": game data from another version);
        "outdated": true for anything not current. "game_version": "26.3" judges it for that version.
        and how well it is covered: "best" (the top score), "covered" (true when the best chunk is
        about everything the question names and scores >= "threshold"; see store.coverage)
    POST /v1/knowledge/learn    {"query": "how do I build an iron farm"}
        -> read the few wiki pages that answer it, now (learn.py; bounded by settings.json):
           {"status": "learned"|"known"|"nothing"|"off"|"capped"|"full"|"recent", "added": [{title,
            status, chunks}], "seconds", "requests", "covered", "results": [the new answer]}
    POST /v1/knowledge/stats    {} -> pages, chunks, sources, size on disk
    POST /v1/knowledge/sources  {} -> the configured sources and their licenses

Crawling whole categories is done with kb.py, never over HTTP; learn is the one bounded write
(a few pages per question, capped per hour and in size). The gateway passes its own embedder so
a question is embedded with the same model the chunks were.
"""
import os
import threading

from . import db_path, learn as learn_mod, sources as sources_mod
from .fetcher import Fetcher
from .sources import knowledge_dir
from .store import KnowledgeStore

_stores = {}
_fetchers = {}               # knowledge dir -> Fetcher (keeps robots.txt and the request pacing)
_sources = {}                # (knowledge dir, source) -> Source (keeps the sitemap title index)
_learning = threading.Lock()  # one look-up at a time: the wiki sees one polite visitor


def store_for(embed=None, model="", path=None):
    path = path or db_path()
    key = (path, model)
    if key not in _stores:
        _stores[key] = KnowledgeStore(path, embed=embed if model else None, model_name=model)
    return _stores[key]


def call(op, req, embed=None, model="", path=None):
    req = req or {}
    if op == "sources":
        return {"sources": [sources_mod.make(n).describe() for n in sources_mod.load_configs()]}
    if op not in ("search", "stats", "learn", "section"):
        raise LookupError("unknown knowledge operation " + op)
    if op == "learn":
        return _learn(req, embed, model, path)
    if not os.path.exists(path or db_path()):
        if op == "stats":
            return {"pages": 0, "chunks": 0, "sources": {}, "note": "empty: run services/knowledge/kb.py crawl"}
        return {"results": [], "count": 0, "best": 0.0, "covered": False,
                "note": "the knowledge base is empty: run services/knowledge/kb.py crawl"}
    store = store_for(embed, model, path)
    if op == "stats":
        return store.stats()
    if op == "section":  # a whole section of a page, in order (step-by-step guides)
        return store.section(req.get("chunk_id"), req.get("page"), req.get("name"), int(req.get("start") or 0),
                             int(req.get("max_chars") or 4500))
    query = str(req.get("query") or "").strip()
    if not query:
        raise ValueError("query is empty")
    k = max(1, min(20, int(req.get("k", 5))))
    ans = store.ask(query, k=k, sources=req.get("sources"), per_page=int(req.get("per_page", 2)),
                    game_version=_version(req))
    _trim(ans["results"], int(req.get("max_chars") or 0))
    return dict(ans, count=len(ans["results"]))


def _version(req):
    """The player's Minecraft version, when the caller says it ("26.3"; #151)."""
    v = str(req.get("game_version") or "").strip()[:20]
    parts = v.split(".")  # (no regex on what the caller sends: 2 or 3 numbers, short)
    return v if 2 <= len(parts) <= 3 and all(p.isascii() and p.isdigit() and len(p) <= 4 for p in parts) else None


def _trim(results, cut):
    for r in results:
        r.pop("page_id", None)  # (the chunk "id" stays: it asks for the whole section)
        if cut and len(r["text"]) > cut:
            r["text"] = r["text"][:cut].rsplit(" ", 1)[0] + " ..."


def _learn(req, embed, model, path):
    query = str(req.get("query") or "").strip()
    if not query:
        raise ValueError("query is empty")
    path = path or db_path()
    kdir = os.path.dirname(path) or knowledge_dir()
    conf = learn_mod.settings(kdir)
    name = req.get("source") or conf.get("source") or "minecraft-wiki"
    store = store_for(embed, model, path)
    if not _learning.acquire(timeout=float(req.get("wait", 30))):
        return {"status": "busy", "query": query, "added": [], "reason": "another look-up is running"}
    try:
        if (kdir, name) not in _sources:
            _sources[(kdir, name)] = sources_mod.make(name, sources_mod.load_configs(kdir))
        src = _sources[(kdir, name)]
        if kdir not in _fetchers:
            _fetchers[kdir] = Fetcher(cache_dir=os.path.join(kdir, "cache"))
        out = learn_mod.learn(store, src, _fetchers[kdir], query, kdir, conf)
    finally:
        _learning.release()
    ans = store.ask(query, k=int(req.get("k", 3)), sources=req.get("sources"), game_version=_version(req))
    _trim(ans["results"], int(req.get("max_chars") or 0))
    return dict(out, covered=ans["covered"], best=ans["best"], results=ans["results"])
