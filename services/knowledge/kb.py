#!/usr/bin/env python3
"""Kindred Spirit's knowledge base, from the command line.

    kb.py sources                                   the sources and their licenses
    kb.py crawl minecraft-wiki --core [--grow 600]  the pages survival players ask about, then the pages
                                                    they link to most (the recommended set, see below)
    kb.py crawl minecraft-wiki [--limit N] [--category Mobs ...] [--page Piston ...] [--all] [--depth 1]
    kb.py crawl local                               your own .md/.txt files (~/.kindred-spirit/knowledge/local)
    kb.py refresh [SOURCE] [--limit N]              fetch again only what changed
    kb.py search "how do I make a piston" [-k 5] [--source minecraft-wiki] [--json]
    kb.py learn "how do I build an iron farm"       read the few wiki pages that answer it, now
    kb.py learning [on|off] [--per-hour N] [--pages N] [--max-mb N]   on-demand learning settings
    kb.py stats                                     pages, chunks, vectors, size on disk
    kb.py reindex [SOURCE]                          rebuild stored pages from the cache (after a parser change)
    kb.py embed                                     give vectors to chunks that have none (gateway needed)
    kb.py compact                                   smaller on disk: 16-bit vectors, free space given back
    kb.py remove SOURCE [--cache]                   forget a source (and its cached downloads)
    kb.py add NAME --kind web --sitemap URL --allow PREFIX --license "..."     add a source
    kb.py eval [--json FILE]                        score it on questions players ask (eval_questions.json)

A crawl that is stopped continues where it was the next time. Requests go one at a time,
at most one per second (--delay), obey robots.txt and are cached. See docs/KNOWLEDGE.md.
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import knowledge  # noqa: E402
from knowledge import crawler, learn, sources  # noqa: E402
from knowledge.fetcher import Fetcher  # noqa: E402


def say(msg):
    print(msg, flush=True)  # a long crawl written to a file shows its progress as it goes


def human(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%.0f %s" if unit == "B" else "%.1f %s") % (n, unit)
        n /= 1024


def dir_size(path):
    total = 0
    for d, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(d, f))
            except OSError:
                pass
    return total


def open_store(args, quiet=False):
    kdir = args.dir
    if args.no_embed:
        return knowledge.KnowledgeStore(knowledge.db_path(kdir))
    model = knowledge.gateway_embedding_model()
    if not model:
        if not quiet:
            print("(embeddings are off in the gateway: keyword search only)")
        return knowledge.KnowledgeStore(knowledge.db_path(kdir))
    try:
        with urllib.request.urlopen(knowledge.GATEWAY.rstrip("/").rsplit("/v1", 1)[0] + "/health", timeout=3):
            pass
    except OSError:
        if not quiet:
            print("(the gateway is not running at %s: storing without vectors, keyword search only; "
                  "run `kb.py embed` once it runs)" % knowledge.GATEWAY)
        return knowledge.KnowledgeStore(knowledge.db_path(kdir), model_name=model)
    return knowledge.KnowledgeStore(knowledge.db_path(kdir), embed=knowledge.gateway_embedder(), model_name=model)


def fetcher_for(args):
    kdir = args.dir or sources.knowledge_dir()
    return Fetcher(cache_dir=os.path.join(kdir, "cache"), delay=args.delay if args.delay is not None else 1.0,
                   log=say)


def cmd_sources(args):
    configs = sources.load_configs(args.dir)
    store = knowledge.KnowledgeStore(knowledge.db_path(args.dir))
    st = store.stats()["sources"]
    for name in configs:
        d = sources.make(name, configs).describe()
        have = st.get(name)
        print("%-16s %-9s %s" % (name, d["kind"], d["title"]))
        print("%16s license: %s %s" % ("", d["license"], d["license_url"]))
        if d.get("terms"):
            print("%16s terms:   %s" % ("", d["terms"]))
        if have:
            print("%16s stored:  %d pages, %d chunks" % ("", have["pages"], have["chunks"]))
    print("\nadd one: kb.py add NAME --kind web --sitemap URL --allow PREFIX --license \"...\" (docs/KNOWLEDGE.md)")


def _run(args, names, refresh):
    store = open_store(args)
    fetcher = fetcher_for(args)
    configs = sources.load_configs(args.dir)
    totals = []
    for name in names:
        src = sources.make(name, configs)
        if refresh:
            row = store.source_row(name)
            opts = json.loads(row["params"] or "{}") if row else {}
            print("refreshing %s %s" % (name, json.dumps(opts) if opts else ""))
        else:
            pages = list(args.page or [])
            if getattr(args, "core", False):
                pages = list(src.config.get("core_pages") or []) + pages
                if not pages:
                    print("%s has no core pages: use --category or --page" % name)
                    return 2
            opts = {"categories": args.category, "pages": pages or None, "all": args.all}
            if args.depth is not None:
                opts["depth"] = args.depth
            opts["retry"] = args.retry
            print("crawling %s (%s, %s)" % (name, src.title, src.license))
        opts["offline"] = getattr(args, "offline", False)
        opts["delay_given"] = args.delay is not None
        try:
            s = crawler.crawl(store, src, fetcher, opts, limit=args.limit, refresh=refresh, log=say)
        except KeyboardInterrupt:
            return 130
        totals.append(s)
        print("  done in %ss: %d new, %d changed, %d same, %d unchanged (not fetched), %d gone, %d not kept,"
              " %d failed, %d blocked; %d chunks; %d requests, %s downloaded; %d still queued" % (
                  s["seconds"], s["new"], s["changed"], s["same"], s["unchanged"], s["gone"], s["skipped"], s["errors"],
                  s["blocked"], s["chunks"], s["requests"], human(s["downloaded"]), s["left"]))
        if s["processed"]:
            print("  %.2f s per page" % (s["seconds"] / s["processed"]))
        if s["embed_errors"]:
            print("  embeddings failed %d times (%s): keyword search still works; `kb.py embed` retries" % (
                s["embed_errors"], s["embed_error"]))
        grow = getattr(args, "grow", None)
        if grow and not refresh:
            canonical = None
            if hasattr(src, "lastmods"):  # the wiki's real titles, so redirects aren't fetched twice
                canonical = {t.lower(): t for t in (src.title_of(u) for u in src.lastmods(
                    fetcher, say, offline=opts.get("offline"))) if t}
            more = crawler.linked_titles(store, src, min_links=args.min_links, canonical=canonical)[:grow]
            if not more:
                print("  nothing linked from %d pages or more is missing" % args.min_links)
                continue
            print("growing: the %d pages most linked from what is stored (from %d links down to %d)" % (
                len(more), more[0][1], more[-1][1]))
            opts = {"pages": [t for t, _ in more], "offline": opts.get("offline"), "delay_given": opts["delay_given"]}
            try:
                s = crawler.crawl(store, src, fetcher, opts, limit=args.limit, log=say)
            except KeyboardInterrupt:
                return 130
            print("  done in %ss: %d new, %d changed, %d same, %d not kept, %d failed; %d chunks; %d requests, %s" % (
                s["seconds"], s["new"], s["changed"], s["same"], s["skipped"], s["errors"], s["chunks"], s["requests"],
                human(s["downloaded"])))
    return 0


def cmd_crawl(args):
    return _run(args, [args.source], refresh=False)


def cmd_refresh(args):
    store = knowledge.KnowledgeStore(knowledge.db_path(args.dir))
    names = [args.source] if args.source else store.source_names()
    if not names:
        print("nothing crawled yet: kb.py crawl minecraft-wiki")
        return 0
    return _run(args, names, refresh=True)


def cmd_search(args):
    store = open_store(args, quiet=args.json)
    t = time.time()
    ans = store.ask(args.query, k=args.k, sources=args.source and [args.source])
    res = ans["results"]
    took = time.time() - t
    if args.json:
        for r in res:
            r.pop("page_id", None)
        print(json.dumps(ans, indent=2, ensure_ascii=False))
        return 0
    if not res:
        print("nothing found")
    for i, r in enumerate(res, 1):
        text = r["text"] if args.full else (r["text"][:420] + (" ..." if len(r["text"]) > 420 else ""))
        print("%d. %s / %s   (score %.2f%s)" % (i, r["title"], r["section"], r["score"],
                                                 ", meaning %.2f" % r["similarity"] if r["similarity"] else ""))
        print("   " + text.replace("\n", "\n   "))
        print("   %s  [%s, %s]\n" % (r["url"], r["attribution"], r["license"]))
    print("(%d ms; %s: best %.2f, threshold %.2f)" % (took * 1000, "covered" if ans["covered"] else "NOT covered",
                                                     ans["best"], ans["threshold"]))
    return 0


def cmd_learn(args):
    kdir = args.dir or sources.knowledge_dir()
    store = open_store(args)
    conf = learn.settings(kdir)
    src = sources.make(args.source or conf["source"], sources.load_configs(args.dir))
    before = store.ask(args.query, k=3)
    print("before: %s (best %.2f)" % ("covered" if before["covered"] else "not covered", before["best"]))
    out = learn.learn(store, src, fetcher_for(args), args.query, kdir, conf, log=say)
    print("%s in %.1fs, %d requests%s" % (out["status"], out["seconds"], out["requests"],
                                          (": " + out["reason"]) if out.get("reason") else ""))
    for a in out["added"]:
        print("  %-40s %s%s" % (a["title"], a["status"], (" (%d chunks)" % a["chunks"]) if a["chunks"] else ""))
    after = store.ask(args.query, k=3)
    print("after: %s (best %.2f)" % ("covered" if after["covered"] else "not covered", after["best"]))
    for r in after["results"][:2]:
        print("  %s / %s: %s" % (r["title"], r["section"], r["text"][:200].replace("\n", " ")))
    return 0


def cmd_learning(args):
    kdir = args.dir or sources.knowledge_dir()
    if args.state or args.per_hour is not None or args.pages is not None or args.max_mb is not None:
        learn.save_settings(kdir, enabled=None if not args.state else args.state == "on", max_per_hour=args.per_hour,
                            pages_per_learn=args.pages, max_total_mb=args.max_mb)
    conf = learn.settings(kdir)
    print("on-demand learning: %s" % ("on" if conf["enabled"] else "off"))
    for k in ("max_per_hour", "pages_per_learn", "max_total_mb", "retry_after_hours", "index_max_age_hours", "source"):
        print("  %-20s %s" % (k, conf[k]))
    store = knowledge.KnowledgeStore(knowledge.db_path(args.dir))
    rows = store.db.execute("select t, query, status, chunks, seconds from learn_log order by t desc limit 8").fetchall()
    if rows:
        print("last look-ups:")
        for r in rows:
            print("  %s  %-8s %4d chunks %5.1fs  %s" % (time.strftime("%m-%d %H:%M", time.localtime(r["t"])), r["status"],
                                                      r["chunks"] or 0, r["seconds"] or 0, r["query"]))
    return 0


def cmd_stats(args):
    store = knowledge.KnowledgeStore(knowledge.db_path(args.dir), model_name=knowledge.gateway_embedding_model())
    st = store.stats()
    kdir = args.dir or sources.knowledge_dir()
    print("knowledge base %s" % st["path"])
    print("  %d pages, %d chunks, database %s, download cache %s" % (
        st["pages"], st["chunks"], human(st["db_bytes"]), human(dir_size(os.path.join(kdir, "cache")))))
    print("  embedding model: %s" % (st["embedding_model"] or "none (keyword search)"))
    for name, s in st["sources"].items():
        print("  %-16s %5d pages %6d chunks %6d with vectors  %s of text  [%s]" % (
            name, s["pages"], s["chunks"], s["embedded"], human(s["text_chars"]), s["license"]))
        if s["queue"].get("pending") or s["queue"].get("failed"):
            print("  %16s queue: %s" % ("", ", ".join("%s %d" % kv for kv in sorted(s["queue"].items()))))
        if s["params"]:
            shown = {k: (v if not isinstance(v, list) or len(v) <= 8 else v[:5] + ["... %d in all" % len(v)])
                     for k, v in s["params"].items()}
            print("  %16s refresh asks for: %s" % ("", json.dumps(shown)))
        when = s["last_refresh"] or s["last_crawl"]
        if when:
            print("  %16s last fetched: %s" % ("", time.strftime("%Y-%m-%d %H:%M", time.localtime(when))))
    return 0


def cmd_reindex(args):
    store = open_store(args)
    configs = sources.load_configs(args.dir)
    for name in [args.source] if args.source else store.source_names():
        src = sources.make(name, configs)
        c = crawler.reindex(store, src, fetcher_for(args), log=say)
        say("%s: %d changed, %d same, %d not kept, %d not in the cache; %d chunks" % (
            name, c["changed"], c["same"], c["skipped"], c["errors"], c["chunks"]))
    return 0


def cmd_embed(args):
    store = open_store(args)
    if not store.embed:
        print("no embedder: start the gateway with an embeddings provider (docs/GATEWAY.md)")
        return 1
    n = store.embed_missing(progress=lambda t: print("  %d chunks embedded" % t))
    print("embedded %d chunks%s" % (n, (" (errors: %s)" % store.last_embed_error) if store.embed_errors else ""))
    return 0


def cmd_eval(args):
    """How well it answers what players ask: eval_questions.json (or --questions), each with the
    pages that answer it. First / top 3: a right page ranks there. Covered: the store says it has
    the answer; covered but wrong is the costly mistake (she won't listen for the real answer)."""
    store = open_store(args, quiet=True)
    path = args.questions or os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_questions.json")
    with open(path, encoding="utf-8") as f:
        qs = json.load(f)["questions"]
    have = {r[0] for r in store.db.execute("select title from pages")}
    rows, t0 = [], time.time()
    for q in qs:
        ans = store.ask(q["q"], k=5)
        got = [re.sub(r" \(Java [0-9.]+ data\)$", "", r["title"]) for r in ans["results"]]  # minecraft-data pages
        gold = set(q["gold"])
        top = ans["results"][0] if ans["results"] else {}
        rows.append({"topic": q["topic"], "q": q["q"], "first": bool(got[:1] and got[0] in gold),
                     "top3": bool(gold & set(got[:3])), "covered": ans["covered"], "best": round(ans["best"], 3),
                     "got": got[:3], "stored": bool(gold & have), "future": bool(q.get("future")),
                     "status": top.get("status", "")})
    ms = 1000 * (time.time() - t0) / max(1, len(qs))
    cur = [r for r in rows if not r["future"]]
    fut = [r for r in rows if r["future"]]
    def n(key):
        return sum(1 for r in cur if r[key])
    print("%d questions (%d ms each): a right page stored %d, first %d, in the top 3 %d; covered %d (right %d, "
          "wrong %d)" % (len(cur), ms, n("stored"), n("first"), n("top3"), n("covered"),
                          sum(1 for r in cur if r["covered"] and r["top3"]),
                          sum(1 for r in cur if r["covered"] and not r["top3"])))
    if fut:
        print("%d about things after the player's version: %d found and marked %s, %d answered as if current" % (
            len(fut), sum(1 for r in fut if r["first"] and r["status"] == "future"), "future",
            sum(1 for r in fut if r["covered"])))
    if args.verbose:
        for r in rows:
            print("%s %s %-11s %-52s %.2f %s%s" % ("1" if r["first"] else "3" if r["top3"] else "-",
                                                   "C" if r["covered"] else " ", r["topic"], r["q"][:52], r["best"],
                                                   r["got"], "" if r["stored"] else "  (no right page stored)"))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1)
    return 0


