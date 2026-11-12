"""The knowledge base: one SQLite file of pages cut into chunks, searchable by words and meaning.

Kept apart from the companion's own memories (services/memory_store.py): this is what the
world says about Minecraft, those are what she lived. Same retrieval idea as the memories,
tuned for reference text instead of personal moments:

  keywords   SQLite FTS5 (BM25, Porter stemming so "pistons" finds "piston"); the title counts
             most, then the section name, then the text
  meaning    cosine similarity of embeddings from the gateway (optional: without an embedding
             service, keyword search still works)
  title      the page is *about* what was asked ("how do I make a piston" -> the Piston page)
  intent     the section fits the kind of question (make -> Crafting/Obtaining, spawn ->
             Spawning, breed -> Breeding, build -> tutorials), and a recipe chunk whose output is
             the thing asked about

No recency or importance: a recipe does not fade. Every chunk keeps its source URL, license
and attribution, so whatever the companion says from it can say where it came from.
Standard library only; numpy is used if present (faster cosine).
"""
import hashlib
import json
import math
import os
import re
import sqlite3
import struct
import threading
import time
from operator import mul

try:
    import numpy as np
except ImportError:
    np = None

from . import textify

SCHEMA = """
pragma journal_mode = wal;
create table if not exists sources (
  name text primary key, kind text, title text, license text, license_url text, attribution text,
  config text default '{}', params text default '{}', created real, last_crawl real, last_refresh real);
create table if not exists pages (
  id integer primary key, source text not null, key text not null, title text, url text, token text, hash text,
  meta text default '{}', data text default '{}', fetched real, checked real, unique(source, key));
create table if not exists chunks (
  id integer primary key, page_id integer not null, source text not null, ord integer, title text, section text,
  text text not null, hash text, data text, emb blob, emb_model text);
create index if not exists chunks_page on chunks(page_id);
create virtual table if not exists chunks_fts using fts5(title, section, text, content='chunks', content_rowid='id',
  tokenize='porter unicode61 remove_diacritics 2');
create trigger if not exists chunks_ai after insert on chunks begin
  insert into chunks_fts(rowid, title, section, text) values (new.id, new.title, new.section, new.text); end;
create trigger if not exists chunks_ad after delete on chunks begin
  insert into chunks_fts(chunks_fts, rowid, title, section, text) values ('delete', old.id, old.title, old.section, old.text); end;
create table if not exists queue (
  source text not null, key text not null, title text, url text, token text, status text default 'pending',
  error text, attempts integer default 0, added real, primary key(source, key));
create table if not exists meta (key text primary key, value text);
create table if not exists learn_log (
  id integer primary key, t real, query text, norm text, status text, pages text, chunks integer, seconds real);
create index if not exists learn_log_t on learn_log(t);
"""

STOP = set("a an of to in on at by as or be "
           "the and you your for are was with this that what where when how can could would should have has had "
           "not but all any our out too its it's i'm there here they them then than just about from into please "
           "pip me my does doing did why which who whom get got minecraft much many some way want need know tell "
           "able thing things is do something anything put give lot one work works working".split())

# kind of question -> words in the section name that answer it, and words to add to the keyword
# search (a question says "make", the page says "Crafting")
INTENTS = [
    ({"make", "craft", "crafted", "crafting", "recipe", "recipes", "made"},
     ("crafting", "obtaining", "recipe"), ("crafting", "recipe")),
    ({"spawn", "spawns", "spawning", "find", "found", "where", "locate", "live", "lives", "generate", "generates"},
     ("spawning", "spawn", "generation", "obtaining", "location", "occurrence", "finding"), ("spawn", "generation")),
    ({"breed", "breeding", "tame", "taming", "feed", "baby", "babies"}, ("breeding", "taming", "feeding", "food"),
     ("breeding", "taming")),
    ({"drop", "drops", "loot"}, ("drops", "loot"), ("drops",)),
    ({"smelt", "smelting", "cook", "cooking", "furnace"}, ("smelting", "cooking", "obtaining"), ("smelting",)),
    ({"enchant", "enchanting", "enchantment", "enchantments"}, ("enchant",), ("enchantment",)),
    ({"brew", "brewing", "potion", "potions"}, ("brewing", "potion"), ("brewing",)),
    ({"use", "used", "uses", "usage", "useful"}, ("usage", "uses"), ("usage",)),
    ({"grow", "growing", "grows", "plant", "planting", "harvest", "faster"}, ("farming", "growth", "growing", "usage"),
     ("farming", "growth")),
    ({"mine", "mining", "break", "breaking", "pickaxe", "tool"}, ("breaking", "mining", "obtaining"), ("breaking",)),
    ({"health", "hearts", "hp", "armor", "speed", "hitbox", "tall", "big", "stats"}, ("facts",), ("health",)),
    ({"damage", "attack", "attacks", "strong", "dangerous", "hits", "hit"}, ("facts", "attack", "combat"), ("damage",)),
]
BUILD_WORDS = {"build", "building", "farm", "farms", "design", "designs", "automatic", "tutorial", "guide",
               "contraption", "machine", "base", "house"}
