"""Kindred Spirit's knowledge base: what Minecraft *is* (recipes, mobs, biomes, mechanics,
redstone, farming, build guides), crawled politely from a few sources into one local SQLite
file the companion can search, so she answers from real text instead of inventing.

    python services/knowledge/kb.py crawl minecraft-wiki --category Mobs --limit 50
    python services/knowledge/kb.py search "how do I make a piston"

From Python:   knowledge.search("how do I make a piston", k=5)
Over HTTP:     POST http://127.0.0.1:11437/v1/knowledge/search {"query": "...", "k": 5}
               (the gateway mounts knowledge/api.py)

Everything lives in ~/.kindred-spirit/knowledge/ (knowledge.db, cache/, local/, sources.json),
apart from the companion's personal memories. See docs/KNOWLEDGE.md.
"""
import json
import os
import sys
import urllib.request

from .sources import knowledge_dir
from .store import KnowledgeStore

GATEWAY = os.environ.get("KINDRED_GATEWAY_URL", "http://127.0.0.1:11437/v1")


def db_path(kdir=None):
    return os.path.join(kdir or knowledge_dir(), "knowledge.db")


def gateway_embedding_model():
    """The embedding model the gateway is set to use (read from gateway.json, the way the gateway
    reads it), so vectors made by the CLI and by the gateway carry the same model name. "" = none."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        import kindred_gateway as gw
        name, p = gw.provider(gw.load(), "embeddings")
    except Exception:
        return "gateway"
    if name == "none" or not p.get("url"):
        return ""
    return "%s:%s" % (name, p.get("model", ""))


def gateway_embedder(base=GATEWAY, timeout=60):
    """embed(texts, query) through the gateway's /v1/embeddings (whatever provider the player chose)."""
    key = os.environ.get("KINDRED_GATEWAY_KEY", "")

    def embed(texts, query=False):
        body = json.dumps({"input": texts, "input_type": "query" if query else "passage"}).encode()
        req = urllib.request.Request(base.rstrip("/") + "/embeddings", data=body, method="POST",
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": "Bearer " + key} if key else {})})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        return [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
    return embed


def open_store(path=None, embed="gateway", model_name=None):
    """The knowledge store. embed="gateway" uses the gateway's embeddings when it answers, else
    keyword search only; pass a function (texts, query) -> vectors, or None for keywords only."""
    if embed == "gateway":
        model_name = gateway_embedding_model() if model_name is None else model_name
        embed = gateway_embedder() if model_name else None
    return KnowledgeStore(path or db_path(), embed=embed, model_name=model_name or "")


_default = None


def search(query, k=5, sources=None, path=None):
    """Ranked chunks: [{title, section, text, url, license, attribution, score, ...}]."""
    global _default
    if path:
        return open_store(path).search(query, k=k, sources=sources)
    if _default is None:
        _default = open_store()
    return _default.search(query, k=k, sources=sources)
