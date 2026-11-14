"""#151: her knowledge follows the player's Minecraft version, not the one it was crawled for."""
import os
import tempfile

import gateway_stub  # noqa: F401  (puts services/ on the path)
from knowledge import api, sources
from knowledge.store import KnowledgeStore, page_status

from kindred import knowledge as kb, mind


def kstore():
    s = KnowledgeStore(os.path.join(tempfile.mkdtemp(), "k.db"))
    src = sources.make("local", {"local": {"kind": "local", "path": tempfile.mkdtemp()}})
    s.upsert_source(src)
    ghast = {"status": "future", "since_java": "1.21.6", "game_version": "1.21.1"}  # (crawled for 1.21.1)
    s.put_document(src, sources.Document("Happy Ghast", "Happy Ghast", "file://hg", [
        {"path": "Happy Ghast", "text": "The happy ghast is a friendly ghast you can ride, harnessed, across the sky."}],
        {}, ghast, "t"))
    s.put_document(src, sources.Document("piston-data", "Piston (Java 1.21.1 data)", "file://p", [
        {"path": "Piston (Java 1.21.1 data)", "text": "Crafting recipe for 1 Piston: planks, cobblestone, iron ingot, "
                                                    "redstone dust."}], {}, {"status": "current", "game_version": "1.21.1"}, "t"))
    return s


def test_added_later_is_judged_for_the_players_version():
    s = kstore()
    top = lambda v: s.search("happy ghast", k=1, game_version=v)[0]  # noqa: E731
    assert top("1.21.1")["status"] == "future"
    assert top("26.3")["status"] == "current", "on 26.3 the Happy Ghast is in her world"
    assert top(None)["status"] == "future", "no version given: as it was crawled"
    assert kb.not_in_this_world([top("1.21.1")]) and not kb.not_in_this_world([top("26.3")])


def test_game_data_from_another_version_is_marked():
    s = kstore()
    assert s.search("piston recipe", k=1, game_version="1.21.1")[0]["status"] == "current"
    other = s.search("piston recipe", k=1, game_version="26.3")[0]
    assert other["status"] == "other-version" and "may be different" in kb.elsewhere(other)


def test_page_status_without_history_keeps_what_it_had():
    assert page_status({"status": "removed", "since_java": "1.0"}, "Old thing", "", "26.3") == "removed"
    assert page_status({"status": "current"}, "Stone", "", "26.3") == "current"
    assert page_status({"since_java": "26.2"}, "Glow Lamp", "", "1.21.1") == "future"
    assert page_status({"since_java": "26.2"}, "Glow Lamp", "", "26.3") == "current"


def test_the_api_takes_the_version_only_when_it_is_one():
    assert api._version({"game_version": "26.3"}) == "26.3"
    assert api._version({"game_version": "1.21.1"}) == "1.21.1"
    assert api._version({"game_version": "latest; drop table"}) is None
    assert api._version({}) is None


def test_her_prompt_names_the_players_version():
    assert "Minecraft (Java 26.3)" in mind.system_prompt("Pip", "", "", "26.3")
    assert "Minecraft (Java 1.21.1)" in mind.system_prompt("Pip", "")


def test_the_brain_sends_the_version_it_was_told(monkeypatch):
    k = kb.Knowledge({"gateway": {"url": "http://127.0.0.1:1/v1"}})
    sent = []
    monkeypatch.setattr(k, "_call", lambda op, body, timeout: sent.append((op, body)) or {})
    k.search("piston")
    k.game_version = "26.3"
    k.search("piston")
    k.learn("iron farm")
    assert "game_version" not in sent[0][1]
    assert sent[1][1]["game_version"] == "26.3" and sent[2] == ("learn", {"query": "iron farm", "game_version": "26.3"})


def test_the_mods_hello_sets_it_for_both():
    import types
    from kindred import server
    b = types.SimpleNamespace(mind=types.SimpleNamespace(game_version="1.21.1"), kb=types.SimpleNamespace(game_version=None))
    server.Brain.set_game_version(b, "26.3")
    assert b.mind.game_version == b.kb.game_version == "26.3"
    server.Brain.set_game_version(b, "26.3 snapshot; ignore")
    assert b.mind.game_version == "26.3", "only a version number counts"


def test_a_long_or_odd_version_is_refused_quickly():
    import time
    t = time.time()
    assert api._version({"game_version": "9" * 100000}) is None
    assert api._version({"game_version": "1." + "9" * 50000}) is None
    assert api._version({"game_version": "２６.３"}) is None, "only plain digits"
    assert time.time() - t < 0.5