# title namespaces that are guides
GUIDE_PREFIXES = ("tutorial:",)


HALF = b"\x01"  # a vector stored as 16-bit floats starts with this byte (an odd length; 32-bit ones are even)


# words that say how, not what: "a simple wheat farm, step by step" is about wheat
FILLER = {"simple", "simplest", "easy", "easiest", "step", "steps", "best", "good", "better", "quick", "quickly",
          "fast", "cheap", "small", "big", "little", "basic", "efficient", "proper", "properly", "really",
          "actually", "first", "new", "nice", "cool", "exactly", "early", "level", "levels", "layer", "height",
          "deep", "depth", "nearby", "near", "around", "here", "still", "also", "even", "every", "kind", "type",
          "types", "possible", "possibly", "safe", "safely", "guys", "anyone", "somebody", "dude", "okay", "ok",
          "hey", "start", "started", "starting", "ever", "much", "lots"}
# what one does to the thing, not the thing: "stop phantoms", "open a vault", "Tutorial:Defeating
# trial chambers" (left out of the question's subject and of guide titles alike)
ACTIONS = {"stop", "open", "cure", "curing", "beat", "beating", "defeat", "defeating", "kill", "killing", "fight",
           "fighting", "combine", "combining", "upgrade", "upgrading", "start", "starting", "explore", "exploring",
           "conquer", "conquering", "survive", "surviving", "gather", "gathering", "obtain", "obtaining", "avoid",
           "avoiding", "protect", "protecting", "fix", "repair", "light", "lighting", "ride", "riding", "activate",
           "summon", "summoning", "trap", "trapping", "manage", "managing", "acquire", "acquiring", "getting"}
SYNONYMS = {"xp": "experience", "exp": "experience", "enderpearl": "ender pearl", "gp": "gunpowder"}
PREPOSITIONS = {"with", "for", "of", "from", "using", "without", "in", "on", "at", "near", "into"}


def _pack(vec):
    """Vectors are kept as 16-bit floats: half the size, and cosine rankings don't change
    (unit vectors, 384 numbers each: about 3 decimals are enough)."""
    return HALF + struct.pack("<%de" % len(vec), *vec)


