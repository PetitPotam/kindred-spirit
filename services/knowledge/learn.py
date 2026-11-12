"""Learning on demand: when the knowledge base doesn't cover a question, read the few wiki pages
that answer it, right now, with the crawler's rules (robots.txt, 1 request/second, cache,
license and URL on every chunk, pages already fresh not fetched again).

    learn(store, src, fetcher, "how do I build an iron farm")
      -> {"status": "learned", "added": [{"title": "Tutorial:Iron golem farming", "status": "new",
          "chunks": 31}, ...], "seconds": 4.2, "requests": 4}

Finding the pages: on a wiki whose robots.txt allows its API, the wiki's own search
(list=search). minecraft.wiki's robots.txt disallows api.php and Special:Search, so there the
titles come from its sitemaps (every article and every tutorial, with their last edit time: two
small files, reused for a day) and are ranked here against the question: the page must be about
the question's subject ("iron", "zombie"), the closer its title the better, and tutorials first
when the question is about building or farming.

Bounded so it never runs away (settings.json in the knowledge folder, `kb.py learning`):
  enabled            on/off (default on; KINDRED_KNOWLEDGE_LEARN=0 turns it off)
  max_per_hour       learn calls that may reach the network in an hour (default 20)
  pages_per_learn    pages read for one question (default 3)
  max_total_mb       database + download cache; above it, no more learning (default 1024)
  retry_after_hours  the same question is not looked up again sooner (default 24)
  index_max_age_hours  how long the sitemap title index is reused (default 24)
"""
import json
import os
import re
import time

from . import crawler
from .store import BUILD_WORDS, INTENTS, STOP, page_title_stems, stem, words

DEFAULTS = {"enabled": True, "max_per_hour": 20, "pages_per_learn": 3, "max_total_mb": 1024,
            "retry_after_hours": 24, "index_max_age_hours": 24, "source": "minecraft-wiki"}


def settings_path(kdir):
    return os.path.join(kdir, "settings.json")


def settings(kdir):
    out = dict(DEFAULTS)
    p = settings_path(kdir)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                out.update((json.load(f) or {}).get("learn") or {})
        except (OSError, ValueError):
            pass
    env = os.environ.get("KINDRED_KNOWLEDGE_LEARN")
    if env is not None and env.strip() != "":
        out["enabled"] = env.strip().lower() not in ("0", "off", "false", "no")
    return out


def save_settings(kdir, **changes):
    p = settings_path(kdir)
    cur = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            cur = json.load(f) or {}
    cur.setdefault("learn", {}).update({k: v for k, v in changes.items() if v is not None})
    os.makedirs(kdir, exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2)
    os.replace(p + ".tmp", p)
    return settings(kdir)


def normalize(query):
    return " ".join(sorted({stem(w) for w in words(query) if w not in STOP and len(w) >= 3}))


KIND_WORDS = {stem(w) for trig, _, _ in INTENTS for w in trig} | {stem(w) for w in BUILD_WORDS}
GUIDE = ("tutorial:",)


def rank_titles(query, items, n=3):
    """The pages most likely to answer the question, best first. A page must be about the
    question's subject; tutorials come first for build/farm questions."""
    q_all = {stem(w) for w in words(query) if w not in STOP and len(w) >= 3}
    subject = q_all - KIND_WORDS
    wants_guide = bool(set(words(query)) & BUILD_WORDS)
    scored = []
    for it in items:
        t = page_title_stems(it.title)
        if not t:
            continue
        hit = t & q_all
        subj = t & subject
        if not hit or (subject and not subj):
            continue
        precision = len(hit) / len(t)
        recall = len(subj) / len(subject) if subject else len(hit) / len(q_all)
        score = precision + 2 * recall
        guide = it.title.lower().startswith(GUIDE)
        if guide:
            score += 1.0 if wants_guide else -0.5
        if "/" in it.title:  # subpages ("Tutorial:X/Design 2") after the page itself
            score -= 0.5
        if re.search(r"\b(Edition|Story Mode|Dungeons|Earth|Legends)\b", it.title):
            score -= 1.0
        scored.append((score, -len(it.title), it))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    if not scored:
        return []
    best = scored[0][0]
    return [it for s, _, it in scored[:n] if s >= best - 1.0]


