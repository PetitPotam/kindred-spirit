"""The gateway's local memory store: one SQLite file with the companion's memories, their
embeddings, and a few small documents. The brain decides *what* to remember; this keeps it and
finds the right memories again ("retrieval" in RAG).

Search blends four signals, as in generative-agent memory designs:
  meaning   cosine similarity of embeddings (if an embedding service is available)
  keywords  SQLite full-text search (BM25), so names and exact words always count
  recency   memories fade (half-life ~ a week) unless used
  importance  set when the memory was written (1-10)

A memory: {id, kind, world, text, importance, meta, created, updated, last_used, uses}.
world = None means it's about the player or the companion everywhere (facts, habits, self).
Standard library only; numpy is used if present (much faster cosine), else plain Python.
"""
import json
import math
import os
import re
import sqlite3
import struct
import threading
import time

try:
    import numpy as np
except ImportError:  # works without, just slower on big memories
    np = None

SCHEMA = """
create table if not exists memories (
  id integer primary key, kind text not null, world text, text text not null,
  importance real default 5, meta text default '{}', created real, updated real,
  last_used real, uses integer default 0, emb blob, emb_model text);
create index if not exists memories_kind on memories(kind, world);
create virtual table if not exists memories_fts using fts5(text, content='memories', content_rowid='id');
create trigger if not exists memories_ai after insert on memories begin
  insert into memories_fts(rowid, text) values (new.id, new.text); end;
create trigger if not exists memories_ad after delete on memories begin
  insert into memories_fts(memories_fts, rowid, text) values ('delete', old.id, old.text); end;
create trigger if not exists memories_au after update of text on memories begin
  insert into memories_fts(memories_fts, rowid, text) values ('delete', old.id, old.text);
  insert into memories_fts(rowid, text) values (new.id, new.text); end;
create table if not exists docs (key text primary key, value text, updated real);
"""

HALF_LIFE_DAYS = 7.0


def _pack(vec):
    return struct.pack("<%df" % len(vec), *vec)