def _unpack(blob):
    if not blob:
        return None
    if len(blob) % 2:
        return list(struct.unpack("<%de" % ((len(blob) - 1) // 2), blob[1:]))
    return list(struct.unpack("<%df" % (len(blob) // 4), blob))


def _np_vec(blob):
    return np.frombuffer(blob[1:], dtype="<f2") if len(blob) % 2 else np.frombuffer(blob, dtype="<f4")


def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def words(text):
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def stem(w):
    """A tiny stemmer for matching titles to questions, the same on both sides: zombies -> zombie,
    berries/berry -> berri, farming -> farm, crafted -> craft, trading/trade -> trad, endermen ->
    enderman (speed, breed stay)."""
    if len(w) > 5 and w.endswith("men"):
        w = w[:-3] + "man"
    if len(w) > 4 and w.endswith("ies"):
        w = w[:-1]
    elif len(w) > 2 and w.endswith("y") and w[-2] not in "aeiou":
        w = w[:-1] + "ie"
    elif len(w) > 6 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) > 5 and w.endswith("ed") and not w.endswith("eed"):
        w = w[:-2]
    elif len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        w = w[:-1]
    if len(w) > 4 and w.endswith("e") and not w.endswith("ee"):
        w = w[:-1]  # trade / trading, slime / slimes: the same either way
    return w


def stems(text):
    return {stem(w) for w in words(text)}


def fts_query(text, extra=()):
    ws = [w for w in re.findall(r"[a-z0-9]{2,}", (text or "").lower()) if w not in STOP and (len(w) >= 3 or w.isdigit())]
    ws += list(extra)
    seen, out = set(), []
    for w in ws:
        if w not in seen:
            seen.add(w)
            out.append('"%s"' % w)
    return " OR ".join(out[:16])


def _alias_ok(name, title):
    """A bold name in the first paragraph counts if it shares a word with the title ("comparator" for
    Redstone Comparator) or is a short abbreviation ("xp" for Experience), not the materials a page
    lists in bold ("copper" on the Helmet page)."""
    return bool(name) and (bool(name & title) or (len(name) == 1 and len(next(iter(name))) <= 3))


def _name_score(t, q_stems, subject, core=None):
    """How well a page name answers: 1.0 = it is the thing asked ("Potion of Night Vision"), 0.95 =
    the thing itself without what it's for ("Tutorial:Creeper farming" for a creeper farm for
    gunpowder), 0.85 = part of it ("The Nether" for a nether portal), 0.4 = most of its words."""
    if t <= q_stems:
        if not subject or subject <= t:
            return 1.0
        return 0.95 if core and core <= t else 0.85
    return 0.4 if len(t & q_stems) >= max(1, len(t) // 2 + 1) else 0.0


def page_title_stems(title):
    t = title.lower()
    guide = False
    for p in GUIDE_PREFIXES:
        if t.startswith(p):
            t = t[len(p):]
            guide = True
    t = re.sub(r"\(.*?\)", "", t)  # "Piston (Java Edition)" -> about pistons
    out = {stem(w) for w in words(t) if w not in STOP}
    if guide:  # "Tutorial:Defeating trial chambers" is about trial chambers
        out = (out - ACTION_STEMS) or out
    return out


def synonyms(text):
    return re.sub(r"[a-z]+", lambda m: SYNONYMS.get(m.group(0), m.group(0)), (text or "").lower())


def parse_question(query):
    """What a question is about: {"terms": stems of its words, "subject": the things it names
    (not the kind of question, how, or what one does to it), "core": the thing itself (before a
    preposition: "a creeper farm *for gunpowder*", "a librarian *with mending*"), "head": its last word}."""
    q = synonyms(query)
    ws = [re.sub(r"'s?$", "", w) for w in words(q)]  # "what's", "player's"
    terms = {stem(w) for w in ws if w not in STOP and len(w) >= 3}
    subject, core, head, closed = [], [], None, False
    for w in ws:
        st = stem(w)
        if w in PREPOSITIONS and core:
            closed = True
            continue
        if w in STOP or len(w) < 3 or st in KIND_STEMS or w in FILLER or w in ACTIONS or st in ACTION_STEMS:
            continue
        subject.append(st)
        if not closed:
            core.append(st)
            head = st
    if head is None and subject:
        head = subject[-1]
    return {"words": set(ws), "stems": {stem(w) for w in ws}, "terms": terms, "subject": set(subject),
            "core": set(core) or set(subject), "head": head, "text": q}


class KnowledgeStore:
    """embed(texts, query=False) -> list of vectors, or None/raise when no embedder is available."""

    def __init__(self, path, embed=None, model_name=""):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.path = path
        self.embed = embed
        self.model_name = model_name
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()
        self._matrix = None
        self.embed_errors = 0
        self.last_embed_error = ""

    def close(self):
        self.db.close()

    # ------------------------------------------------------------------ bookkeeping

    def _bump(self):
        self.db.execute("insert into meta(key, value) values ('generation', '1') on conflict(key) do update set "
                        "value = cast(value as integer) + 1")

    def generation(self):
        r = self.db.execute("select value from meta where key = 'generation'").fetchone()
        return int(r[0]) if r else 0

    def upsert_source(self, src, params=None, crawled=False, refreshed=False):
        d = src.describe()
        now = time.time()
        with self.lock:
            self.db.execute(
                "insert into sources(name, kind, title, license, license_url, attribution, config, params, created)"
                " values (?,?,?,?,?,?,?,?,?) on conflict(name) do update set kind=excluded.kind, title=excluded.title,"
                " license=excluded.license, license_url=excluded.license_url, attribution=excluded.attribution,"
                " config=excluded.config",
                (src.name, d["kind"], d["title"], d["license"], d["license_url"], d["attribution"],
                 json.dumps(src.config), json.dumps(params or {}), now))
            if params:
                old = self.source_row(src.name)
                merged = self._merge_params(json.loads(old["params"] or "{}") if old else {}, params)
                self.db.execute("update sources set params = ? where name = ?", (json.dumps(merged), src.name))
            if crawled:
                self.db.execute("update sources set last_crawl = ? where name = ?", (now, src.name))
            if refreshed:
                self.db.execute("update sources set last_refresh = ? where name = ?", (now, src.name))
            self.db.commit()

    @staticmethod
    def _merge_params(old, new):
        """What refresh should ask for again: the union of everything crawled so far."""
        out = dict(old)
        for k, v in new.items():
            if isinstance(v, list):
                out[k] = sorted(set(out.get(k) or []) | set(v))
            else:
                out[k] = v
        return out

    def prune_params(self, name):
        """What refresh asks for again: only pages that were kept (or are still queued), under the
        name they were stored by; not redirects, pages left out by the rules, or ones gone."""
        row = self.source_row(name)
        params = json.loads(row["params"] or "{}") if row else {}
        if not params.get("pages"):
            return 0
        keep = {r[0] for r in self.db.execute("select key from pages where source = ?", (name,))}
        keep |= {r[0] for r in self.db.execute("select key from queue where source = ? and status = 'pending'", (name,))}
        before = len(params["pages"])
        params["pages"] = sorted(p for p in params["pages"] if p in keep)
        with self.lock:
            self.db.execute("update sources set params = ? where name = ?", (json.dumps(params), name))
            self.db.commit()
        return before - len(params["pages"])

    def source_row(self, name):
        return self.db.execute("select * from sources where name = ?", (name,)).fetchone()

    def source_names(self):
        return [r[0] for r in self.db.execute("select name from sources order by name")]

    # ------------------------------------------------------------------ pages

    def page(self, source, key):
        r = self.db.execute("select * from pages where source = ? and key = ?", (source, key)).fetchone()
        return dict(r) if r else None

    def tokens(self, source):
        return {r[0]: r[1] for r in self.db.execute("select key, token from pages where source = ?", (source,))}

    def touch_page(self, source, key, token=None):
        with self.lock:
            self.db.execute("update pages set checked = ?, token = coalesce(?, token) where source = ? and key = ?",
                            (time.time(), token, source, key))
            self.db.commit()

    def put_document(self, src, doc, max_chars=1200):
        """Store (or update) a fetched document. Returns ("new" | "changed" | "same", chunks)."""
        now = time.time()
        old = self.page(src.name, doc.key)
        h = doc.hash
        if old and old["hash"] == h:
            with self.lock:
                self.db.execute("update pages set token = ?, checked = ?, meta = ? where id = ?",
                                (doc.token, now, json.dumps(doc.meta), old["id"]))
                self.db.commit()
            return "same", 0
        chunks = textify.chunk(doc.sections, max_chars=max_chars)
        reuse = {}
        if old:  # unchanged chunks keep their vectors: no need to ask the embedder again
            for r in self.db.execute("select hash, emb, emb_model from chunks where page_id = ? and emb is not null",
                                     (old["id"],)):
                if r["emb_model"] == self.model_name:
                    reuse[r["hash"]] = r["emb"]
        with self.lock:
            if old:
                pid = old["id"]
                self.db.execute("delete from chunks where page_id = ?", (pid,))
                self.db.execute("update pages set title=?, url=?, token=?, hash=?, meta=?, data=?, fetched=?, checked=?"
                                " where id = ?", (doc.title, doc.url, doc.token, h, json.dumps(doc.meta),
                                                  json.dumps(doc.data), now, now, pid))
            else:
                pid = self.db.execute(
                    "insert into pages(source, key, title, url, token, hash, meta, data, fetched, checked)"
                    " values (?,?,?,?,?,?,?,?,?,?)", (src.name, doc.key, doc.title, doc.url, doc.token, h,
                                                      json.dumps(doc.meta), json.dumps(doc.data), now, now)).lastrowid
            for i, c in enumerate(chunks):
                ch = _chunk_hash(doc.title, c)
                emb = reuse.get(ch)
                self.db.execute("insert into chunks(page_id, source, ord, title, section, text, hash, data, emb, emb_model)"
                                " values (?,?,?,?,?,?,?,?,?,?)",
                                (pid, src.name, i, doc.title, c["section"], c["text"], ch,
                                 json.dumps(c["data"]) if c.get("data") else None, emb,
                                 self.model_name if emb else None))
            self._bump()
            self.db.commit()
        self.embed_page(pid)
        return ("changed" if old else "new"), len(chunks)

    def delete_page(self, source, key):
        with self.lock:
            r = self.db.execute("select id from pages where source = ? and key = ?", (source, key)).fetchone()
            if not r:
                return False
            self.db.execute("delete from chunks where page_id = ?", (r[0],))
            self.db.execute("delete from pages where id = ?", (r[0],))
            self._bump()
            self.db.commit()
            return True

    def remove_source(self, name):
        with self.lock:
            n = self.db.execute("select count(*) from pages where source = ?", (name,)).fetchone()[0]
            self.db.execute("delete from chunks where source = ?", (name,))
            self.db.execute("delete from pages where source = ?", (name,))
            self.db.execute("delete from queue where source = ?", (name,))
            self.db.execute("delete from sources where name = ?", (name,))
            self._bump()
            self.db.commit()
        return n

    def compact(self):
        """Older 32-bit vectors -> 16-bit, then vacuum. Returns how many vectors were rewritten."""
        n = 0
        with self.lock:
            rows = self.db.execute("select id, emb from chunks where emb is not null and length(emb) % 2 = 0").fetchall()
            for r in rows:
                self.db.execute("update chunks set emb = ? where id = ?", (_pack(_unpack(r["emb"])), r["id"]))
                n += 1
            if n:
                self._bump()
            self.db.commit()
        self.vacuum()
        return n

    def vacuum(self):
        with self.lock:
            self.db.execute("insert into chunks_fts(chunks_fts) values ('optimize')")
            self.db.commit()
            self.db.execute("vacuum")
            self.db.execute("pragma wal_checkpoint(truncate)")  # give the write-ahead log's space back too

    # ------------------------------------------------------------------ the crawl queue (resume after a stop)

    def enqueue(self, source, items):
        """Remember what to fetch. A page already stored with the same token is not queued
        (unchanged since last time). Returns (queued, unchanged)."""
        stored = self.tokens(source)
        queued = unchanged = 0
        now = time.time()
        with self.lock:
            for it in items:
                if it.token and stored.get(it.key) == it.token:
                    unchanged += 1
                    self.db.execute("delete from queue where source = ? and key = ? and status != 'pending'",
                                    (source, it.key))
                    continue
                cur = self.db.execute("select status, token from queue where source = ? and key = ?",
                                      (source, it.key)).fetchone()
                if cur and cur["status"] == "pending":
                    self.db.execute("update queue set token = coalesce(?, token), url = ? where source = ? and key = ?",
                                    (it.token, it.url, source, it.key))
                elif cur and cur["status"] == "done" and it.token is None:
                    # no way to know if it changed: ask again (a conditional GET is cheap)
                    self.db.execute("update queue set status='pending', added=? where source=? and key=?",
                                    (now, source, it.key))
                    queued += 1
                    continue
                elif cur and cur["status"] == "failed" and cur["token"] == it.token:
                    continue  # failed for good with this version: leave it (kb.py crawl --retry)
                else:
                    self.db.execute("insert into queue(source, key, title, url, token, status, attempts, added)"
                                    " values (?,?,?,?,?,'pending',0,?) on conflict(source, key) do update set"
                                    " title=excluded.title, url=excluded.url, token=excluded.token, status='pending',"
                                    " attempts=0, error=null, added=excluded.added",
                                    (source, it.key, it.title, it.url, it.token, now))
                queued += 1
            self.db.commit()
        return queued, unchanged

    def pending(self, source, limit=None):
        sql = "select * from queue where source = ? and status = 'pending' order by added, rowid"
        args = [source]
        if limit:
            sql += " limit ?"
            args.append(int(limit))
        return [dict(r) for r in self.db.execute(sql, args)]

    def mark(self, source, key, status, error=None):
        with self.lock:
            if status == "error":
                self.db.execute("update queue set attempts = attempts + 1, error = ?, status = case when attempts + 1"
                                " >= 3 then 'failed' else 'pending' end where source = ? and key = ?",
                                (error, source, key))
            else:
                self.db.execute("update queue set status = ?, error = ? where source = ? and key = ?",
                                (status, error, source, key))
            self.db.commit()

    def retry_failed(self, source):
        with self.lock:
            n = self.db.execute("update queue set status='pending', attempts=0 where source=? and status='failed'",
                                (source,)).rowcount
            self.db.commit()
        return n

    def queue_counts(self, source):
        return {r[0]: r[1] for r in self.db.execute("select status, count(*) from queue where source = ? group by status",
                                                     (source,))}

    # ------------------------------------------------------------------ embeddings

    def _vectors(self, texts, query=False):
        if not self.embed or not texts:
            return None
        try:
            vecs = self.embed(texts, query)
        except Exception as exc:  # embeddings are a bonus: keyword search still works
            self.embed_errors += 1
            self.last_embed_error = str(exc)[:200]
            return None
        if not vecs or len(vecs) != len(texts):
            return None
        return [_norm(v) for v in vecs]

    def embed_page(self, page_id, batch=32):
        rows = self.db.execute("select id, title, section, text from chunks where page_id = ? and"
                               " (emb is null or emb_model != ?)", (page_id, self.model_name)).fetchall()
        return self._embed_rows(rows, batch)

    def _embed_rows(self, rows, batch=32):
        if not self.embed or not rows:
            return 0
        done = 0
        for i in range(0, len(rows), batch):
            part = rows[i:i + batch]
            vecs = self._vectors([embed_text(r["title"], r["section"], r["text"]) for r in part])
            if not vecs:
                return done
            with self.lock:
                self.db.executemany("update chunks set emb = ?, emb_model = ? where id = ?",
                                    [(_pack(v), self.model_name, r["id"]) for r, v in zip(part, vecs)])
                self._bump()
                self.db.commit()
            done += len(part)
        return done

    def embed_missing(self, limit=None, batch=32, progress=None):
        """Give vectors to chunks that have none (or another model's)."""
        if not self.embed:
            return 0
        total = 0
        while True:
            rows = self.db.execute("select id, title, section, text from chunks where emb is null or emb_model != ?"
                                   " limit ?", (self.model_name, batch * 8)).fetchall()
            if not rows:
                return total
            n = self._embed_rows(rows, batch)
            total += n
            if progress:
                progress(total)
            if n < len(rows) or (limit and total >= limit):
                return total

    def _load_matrix(self):
        gen = self.generation()
        if self._matrix and self._matrix[0] == gen and self._matrix[1] == self.model_name:
            return self._matrix[2], self._matrix[3]
        rows = self.db.execute("select id, emb, page_id from chunks where emb is not null and emb_model = ?",
                               (self.model_name,)).fetchall()
        ids = [r[0] for r in rows]
        if np is not None and rows:
            mat = np.array([_np_vec(r[1]) for r in rows], dtype=np.float32)
        else:
            mat = [_unpack(r[1]) for r in rows]
            # without numpy, a large store is searched page by page first (see _pure_sims)
            pages = {}
            for i, r in enumerate(rows):
                pages.setdefault(r[2], []).append(i)
            cents = []
            for pid, idx in pages.items():
                c = [sum(col) for col in zip(*(mat[i] for i in idx))]
                cents.append((pid, _norm(c)))
            self._pure = {"pages": pages, "centroids": cents, "index": {cid: i for i, cid in enumerate(ids)}}
        self._matrix = (gen, self.model_name, ids, mat)
        return ids, mat

    # without numpy (the gateway's own Python may not have it): plain Python cosine. Up to
    # PURE_FULL_SCAN chunks every vector is compared; above it, the pages are ranked first by their
    # mean vector and only the chunks of the PURE_PAGES nearest pages (and the keyword hits) are
    # compared: ~250 ms -> ~90 ms per question at 19,000 chunks, the same answers on the eval set.
    PURE_FULL_SCAN = 4000
    PURE_PAGES = 60

    def _pure_sims(self, ids, mat, qv, also=()):
        if len(ids) <= self.PURE_FULL_SCAN:
            pick = range(len(ids))
        else:
            pure = self._pure
            near = sorted(((sum(map(mul, c, qv)), pid) for pid, c in pure["centroids"]), reverse=True)[:self.PURE_PAGES]
            pick = {i for _, pid in near for i in pure["pages"][pid]}
            pick |= {pure["index"][c] for c in also if c in pure["index"]}
        scored = sorted(((sum(map(mul, mat[i], qv)), ids[i]) for i in pick), reverse=True)[:300]
        return {cid: sc for sc, cid in scored}

    # ------------------------------------------------------------------ search

    def search(self, query, k=5, sources=None, per_page=2, min_score=0.0):
        """The chunks that best answer `query`, best first:
        [{title, section, text, url, source, license, license_url, attribution, score, data, ...}]"""
        query = (query or "").strip()
        if not query:
            return []
        with self.lock:
            return self._search(query, k, sources, per_page, min_score)

    def ask(self, query, k=5, sources=None, per_page=2):
        """search() plus whether the knowledge base really covers the question:
        {"results": [...], "best": score, "covered": bool, "threshold": COVERED_SCORE}.
        Covered = the best chunk is about everything the question names (all its subject words,
        e.g. "iron" and "golem"), scores at least COVERED_SCORE, and, for a build/farm question,
        one of the top results is a guide (a wiki tutorial or a guide source)."""
        res = self.search(query, k=k, sources=sources, per_page=per_page)
        return dict(coverage(query, res), results=res)

    def _search(self, query, k, sources, per_page, min_score):
        pq = parse_question(query)
        q_stems, q_words, q_terms = pq["stems"], pq["words"], pq["terms"]
        intents = [targets for trig, targets, _ in INTENTS if q_words & trig]
        expand = [w for trig, _, more in INTENTS if q_words & trig for w in more]
        wants_guide = bool(q_words & BUILD_WORDS)
        crafting = bool(q_words & INTENTS[0][0])
        # what the question is about, without the words that only say what kind of question it is,
        # how, or what one does to it
        subject, core = pq["subject"], pq["core"]
        kw = {}
        fq = fts_query(pq["text"], expand)
        if fq:
            try:
                hits = self.db.execute("select rowid, bm25(chunks_fts, 6.0, 2.0, 1.0) as b from chunks_fts where "
                                       "chunks_fts match ? order by b limit 300", (fq,)).fetchall()
            except sqlite3.OperationalError:
                hits = []
            if hits:
                best = -hits[0][1] or 1.0
                for rid, b in hits:
                    kw[rid] = max(0.0, -b) / best
        sims = {}
        qv = None
        if self.embed and self.model_name:
            ids, mat = self._load_matrix()
            if ids:
                v = self._vectors([query], query=True)
                qv = v[0] if v else None
            if qv:
                if np is not None:
                    s = mat @ np.array(qv, dtype=np.float32)
                    top = np.argsort(-s)[:300]
                    sims = {ids[i]: float(s[i]) for i in top}
                else:
                    sims = self._pure_sims(ids, mat, qv, also=kw)
        cand = set(kw) | set(sims)
        if not cand:
            return []
        rows = []
        cl = list(cand)
        for i in range(0, len(cl), 500):
            part = cl[i:i + 500]
            rows += self.db.execute(
                "select c.id, c.page_id, c.source, c.title, c.section, c.text, c.data, p.url, p.meta, p.fetched,"
                " s.license, s.license_url, s.attribution, s.kind from chunks c join pages p on p.id = c.page_id"
                " left join sources s on s.name = c.source where c.id in (%s)" % ",".join("?" * len(part)),
                part).fetchall()
        if sources:
            rows = [r for r in rows if r["source"] in set(sources)]
        out = []
        names_cache = {}
        for r in rows:
            meta = json.loads(r["meta"] or "{}")
            t_stems = page_title_stems(r["title"])
            # the page's own names count too ("Redstone Comparator", or simply "comparator")
            if r["page_id"] not in names_cache:
                names = [t_stems] + [n for n in ({stem(w) for w in words(a) if w not in STOP}
                                                  for a in meta.get("aliases") or []) if _alias_ok(n, t_stems)]
                names_cache[r["page_id"]] = max(((_name_score(n, q_stems, subject, core), n) for n in names if n),
                                                key=lambda x: x[0], default=(0.0, t_stems))
            title, best_name = names_cache[r["page_id"]]
            have = stems("%s %s %s" % (r["title"], r["section"], r["text"]))
            about = bool(title) or not subject or bool(subject & have)
            covers = (len(subject & have) / len(subject)) if subject else 1.0
            # the subject is what this page or section is about, not a word in passing
            heading = not subject or subject <= stems("%s %s" % (r["title"], r["section"]))
            titled = bool(core) and core <= best_name  # "Tutorial:Iron golem farming" for an iron golem farm
            guide = r["title"].lower().startswith(GUIDE_PREFIXES) or (r["kind"] or "") in ("web", "local")
            # "Smiling Creeper" for a creeper question: a different thing with a similar name
            named_like = bool(best_name & subject) and not best_name <= q_stems and not guide
            sec = (r["section"] or "").lower()
            intent = 1.0 if any(any(t in sec for t in targets) for targets in intents) else 0.0
            if wants_guide and r["title"].lower().startswith(GUIDE_PREFIXES):
                intent = max(intent, 0.8)
            data = json.loads(r["data"]) if r["data"] else None
            recipe = 0.0
            if data and data.get("recipes") and crafting:
                for rec in data["recipes"]:
                    o = page_title_stems(rec.get("output", ""))
                    if o and o <= q_stems:
                        recipe = 1.0
            if not about:  # a Crafting section about something else is no answer to "how do I make X"
                intent = recipe = 0.0
            sim = sims.get(r["id"], 0.0)
            k_ = kw.get(r["id"], 0.0)
            if k_ and q_terms:  # BM25 relative to the best hit, tempered by how much of the question is covered
                k_ = 0.5 * k_ + 0.5 * len(q_terms & have) / len(q_terms)
            if qv:
                score = 0.4 * max(0.0, sim) + 0.2 * k_ + 0.15 * title + 0.15 * intent + 0.1 * recipe
            else:
                score = 0.4 * k_ + 0.25 * title + 0.25 * intent + 0.1 * recipe
            # how things worked in an older version, things added after the player's version, removed
            # or April Fools things: still searchable (she can say it isn't in her world), but current
            # pages come first, and only a current page counts as an answer (else learn the current one).
            # Asked about that very thing (the Happy Ghast), its page still comes first, marked.
            status = page_status(meta, r["title"], r["text"])
            weight = STATUS_WEIGHT.get(status, 1.0)
            if title >= 1.0 and status in ("future", "removed", "other-edition"):
                weight = max(weight, 0.85)
            score *= weight
            if score < min_score:
                continue
            out.append({"id": r["id"], "title": r["title"], "section": r["section"], "text": r["text"],
                        "url": r["url"], "source": r["source"], "license": r["license"],
                        "license_url": r["license_url"], "attribution": r["attribution"],
                        "edition": meta.get("edition", ""), "fetched": r["fetched"], "data": data,
                        "score": round(score, 4), "similarity": round(sim, 4), "keywords": round(k_, 4),
                        "about": about, "covers": round(covers, 3), "title_match": title, "named_like": named_like,
                        "in_heading": heading, "title_subject": titled,
                        "name_covers": sorted(best_name & subject),
                        "guide": guide, "page_id": r["page_id"], "status": status,
                        "outdated": status != "current", "since": meta.get("since_java")})
        out.sort(key=lambda d: d["score"], reverse=True)
        per, final = {}, []
        for d in out:
            if per.get(d["page_id"], 0) >= per_page:
                continue
            per[d["page_id"]] = per.get(d["page_id"], 0) + 1
            final.append(d)
            if len(final) >= k:
                break
        return final

    # ------------------------------------------------------------------ whole sections (for step-by-step guides)

    def section(self, chunk_id=None, page=None, name=None, start=0, max_chars=4500):
        """The passages of one section of a page, in order, from passage `start` of that section, up to
        `max_chars`: {title, section, text, part, parts, more, next_start, outline, url, ...}.
        Give a chunk id (from a search result), or a page title and a section name (or a part of it,
        "Step two"; the page's first section if none)."""
        with self.lock:
            if chunk_id is not None:
                row = self.db.execute("select page_id, section from chunks where id = ?", (int(chunk_id),)).fetchone()
                if not row:
                    return {"error": "no such passage"}
                pid, sec = row["page_id"], row["section"]
            else:
                p = self.db.execute("select id from pages where lower(title) = lower(?)", (page or "",)).fetchone()
                if not p:
                    return {"error": "no page called %r" % page}
                pid = p["id"]
                secs = [r["section"] for r in self.db.execute(
                    "select section from chunks where page_id = ? group by section order by min(ord)", (pid,))]
                want = (name or "").lower()
                sec = next((s for s in secs if want and want in (s or "").lower()), secs[0] if secs else "")
            rows = self.db.execute("select id, ord, text from chunks where page_id = ? and section = ? order by ord",
                                   (pid, sec)).fetchall()
            page_row = self.db.execute("select title, url, meta from pages where id = ?", (pid,)).fetchone()
            outline = [r["section"] for r in self.db.execute(
                "select section from chunks where page_id = ? group by section order by min(ord)", (pid,))]
        start = max(0, int(start))
        texts, used, i = [], 0, start
        while i < len(rows) and (not texts or used + len(rows[i]["text"]) <= max_chars):
            texts.append(rows[i]["text"])
            used += len(rows[i]["text"])
            i += 1
        meta = json.loads(page_row["meta"] or "{}")
        status = page_status(meta, page_row["title"], rows[0]["text"] if rows else "")
        nxt = outline[outline.index(sec) + 1] if sec in outline and outline.index(sec) + 1 < len(outline) else None
        return {"title": page_row["title"], "section": sec, "text": "\n\n".join(texts), "url": page_row["url"],
                "part": start + 1, "parts": len(rows), "more": i < len(rows), "next_start": i if i < len(rows) else None,
                "next_section": nxt, "outline": outline, "status": status, "outdated": status != "current"}

    # ------------------------------------------------------------------ numbers

    def stats(self):
        out = {"path": self.path, "embedding_model": self.model_name or None, "sources": {}}
        for s in self.db.execute("select * from sources order by name"):
            name = s["name"]
            pages = self.db.execute("select count(*) from pages where source = ?", (name,)).fetchone()[0]
            ch = self.db.execute("select count(*), sum(length(text)), sum(emb is not null and emb_model = ?) from chunks"
                                 " where source = ?", (self.model_name, name)).fetchone()
            out["sources"][name] = {"title": s["title"], "license": s["license"], "pages": pages, "chunks": ch[0],
                                    "text_chars": ch[1] or 0, "embedded": ch[2] or 0,
                                    "params": json.loads(s["params"] or "{}"), "last_crawl": s["last_crawl"],
                                    "last_refresh": s["last_refresh"], "queue": self.queue_counts(name)}
        out["pages"] = sum(v["pages"] for v in out["sources"].values())
        out["chunks"] = sum(v["chunks"] for v in out["sources"].values())
        try:
            out["db_bytes"] = sum(os.path.getsize(self.path + suf) for suf in ("", "-wal") if os.path.exists(self.path + suf))
        except OSError:
            out["db_bytes"] = None
        return out


# A best chunk scoring at least this counts as an answer ("covered"). Calibrated on minecraft.wiki
# with local embeddings: real answers score 0.6-0.9, near misses (a guide that mentions the thing,
# another mob's page) 0.45-0.6; on words alone answers score 0.6-1.0.
COVERED_SCORE = 0.55
# a passage whose page and section aren't about the thing asked must match this well to count
STRONG_SCORE = 0.72


# how much a page that isn't about the player's game counts (textify.wiki_status says which)
STATUS_WEIGHT = {"current": 1.0, "outdated": 0.55, "removed": 0.5, "future": 0.45, "other-edition": 0.45,
                 "spin-off": 0.3, "joke": 0.3}


def page_status(meta, title="", lead=""):
    """'current', or why the page isn't about the game as the player has it (see textify.wiki_status):
    stored with the page when it was fetched; worked out from its categories for older pages."""
    meta = meta or {}
    return meta.get("status") or textify.wiki_status(meta, title or "", lead or "")


def outdated(meta, text=""):
    """Kept for callers of the first version: anything not current."""
    return page_status(meta, "", text) != "current"


def coverage(query, results, threshold=COVERED_SCORE):
    """Is the question answered by these results? The best one must score >= threshold, be about
    the game as the player has it (status current), and be about the thing asked: its page *is*
    that thing ("Piston" for "make a piston"), or its page or section heading names it, or it names
    it and matches very well; not a different thing with a similar name ("Smiling Creeper" is not
    "Creeper"). A question about two things ("a librarian with mending") is answered by the pages
    of both among the top 3. A build/farm question needs a current guide whose title names the thing."""
    best = results[0]["score"] if results else 0.0

    def current(r):
        return r["score"] >= threshold and r.get("status", "current") == "current"

    def answers(r):
        # not a word in passing ("bed" in Bone Meal), not a different thing with a similar name
        if not current(r):
            return False
        if r["title_match"] >= 0.95:
            return True
        if r["covers"] < 1.0 or r["named_like"]:
            return False
        return r.get("in_heading", True) or r["score"] >= STRONG_SCORE
    covered = bool(results) and answers(results[0])
    subject = parse_question(query)["subject"]
    if not covered and results and len(subject) > 1 and current(results[0]) and results[0]["title_match"] >= 0.85:
        named = set()
        for r in results[:3]:
            if current(r) and r["title_match"] >= 0.85:
                named |= set(r.get("name_covers") or [])
        covered = subject <= named
    if set(words(query)) & BUILD_WORDS:
        # a guide about that very thing (its title names it: "Tutorial:Iron golem farming"), current, not a
        # paragraph in a general tutorial ("Flat survival") or how it worked in an older version
        covered = any(r["guide"] and current(r) and r.get("title_subject", r["title_match"] > 0)
                      and r["covers"] >= 1.0 for r in results[:3])
    return {"best": best, "covered": covered, "threshold": threshold}


def embed_text(title, section, text):
    head = title if not section or section == "Summary" else "%s - %s" % (title, section)
    return (head + ": " + text)[:2000]


def _chunk_hash(title, c):
    return hashlib.sha1(("%s\x00%s\x00%s" % (title, c["section"], c["text"])).encode("utf-8")).hexdigest()


# the words that say what kind of question it is ("make", "spawn", "build"...) and what one does
KIND_STEMS = {stem(w) for trig, _, _ in INTENTS for w in trig} | {stem(w) for w in BUILD_WORDS}
ACTION_STEMS = {stem(w) for w in ACTIONS}