def cmd_compact(args):
    store = knowledge.KnowledgeStore(knowledge.db_path(args.dir))
    before = store.stats()["db_bytes"]
    n = store.compact()
    print("%d vectors made 16-bit; database %s -> %s" % (n, human(before), human(store.stats()["db_bytes"])))
    return 0


def cmd_remove(args):
    store = knowledge.KnowledgeStore(knowledge.db_path(args.dir))
    n = store.remove_source(args.source)
    store.vacuum()
    print("removed %s: %d pages" % (args.source, n))
    if args.cache:
        configs = sources.load_configs(args.dir)
        cfg = configs.get(args.source, {})
        url = cfg.get("base") or cfg.get("sitemap") or (cfg.get("urls") or [""])[0]
        host = urllib.parse.urlsplit(url).netloc
        p = os.path.join(args.dir or sources.knowledge_dir(), "cache", host.replace(":", "_")) if host else None
        if p and os.path.isdir(p):
            shutil.rmtree(p)
            print("deleted its download cache %s" % p)
    return 0


def cmd_add(args):
    cfg = {"kind": args.kind, "title": args.title or args.name, "license": args.license,
           "license_url": args.license_url or "", "attribution": args.attribution or args.title or args.name}
    if args.kind == "web":
        if not (args.url or args.sitemap):
            print("a web source needs --url (one or more) or --sitemap")
            return 2
        cfg.update({"urls": args.url or [], "sitemap": args.sitemap or "", "allow": args.allow or []})
    elif args.kind == "local":
        cfg["path"] = os.path.expanduser(args.path or "")
    elif args.kind == "mediawiki":
        cfg.update({"base": args.base, "sitemaps": [args.sitemap] if args.sitemap else []})
    if args.delay is not None:
        cfg["delay"] = args.delay
    sources.save_config(args.name, cfg, args.dir)
    print("added %s to %s; now: kb.py crawl %s --limit 20" % (args.name, sources.sources_file(args.dir), args.name))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="kb.py", description="Kindred Spirit's knowledge base")
    p.add_argument("--dir", help="knowledge folder (default ~/.kindred-spirit/knowledge)")
    p.add_argument("--no-embed", action="store_true", help="don't use the gateway's embeddings")
    p.add_argument("--delay", type=float, help="seconds between requests to one site (default 1)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sources")
    c = sub.add_parser("crawl")
    c.add_argument("source")
    c.add_argument("--limit", type=int, help="fetch at most N pages this time")
    c.add_argument("--category", action="append", help="a wiki category (repeatable)")
    c.add_argument("--page", action="append", help="a page title or URL (repeatable)")
    c.add_argument("--all", action="store_true", help="every page in the sitemap (hours, for a big wiki)")
    c.add_argument("--depth", type=int, help="subcategory depth (default 1)")
    c.add_argument("--retry", action="store_true", help="try pages that failed 3 times again")
    c.add_argument("--offline", action="store_true", help="rebuild from the download cache, no network")
    c.add_argument("--core", action="store_true", help="the source's core pages (what survival players ask about)")
    c.add_argument("--grow", type=int, help="then the N pages the stored pages link to most")
    c.add_argument("--min-links", type=int, default=4, help="--grow: linked from at least this many pages (4)")
    r = sub.add_parser("refresh")
    r.add_argument("source", nargs="?")
    r.add_argument("--limit", type=int)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=5)
    s.add_argument("--source")
    s.add_argument("--json", action="store_true")
    s.add_argument("--full", action="store_true", help="whole chunks, not the first lines")
    ln = sub.add_parser("learn")
    ln.add_argument("query")
    ln.add_argument("--source")
    lg = sub.add_parser("learning")
    lg.add_argument("state", nargs="?", choices=["on", "off"])
    lg.add_argument("--per-hour", type=int)
    lg.add_argument("--pages", type=int)
    lg.add_argument("--max-mb", type=float)
    sub.add_parser("stats")
    ri = sub.add_parser("reindex")
    ri.add_argument("source", nargs="?")
    sub.add_parser("embed")
    sub.add_parser("compact")
    ev = sub.add_parser("eval")
    ev.add_argument("--questions", help="a JSON file like eval_questions.json")
    ev.add_argument("--json", help="write every answer to this file")
    ev.add_argument("-v", "--verbose", action="store_true", help="one line per question")
    rm = sub.add_parser("remove")
    rm.add_argument("source")
    rm.add_argument("--cache", action="store_true", help="also delete its cached downloads")
    a = sub.add_parser("add")
    a.add_argument("name")
    a.add_argument("--kind", choices=["web", "local", "mediawiki"], default="web")
    a.add_argument("--title")
    a.add_argument("--url", action="append")
    a.add_argument("--sitemap")
    a.add_argument("--allow", action="append", help="keep only sitemap URLs starting with this (repeatable)")
    a.add_argument("--path", help="folder, for --kind local")
    a.add_argument("--base", help="wiki address, for --kind mediawiki")
    a.add_argument("--license", required=True, help="the site's license or terms, e.g. 'CC BY-SA 4.0'")
    a.add_argument("--license-url")
    a.add_argument("--attribution")
    args = p.parse_args(argv)
    if args.cmd in ("refresh",):
        args.category = args.page = None
        args.all = args.retry = False
        args.depth = None
    return {"sources": cmd_sources, "crawl": cmd_crawl, "refresh": cmd_refresh, "search": cmd_search,
            "stats": cmd_stats, "embed": cmd_embed, "remove": cmd_remove, "add": cmd_add, "learn": cmd_learn,
            "learning": cmd_learning, "reindex": cmd_reindex, "compact": cmd_compact, "eval": cmd_eval}[args.cmd](args) or 0


if __name__ == "__main__":
    sys.exit(main())
