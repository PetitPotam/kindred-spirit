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
from . import store as store_mod
from .store import BUILD_WORDS, INTENTS, STOP, page_title_stems, parse_question, stem, words

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
    return " ".join(sorted({stem(w) for w in words(focus(query)) if w not in STOP and len(w) >= 3}))


KIND_WORDS = {stem(w) for trig, _, _ in INTENTS for w in trig} | {stem(w) for w in BUILD_WORDS}
FILLER = {stem(w) for w in store_mod.FILLER}
WHERE = {"where", "find", "found", "level", "layer", "height", "deep", "depth", "spawn", "spawns", "locate"}
GUIDE = ("tutorial:",)
ABOUT_US = re.compile(r"\b(you|your|yourself|my|mine|our|me)\b", re.I)
POLITE = re.compile(r"\b((can|could|would|will) you( please)?( (tell|show|teach) me| explain)?|do you know|"
                    r"(tell|show|teach) me|please)\b", re.I)
ASKING = re.compile(r"\b(how|what|where|which|why|when|can|could|is there|are there|do|does)\b", re.I)


def focus(query):
    """The question in what was said: "That thing ignored me. How do I tame a parrot? Thanks!"
    -> "How do I tame a parrot?". A long message with no question about the world -> ""."""
    q = (query or "").strip()
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", q) if x.strip()]
    if len(sentences) <= 1 and len(words(q)) <= 25:
        return q
    def about_us(x):  # "can you tell me how..." is still a question about the world; "can you tell me?" isn't
        rest = POLITE.sub(" ", x)
        return ABOUT_US.search(rest) or not [w for w in words(rest) if w not in STOP and len(w) >= 3
                                              and not ASKING.fullmatch(w)]
    asks = [x for x in sentences if x.endswith("?") and ASKING.search(x) and not about_us(x)]
    if asks:
        return asks[0]
    asks = [x for x in sentences if ASKING.search(x) and not about_us(x)]
    return asks[0] if asks and len(words(asks[0])) <= 25 else ""


def rank_titles(query, items, n=3):
    """The pages most likely to answer the question, best first. A page must be about the
    question's subject; the last subject word (the thing itself: "door" in "redstone door") counts
    double; tutorials come first for build/farm questions, "X Ore" for where-to-find questions."""
    query = focus(query)
    pq = parse_question(query)
    q_all = pq["terms"] - FILLER
    subject = pq["subject"]
    head = pq["head"]
    wants_guide = bool(set(words(query)) & BUILD_WORDS)
    wants_place = bool(set(words(query)) & WHERE)
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
        if subject:
            recall = (len(subj) + (1 if head in subj else 0)) / (len(subject) + 1)
        else:
            recall = len(hit) / len(q_all)
        score = precision + 2 * recall
        guide = it.title.lower().startswith(GUIDE)
        if guide:
            score += 1.0 if wants_guide else -0.5
        if wants_place and it.title.endswith(" Ore") and subj:
            score += 0.5
        if "/" in it.title:  # subpages ("Tutorial:X/Design 2") after the page itself
            score -= 0.5
        if re.search(r"\b(Edition|Story Mode|Dungeons|Earth|Legends)\b", it.title) or \
                re.match(r"^(\d|Pet |Monsterized )", it.title) or "!" in it.title:
            score -= 1.0  # other games, April Fools pets, Earth adventures
        scored.append((score, -len(it.title), it))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    if not scored:
        return []
    best = scored[0][0]
    picks = [it for s, _, it in scored[:n] if s >= best - 0.5]
    # a question about two things ("a librarian with mending"): the best page for what is still missing
    missing = subject - {w for it in picks for w in page_title_stems(it.title)}
    for s, _, it in scored:
        if len(picks) >= n or not missing:
            break
        got = page_title_stems(it.title) & missing
        if got and it not in picks and s >= best - 1.5:
            picks.append(it)
            missing -= got
    return picks


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
        return dict(out, status="nothing", reason="no question about the world in it" if query else "no words to look up")
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
    found = src.find_pages(fetcher, focus(query), log, n=10, max_age=float(conf["index_max_age_hours"]) * 3600)
    want = int(conf["pages_per_learn"])
    picks = rank_titles(query, found, n=want + 3)
    added, useful, fetched = [], 0, 0
    for it in picks:
        # enough pages that answer, or enough asked of the wiki for one question
        if useful >= want or fetched >= want + 2:
            break
        page = store.page(src.name, it.key)
        if page and it.token and page["token"] == it.token:
            added.append({"title": it.title, "url": it.url, "status": "fresh", "chunks": 0})
            useful += 1
            continue
        status, title, n, error = crawler.fetch_one(store, src, fetcher, it)
        fetched += 1
        if status in ("new", "changed", "same"):
            useful += 1
        added.append({"title": title, "url": it.url, "status": status, "chunks": n,
                      **({"error": error} if error else {})})
        log("  %s: %s%s" % (title, ("not kept (%s)" % error) if status == "skipped" else status,
                            (" (%d chunks)" % n) if n else ""))
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
