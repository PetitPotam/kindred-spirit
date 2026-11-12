"""The gateway's memory store: ranking, merging, keyword search, safety."""
import os
import tempfile

import gateway_stub  # noqa: F401  (puts services/ on the path)
import memory_store


def words(texts, query=False):  # deterministic stand-in embedder: bag of words over a tiny vocabulary
    vocab = ["diamond", "cherry", "house", "blue", "zombie", "base", "sunset", "mine"]
    return [[float(t.lower().count(w)) + 0.01 for w in vocab] for t in texts]


def store(embed=words):
    return memory_store.Store(os.path.join(tempfile.mkdtemp(), "m.db"), embed=embed, model_name="test" if embed else "")


def test_meaning_and_keywords_rank_the_right_memory_first():
    s = store()
    s.add("player", "Likes the colour blue.", world=None, importance=6)
    s.add("episode", "We mined diamonds near the base.", world="w", importance=3)
    s.add("episode", "Watched the sunset from the cherry house.", world="w", importance=3)
    top = s.search("where were the diamonds?", world="w", k=1)[0]
    assert "diamonds" in top["text"]


def test_keyword_only_when_no_embedder():
    s = store(embed=None)
    s.add("player", "Calls the dog Biscuit.", importance=5)
    s.add("player", "Likes rainy days.", importance=5)
    assert "Biscuit" in s.search("what's my dog Biscuit doing", k=1)[0]["text"]


def test_world_scoping():
    s = store()
    s.add("world", "Castle of quartz.", world="a")
    s.add("player", "Likes quartz.", world=None)
    seen = [m["text"] for m in s.search("quartz", world="b", k=5)]
    assert seen == ["Likes quartz."], "another world's facts stay there; facts about you go everywhere"


def test_near_duplicates_merge():
    s = store()
    a, merged1 = s.add("player", "Likes blue", dedupe=0.95)
    b, merged2 = s.add("player", "likes BLUE", importance=9, dedupe=0.95)
    assert a == b and merged2 and not merged1
    assert s.get(a)["importance"] == 9


def test_delete_never_wipes_everything_by_accident():
    s = store()
    s.add("player", "x")
    assert s.delete() == 0
    assert s.delete(kinds=["player"], contains="x") == 1


def test_docs_and_reembed():
    s = store(embed=None)
    s.doc("k", {"a": 1})
    assert s.doc("k") == {"a": 1}
    s.add("player", "Likes diamonds")
    s2 = memory_store.Store(s.path, embed=words, model_name="test")
    assert s2.reembed() == 1 and s2.reembed() == 0


def test_a_full_reset_also_clears_the_bond_and_conversations():
    s = store()
    s.doc("heart", {"bond": 80, "discovered": ["find_ore"]})
    s.doc("world:sp:A:history", [{"role": "user", "content": "hi"}])
    assert s.clear_docs() == 2
    assert s.doc("heart") is None and s.doc("world:sp:A:history") is None
