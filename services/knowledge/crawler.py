"""Crawling: discover -> queue -> fetch -> clean -> chunk -> store (-> embed).

The queue lives in the knowledge database, so a crawl that is stopped (Ctrl+C, a crash, a
closed laptop) simply continues where it was the next time. Pages whose version token is
unchanged are not fetched again; pages fetched again but unchanged keep their chunks and vectors.
"""
import json
import time

from .fetcher import Blocked
from .sources import GONE, Item


def crawl(store, src, fetcher, opts=None, limit=None, log=print, refresh=False):
    """Crawl one source. opts: categories, pages, depth, all, offline, retry.
    Returns a summary dict."""
    opts = dict(opts or {})
    t0 = time.time()
    req0, bytes0 = fetcher.requests, fetcher.bytes
    if src.delay is not None and not opts.get("delay_given"):
        fetcher.delay = max(fetcher.delay, float(src.delay))
    explicit = opts.get("categories") or opts.get("pages") or opts.get("all")
    resume = not refresh and not explicit and store.pending(src.name)
    if not refresh and not explicit and not resume and src.config.get("default_categories"):
        opts["categories"] = list(src.config["default_categories"])  # a first crawl: the starter set
        log("  no --category/--page given: the starter categories %s" % ", ".join(opts["categories"]))
    store.upsert_source(src, params=src.params(opts))
    if opts.get("retry"):
        n = store.retry_failed(src.name)
        if n:
            log("  trying %d failed pages again" % n)

    # 1. what is there to fetch (cheap: a few listing pages and the sitemap)
    if resume:  # a bare `crawl SOURCE` after a stop: carry on, don't look for more
        items = []
        log("  resuming: %d pages still queued from last time" % len(resume))
    else:
        items = list(src.discover(fetcher, opts, log))
    if refresh:  # also look again at every page already stored, however it was found
        known = {i.key for i in items}
        lastmods = getattr(src, "_lastmods", None) or {}
        for r in store.db.execute("select key, title, url from pages where source = ?", (src.name,)):
            if r["key"] not in known:
                lm = lastmods.get(r["url"])
                items.append(Item(r["key"], r["title"], r["url"], ("lastmod:" + lm) if lm else None))
    queued, unchanged = store.enqueue(src.name, items)
    pend = store.pending(src.name)
    log("  %s: %d found, %d unchanged since last time, %d to fetch%s" % (
        src.name, len(items), unchanged, len(pend), (" (stopping after %d)" % limit) if limit and limit < len(pend) else ""))

    # 2. fetch them, politely, one by one
    counts = {"new": 0, "changed": 0, "same": 0, "gone": 0, "skipped": 0, "blocked": 0, "errors": 0, "chunks": 0}
    done = 0
    try:
        for q in pend:
            if limit and done >= limit:
                break
            done += 1
            item = Item(q["key"], q["title"], q["url"], q["token"])
            status, title, n, error = fetch_one(store, src, fetcher, item, offline=bool(opts.get("offline")))
            counts[status] += 1
            counts["chunks"] += n
            if status in ("blocked", "errors"):
                store.mark(src.name, item.key, "blocked" if status == "blocked" else "error", error)
                log("  [%d/%d] %s: %s (%s)" % (done, len(pend), title, "skipped" if status == "blocked" else "failed",
                                              error[:120]))
                continue
            store.mark(src.name, item.key, "done", "gone" if status == "gone" else error if status == "skipped" else None)
            log("  [%d/%d] %s: %s%s" % (done, len(pend), title, "gone, removed" if status == "gone" else
                                       ("not kept (%s)" % error) if status == "skipped" else status,
                                       (" (%d chunks)" % n) if n else ""))
    except KeyboardInterrupt:
        log("  stopped: %d pages still queued, `kb.py crawl %s` continues from here" % (
            len(store.pending(src.name)), src.name))
        raise
    finally:
        store.upsert_source(src, crawled=not refresh, refreshed=refresh)
        store.prune_params(src.name)
    took = time.time() - t0
    summary = dict(counts, source=src.name, found=len(items), unchanged=unchanged, processed=done,
                   left=len(store.pending(src.name)), requests=fetcher.requests - req0,
                   downloaded=fetcher.bytes - bytes0, seconds=round(took, 1),
                   embed_errors=store.embed_errors, embed_error=store.last_embed_error)
    return summary