def _disk_mb(store, kdir):
    total = 0
    for suf in ("", "-wal"):
        p = store.path + suf
        if os.path.exists(p):
            total += os.path.getsize(p)
    for d, _, files in os.walk(os.path.join(kdir, "cache")):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(d, f))
            except OSError:
                pass
    return total / 1e6


def learn(store, src, fetcher, query, kdir, conf=None, log=lambda m: None, now=None):
    """Read the pages that answer `query` into the knowledge base. Returns
    {"status": learned | known | nothing | off | capped | full | recent | busy, "added": [...],
     "seconds", "requests", "reason"}."""
    conf = conf or settings(kdir)
    t0 = time.time()
    now = now or t0
    query = (query or "").strip()
    norm = normalize(query)
    out = {"query": query, "added": [], "seconds": 0.0, "requests": 0, "source": src.name}
    if not conf.get("enabled"):
        return dict(out, status="off", reason="on-demand learning is off (kb.py learning on)")
    if not norm:
        return dict(out, status="nothing", reason="no words to look up")
    recent = store.db.execute("select t, status, pages from learn_log where norm = ? and t > ? and status in"
                              " ('learned', 'known', 'nothing') order by t desc limit 1",
                              (norm, now - float(conf["retry_after_hours"]) * 3600)).fetchone()
    if recent:
        return dict(out, status="recent", added=json.loads(recent["pages"] or "[]"),
                    reason="looked up %d minutes ago (%s)" % ((now - recent["t"]) / 60, recent["status"]))
    n_hour = store.db.execute("select count(*) from learn_log where t > ? and status in ('learned', 'known', 'nothing')",
                              (now - 3600,)).fetchone()[0]
    if n_hour >= int(conf["max_per_hour"]):
        return dict(out, status="capped", reason="already %d look-ups in the last hour (max_per_hour)" % n_hour)
    mb = _disk_mb(store, kdir)
    if mb >= float(conf["max_total_mb"]):
        return dict(out, status="full", reason="the knowledge base uses %.0f MB (max_total_mb %s)" % (
            mb, conf["max_total_mb"]))

    if not hasattr(src, "find_pages"):
        return dict(out, status="nothing", reason="%s can't be searched for one question" % src.name)
    req0 = fetcher.requests
    store.upsert_source(src)
    found = src.find_pages(fetcher, query, log, n=10, max_age=float(conf["index_max_age_hours"]) * 3600)
    picks = rank_titles(query, found, n=int(conf["pages_per_learn"]))
    added = []
    for it in picks:
        page = store.page(src.name, it.key)
        if page and it.token and page["token"] == it.token:
            added.append({"title": it.title, "url": it.url, "status": "fresh", "chunks": 0})
            continue
        status, title, n, error = crawler.fetch_one(store, src, fetcher, it)
        added.append({"title": title, "url": it.url, "status": status, "chunks": n,
                      **({"error": error} if error else {})})
        log("  %s: %s%s" % (title, status, (" (%d chunks)" % n) if n else ""))
    got = [a for a in added if a["status"] in ("new", "changed")]
    status = "learned" if got else ("known" if any(a["status"] in ("fresh", "same") for a in added) else "nothing")
    out.update(status=status, added=added, seconds=round(time.time() - t0, 2), requests=fetcher.requests - req0,
               reason="" if picks else "no page about that in %s" % src.title)
    with store.lock:
        store.db.execute("insert into learn_log(t, query, norm, status, pages, chunks, seconds) values (?,?,?,?,?,?,?)",
                         (now, query, norm, status, json.dumps(added), sum(a["chunks"] for a in added),
                          out["seconds"]))
        store.db.commit()
    return out
