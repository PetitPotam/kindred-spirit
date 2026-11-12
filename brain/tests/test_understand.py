"""System 0's understanding: a request must be close to its examples and clearly closer than chat."""
import zlib

from kindred.understand import Understand

WORDS = 64


def fake_embed(texts, query):
    """Bag of words: shared words make sentences similar (enough to test the decision rule)."""
    out = []
    for t in texts:
        v = [0.0] * WORDS
        for w in t.lower().replace(",", " ").replace("?", " ").split():
            v[zlib.crc32(w.encode()) % WORDS] += 1.0
        out.append(v)
    return out


def understand():
    u = Understand({"gateway": {"url": "http://127.0.0.1:9/v1"}})
    u._embed = fake_embed
    return u


def test_a_request_close_to_its_examples_is_understood():
    u = understand()
    assert u.hint("help, i'm being attacked", ["protect", "guide"]) == "protect"
    assert u.hint("help, i'm being attacked", ["guide"]) is None, "only powers she may use"


def test_plain_conversation_is_not_a_request():
    u = understand()
    assert u.hint("thank you", ["protect", "guide", "find_animal"]) is None


def test_without_embeddings_only_the_rules_apply():
    u = Understand({"gateway": {"url": "http://127.0.0.1:9/v1"}})  # nothing listens there
    assert u.hint("protect me", ["protect"]) is None