def fetch_one(store, src, fetcher, item, offline=False):
    """Fetch, clean, chunk and store one page. Returns (status, title, chunks, error) with status
    new | changed | same | gone | skipped | blocked | errors. Never raises for a bad page."""
    try:
        doc = src.fetch(fetcher, item, offline=offline)
    except Blocked as exc:
        return "blocked", item.title or item.key, 0, str(exc)
    except Exception as exc:  # one bad page must not stop a crawl: it is retried next time
        return "errors", item.title or item.key, 0, str(exc)[:300]
    if doc is GONE:
        store.delete_page(src.name, item.key)
        return "gone", item.title or item.key, 0, None
    if doc.key != item.key and hasattr(src, "wanted") and not src.wanted(doc.key):
        # a redirect to a page the rules leave out ("Tutorial:Redstone" is the "Tutorials" index)
        store.delete_page(src.name, item.key)
        return "skipped", doc.title, 0, "redirects to %s" % doc.title
    skip = src.skip_status() if hasattr(src, "skip_status") else ()
    if doc.meta.get("status") in skip:  # April Fools, spin-off games: not kept
        store.delete_page(src.name, item.key)
        if doc.key != item.key:
            store.delete_page(src.name, doc.key)
        return "skipped", doc.title, 0, doc.meta["status"]
    if doc.key != item.key and store.page(src.name, item.key):
        store.delete_page(src.name, item.key)  # it moved (a redirect): keep one copy, under the new name
    try:
        status, n = store.put_document(src, doc)
    except Exception as exc:
        return "errors", doc.title, 0, "storing: %s" % str(exc)[:280]
    if doc.token is None and item.token:
        store.touch_page(src.name, doc.key, item.token)
    return status, doc.title, n, None


def reindex(store, src, fetcher, log=print):
    """Rebuild every stored page of a source from the download cache, no network: after the
    cleaning or chunking rules changed. Pages whose text comes out the same are left as they are."""
    counts = {"new": 0, "changed": 0, "same": 0, "gone": 0, "skipped": 0, "blocked": 0, "errors": 0, "chunks": 0}
    rows = store.db.execute("select key, title, url, token from pages where source = ?", (src.name,)).fetchall()
    for r in rows:
        if hasattr(src, "wanted") and not src.wanted(r["key"]):  # the source's rules now leave it out
            store.delete_page(src.name, r["key"])
            counts["skipped"] += 1
            log("  %s: removed (not wanted any more)" % r["title"])
            continue
        url = src.url_of(r["key"]) if hasattr(src, "url_of") else r["url"]  # the address it was fetched by
        status, title, n, error = fetch_one(store, src, fetcher, Item(r["key"], r["title"], url, r["token"]),
                                            offline=True)
        if status == "gone":
            status = "errors"  # not in the cache is not "gone": keep the page
        counts[status] += 1
        counts["chunks"] += n
        if status == "changed":
            log("  %s: changed (%d chunks)" % (title, n))
        elif status == "skipped":
            log("  %s: removed (%s)" % (title, error))
        elif status == "errors":
            log("  %s: %s" % (title, error or "not in the cache"))
    return counts


def linked_titles(store, src, min_links=3, exclude=(), canonical=None):
    """Pages the stored pages link to most, not stored yet: [(title, how many pages link to it)].
    What a set of good pages keeps pointing at (Diamond, Redstone Dust, Crafting Table) is worth
    having too; a focused crawl grows the knowledge base along those links. canonical: the real
    titles ({lowercase: Title}, from the sitemap): a link to "Iron golem" or "Endermen" is a
    redirect to a page stored already, or to one under its real name; links to no real page go."""
    def real(t):
        if canonical is None:
            return t
        return canonical.get(t.lower())
    have = {r[0] for r in store.db.execute("select key from pages where source = ?", (src.name,))}
    have |= {r[0] for r in store.db.execute("select key from queue where source = ? and status = 'done'", (src.name,))}
    have = {real(t) or t for t in have}
    count = {}
    for (meta,) in store.db.execute("select meta from pages where source = ?", (src.name,)):
        try:
            links = json.loads(meta or "{}").get("links") or []
        except ValueError:
            continue
        for t in {real(x) for x in links} - {None}:
            if t not in have and t not in exclude and (not hasattr(src, "wanted") or src.wanted(t)):
                count[t] = count.get(t, 0) + 1
    return sorted(((t, n) for t, n in count.items() if n >= min_links), key=lambda x: (-x[1], x[0]))