def _unpack(blob):
    return list(struct.unpack("<%df" % (len(blob) // 4), blob)) if blob else None


def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _fts_query(text):
    words = [w for w in re.findall(r"[A-Za-z0-9_']{3,}", text.lower()) if w not in STOP]
    return " OR ".join('"%s"' % w.replace('"', "") for w in words[:12])


STOP = set("the and you your for are was with this that what where when how can could would should have has "
           "had not but all any our out too its it's i'm there here they them then than just about from into "
           "please pip me my".split())


class Store:
    """embed(texts, query=False) -> list of vectors (or None when no embedder is available)."""

    def __init__(self, path, embed=None, model_name=""):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.embed = embed
        self.model_name = model_name
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ------------------------------------------------------------------ writing

    def _vector(self, text, query=False):
        if not self.embed:
            return None
        try:
            v = self.embed([text], query)
            return _norm(v[0]) if v else None
        except Exception:
            return None  # embeddings are a bonus: keyword search still works

    def add(self, kind, text, world=None, importance=5.0, meta=None, dedupe=None, now=None):
        """Adds a memory. dedupe=0.9 merges it into a very similar one of the same kind instead
        (keeping the newer wording and the higher importance). Returns (id, merged)."""
        now = now or time.time()
        text = " ".join((text or "").split())[:1000]
        if not text:
            raise ValueError("empty memory")
        vec = self._vector(text)
        if dedupe and vec:
            for hit in self.search(text, kinds=[kind], world=world, k=1, now=now, _vec=vec, touch=False):
                if hit["similarity"] >= dedupe:
                    merged = {**hit["meta"], **(meta or {})}
                    if "expires" not in (meta or {}) or "expires" not in hit["meta"]:
                        merged.pop("expires", None)  # lasting wins over passing, whichever came first
                    self.update(hit["id"], text=text, importance=max(importance, hit["importance"]),
                                meta=merged, now=now, _vec=vec)
                    return hit["id"], True
        with self.lock:
            cur = self.db.execute(
                "insert into memories(kind, world, text, importance, meta, created, updated, last_used, emb, emb_model)"
                " values (?,?,?,?,?,?,?,?,?,?)",
                (kind, world, text, float(importance), json.dumps(meta or {}), now, now, now,
                 _pack(vec) if vec else None, self.model_name if vec else None))
            self.db.commit()
            return cur.lastrowid, False

    def update(self, mid, text=None, importance=None, meta=None, now=None, _vec=None):
        now = now or time.time()
        row = self.get(mid)
        if not row:
            return False
        sets, vals = ["updated = ?"], [now]
        if text is not None and text != row["text"]:
            vec = _vec or self._vector(text)
            sets += ["text = ?", "emb = ?", "emb_model = ?"]
            vals += [text, _pack(vec) if vec else None, self.model_name if vec else None]
        if importance is not None:
            sets.append("importance = ?")
            vals.append(float(importance))
        if meta is not None:
            sets.append("meta = ?")
            vals.append(json.dumps(meta))
        with self.lock:
            self.db.execute("update memories set %s where id = ?" % ", ".join(sets), vals + [mid])
            self.db.commit()
        return True

    def delete(self, mid=None, kinds=None, world=None, contains=None, strict=False):
        where, vals = self._filter(kinds, world, all_worlds=world is None, strict=strict)
        if mid is not None:
            where.append("id = ?")
            vals.append(mid)
        if contains:
            where.append("lower(text) like ?")
            vals.append("%" + contains.lower() + "%")
        if mid is None and not contains and not kinds:
            return 0  # never "delete everything" by accident
        with self.lock:
            cur = self.db.execute("delete from memories where " + " and ".join(where or ["1"]), vals)
            self.db.commit()
            return cur.rowcount

    # ------------------------------------------------------------------ reading

    def get(self, mid):
        r = self.db.execute("select * from memories where id = ?", (mid,)).fetchone()
        return self._row(r) if r else None

    def _row(self, r):
        return {"id": r["id"], "kind": r["kind"], "world": r["world"], "text": r["text"],
                "importance": r["importance"], "meta": json.loads(r["meta"] or "{}"),
                "created": r["created"], "updated": r["updated"], "uses": r["uses"]}

    @staticmethod
    def _filter(kinds, world, all_worlds=False, strict=False):
        where, vals = [], []
        if kinds:
            where.append("kind in (%s)" % ",".join("?" * len(kinds)))
            vals += list(kinds)
        if not all_worlds:
            # this world's memories plus, unless strict (each world has its own companion), the ones
            # that belong everywhere (about you, about itself)
            where.append("world = ?" if strict else "(world is null or world = ?)")
            vals.append(world)
        return where, vals

    def list(self, kinds=None, world=None, limit=50, order="recent", all_worlds=False, strict=False):
        where, vals = self._filter(kinds, world, all_worlds, strict)
        by = {"recent": "updated desc", "important": "importance desc, updated desc", "oldest": "created asc"}.get(order, "updated desc")
        rows = self.db.execute("select * from memories %s order by %s limit ?" % (
            ("where " + " and ".join(where)) if where else "", by), vals + [int(limit)]).fetchall()
        return [self._row(r) for r in rows]

    def search(self, query, kinds=None, world=None, k=8, now=None, touch=True, _vec=None, all_worlds=False,
               strict=False):
        """The memories that matter for this query, best first, each with a score."""
        now = now or time.time()
        where, vals = self._filter(kinds, world, all_worlds, strict)
        rows = self.db.execute("select * from memories %s" % (("where " + " and ".join(where)) if where else ""),
                               vals).fetchall()
        if not rows:
            return []
        # keywords (BM25 via full-text search), turned into a 0..1 rank score
        kw = {}
        fq = _fts_query(query)
        if fq:
            try:
                hits = self.db.execute("select rowid from memories_fts where memories_fts match ? order by rank limit 50",
                                       (fq,)).fetchall()
                for i, h in enumerate(hits):
                    kw[h[0]] = 1.0 - i / max(1, len(hits))
            except sqlite3.OperationalError:
                pass
        # meaning (cosine of embeddings); rows embedded with another model are skipped until re-embedded
        qv = _vec or self._vector(query, query=True)
        sims = {}
        if qv:
            ids = [r["id"] for r in rows if r["emb"] and r["emb_model"] == self.model_name]
            if ids:
                byid = {r["id"]: r for r in rows}
                if np is not None:
                    m = np.array([_unpack(byid[i]["emb"]) for i in ids], dtype=np.float32)
                    s = m @ np.array(qv, dtype=np.float32)
                    sims = dict(zip(ids, (float(x) for x in s)))
                else:
                    for i in ids:
                        v = _unpack(byid[i]["emb"])
                        sims[i] = sum(a * b for a, b in zip(v, qv))
        out = []
        for r in rows:
            sim = sims.get(r["id"], 0.0)
            age_days = max(0.0, (now - (r["last_used"] or r["created"] or now)) / 86400)
            recency = 0.5 ** (age_days / HALF_LIFE_DAYS)
            imp = min(10.0, max(0.0, r["importance"] or 5)) / 10
            if qv:
                score = 0.6 * max(0.0, sim) + 0.15 * kw.get(r["id"], 0) + 0.12 * recency + 0.13 * imp
            else:
                score = 0.6 * kw.get(r["id"], 0) + 0.2 * recency + 0.2 * imp
            d = self._row(r)
            d["score"] = round(score, 4)
            d["similarity"] = round(sim, 4)
            out.append(d)
        out.sort(key=lambda d: d["score"], reverse=True)
        out = out[:int(k)]
        if touch and out:
            with self.lock:
                self.db.executemany("update memories set last_used = ?, uses = uses + 1 where id = ?",
                                    [(now, d["id"]) for d in out])
                self.db.commit()
        return out

    def reembed(self, batch=64):
        """After switching embedding model: give old memories the new kind of vector."""
        if not self.embed:
            return 0
        rows = self.db.execute("select id, text from memories where emb_model is null or emb_model != ? limit ?",
                               (self.model_name, batch)).fetchall()
        if not rows:
            return 0
        vecs = self.embed([r["text"] for r in rows], False)
        if not vecs:
            return 0
        with self.lock:
            self.db.executemany("update memories set emb = ?, emb_model = ? where id = ?",
                                [(_pack(_norm(v)), self.model_name, r["id"]) for r, v in zip(rows, vecs)])
            self.db.commit()
        return len(rows)

    # ------------------------------------------------------------------ small documents (stats, recent talk)

    def doc(self, key, value=None, now=None):
        if value is None:
            r = self.db.execute("select value from docs where key = ?", (key,)).fetchone()
            return json.loads(r[0]) if r else None
        with self.lock:
            self.db.execute("insert into docs(key, value, updated) values (?,?,?) on conflict(key) do update set "
                            "value = excluded.value, updated = excluded.updated", (key, json.dumps(value), now or time.time()))
            self.db.commit()
        return value

    def docs(self, prefix=""):
        rows = self.db.execute("select key, length(value), updated from docs where key like ? order by updated desc",
                               (prefix + "%",)).fetchall()
        return [{"key": r[0], "size": r[1], "updated": r[2]} for r in rows]

    def clear_docs(self, prefix=""):
        """Forget the saved state (all of it, or one world's: prefix "world:ID:"): the bond,
        discovered powers, conversations and summaries."""
        with self.lock:
            like = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            n = self.db.execute("delete from docs where key like ? escape '\\'", (like,)).rowcount
            self.db.commit()
        return n

    def stats(self):
        rows = self.db.execute("select kind, count(*) from memories group by kind").fetchall()
        return {"memories": {r[0]: r[1] for r in rows}, "path": self.path, "embedding_model": self.model_name or None}
