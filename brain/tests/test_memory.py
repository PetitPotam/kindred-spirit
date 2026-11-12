import asyncio

from fixtures import snap
from gateway_stub import memory

from kindred.memory import ago, compass, parse_when


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


def run(coro):
    return asyncio.run(coro)


def test_learned_things_about_you_follow_you_to_every_world():
    m = memory()

    async def go():
        await m.open_world("sp:A")
        assert await m.remember("Loves cherry trees.")
        await m.open_world("sp:B")
        return await m.context(snap(), "what should we plant?")
    assert "Loves cherry trees." in run(go())


def test_world_knowledge_stays_in_its_world():
    m = memory()

    async def go():
        await m.open_world("sp:A")
        await m.remember("The castle is made of quartz.", about="world")
        a = await m.context(snap(), "castle")
        await m.open_world("sp:B")
        b = await m.context(snap(), "castle")
        return a, b
    a, b = run(go())
    assert "quartz" in a and "quartz" not in b


def test_places_from_where_you_stand_and_renaming_moves_them():
    m = memory()

    async def go():
        await m.open_world("sp:A")
        await m.name_place("my base", snap())                                  # x 12, z -30
        far = snap(where={"x": 12, "y": 70, "z": 70, "dimension": "minecraft:overworld"})
        one = await m.context(far, "hello")
        await m.name_place("my base", far)                                     # moved house
        two = await m.context(snap(), "hello")
        return one, two, len(await m.places())
    one, two, n = run(go())
    assert "my base (100 blocks north)" in one
    assert "my base (100 blocks south)" in two and n == 1


def test_recall_brings_up_relevant_episodes():
    m = memory()

    async def go():
        await m.open_world("sp:A")
        await m.episode("The player said: we built a pink cherry house | I said: it's lovely", 3)
        await m.episode("The player said: zombies again | I said: careful!", 3)
        return await m.context(snap(), "how is the cherry house looking?")
    ctx = run(go())
    assert "cherry house" in ctx and "Memories that come to mind" in ctx


def test_reminders_by_clock_game_time_and_session():
    c = Clock()
    m = memory(clock=c)

    async def go():
        await m.open_world("sp:A")
        await m.add_reminder("check the furnace", "in 10 minutes")
        await m.add_reminder("go to bed", "every night")
        await m.add_reminder("bring the map", "next time we play")
        early = [r["text"] for r in await m.due()]
        c.t += 601
        clock = [r["text"] for r in await m.due()]
        night = [r["text"] for r in await m.due("night")]
        night2 = [r["text"] for r in await m.due("night")]
        session = [r["text"] for r in await m.due("session")]
        left = [r["text"] for r in await m.reminders()]
        return early, clock, night, night2, session, left
    early, clock, night, night2, session, left = run(go())
    assert early == [] and clock == ["check the furnace"]
    assert night == ["go to bed"] and night2 == ["go to bed"], "repeats every night"
    assert session == ["bring the map"]
    assert left == ["go to bed"]


def test_parse_when():
    assert parse_when("in 10 minutes", 0)["due"] == 600
    assert parse_when("in an hour", 0)["due"] == 3600
    assert parse_when("every 20 minutes", 0)["every"] == 1200
    assert parse_when("at night", 0)["game"] == "night"
    assert parse_when("tomorrow morning", 0)["game"] == "morning"
    assert parse_when("next time we play", 0)["session"]


def test_sessions_and_welcome_back():
    c = Clock()
    m = memory(clock=c)

    async def go():
        await m.open_world("sp:A")
        first = await m.start_session()
        c.t += 600
        await m.end_session()
        await m.write_diary("We built a little birch cabin.")
        c.t += 2 * 86400
        await m.open_world("sp:A")
        since = await m.start_session()
        return first, await m.welcome(since), await m.context(snap(), "hi")
    first, welcome, ctx = run(go())
    assert first is None
    assert "2 days" in welcome and "birch cabin" in welcome
    assert "played together 2 times" in ctx and "10 minutes" in ctx


def test_learning_merges_instead_of_repeating():
    def embed(texts, query=False):  # a tiny stand-in for a real embedder: bag of letters
        out = []
        for t in texts:
            v = [0.0] * 26
            for ch in t.lower():
                if "a" <= ch <= "z":
                    v[ord(ch) - 97] += 1
            out.append(v)
        return out
    m = memory(embed=embed)

    async def go():
        await m.open_world("sp:A")
        n1 = await m.learn({"player": [{"text": "Likes building with birch wood.", "importance": 6}],
                            "self": ["I love sunsets."], "diary": "A cozy first day."})
        n2 = await m.learn({"player": [{"text": "Likes building with birch wood!", "importance": 8}]})
        rows = (await m.store.call("list", kinds=["player"], world="sp:A"))["results"]
        return n1, n2, rows
    n1, n2, rows = run(go())
    assert n1 == 2 and n2 == 0, "the second time it's merged, not added"
    assert len(rows) == 1 and rows[0]["importance"] == 8


def test_words():
    assert ago(90) == "1 minute" and ago(3 * 86400 + 5) == "3 days"
    assert compass(0, -5) == "north" and compass(5, 0) == "east"


def test_diary_as_list_and_merging_duplicates():
    m = memory()

    async def go():
        await m.open_world("sp:A")
        await m.learn({"player": ["Player's name is Alex.", "The player's name is Alex and he builds."]})
        rows = (await m.store.call("list", kinds=["player"], world="sp:A"))["results"]
        ids = sorted(r["id"] for r in rows)
        await m.learn({"diary": [{"text": "A lovely day.", "importance": 9}], "merge": [[ids[0], ids[1]]]})
        rows = (await m.store.call("list", kinds=["player"], world="sp:A"))["results"]
        diary = (await m.store.call("list", kinds=["diary"], world="sp:A"))["results"]
        return rows, diary
    rows, diary = run(go())
    assert len(rows) == 1 and "builds" in rows[0]["text"]
    assert diary[0]["text"].endswith("A lovely day.")


def test_each_world_has_its_own_companion():
    from kindred import config
    from kindred.heart import Heart

    async def run():
        m = memory()
        m.store.strict = m.per_world = True
        h = Heart(config.merge(config.DEFAULTS, {}), m)
        await m.open_world("sp:A")
        await h.load()
        await m.remember("The player's name is Alex.")
        h.change(40)
        h.state["discovered"].append("find_ore")
        await h.save()
        await m.open_world("sp:B")
        await h.load()
        assert "Alex" not in await m.context({}, "what's my name?"), "a new world: a new companion"
        assert h.bond == 30 and h.state["discovered"] == []
        await m.open_world("sp:A")
        await h.load()
        assert "Alex" in await m.context({}, "what's my name?")
        assert h.bond == 70 and h.state["discovered"] == ["find_ore"], "back in A: she's herself again"
    asyncio.run(run())


def test_import_what_she_knew_from_another_world(capsys, monkeypatch):
    from kindred.memory import worlds_cli

    async def setup():
        m = memory()
        m.store.strict = m.per_world = True
        await m.open_world("sp:Old World")
        await m.remember("The player's name is Alex.")
        await m.name_place("base", snap())  # places stay in their world
        await m.store.call("doc", key="world:sp:Old World:heart", value={"bond": 72, "discovered": ["guide"]})
        await m.open_world("sp:New World")
        await m.episode("We just arrived.")
        return m
    m = asyncio.run(setup())
    monkeypatch.delenv("KINDRED_GAME_CONNECTED", raising=False)
    assert worlds_cli(m.store, ["import", "old"]) == 0
    out = capsys.readouterr().out
    assert "Copied 1 memories" in out and "bond (72)" in out
    assert "Alex" in asyncio.run(m.context({}, "what's my name?"))
    heart = asyncio.run(m.store.call("doc", key="world:sp:New World:heart"))["value"]
    assert heart["bond"] == 72 and heart["discovered"] == ["guide"]
    assert not asyncio.run(m.places()), "her old base isn't in this world"
    monkeypatch.setenv("KINDRED_GAME_CONNECTED", "1")
    worlds_cli(m.store, ["import", "old", "new"])
    assert "not copied: the game is connected" in capsys.readouterr().out


def test_passing_feelings_fade_lasting_facts_stay():
    t = [1_000_000.0]
    m = memory(clock=lambda: t[0])

    async def run():
        await m.open_world("sp:A")
        await m.learn({"player": [{"text": "Alex is sad about losing all their items.", "importance": 9,
                                   "temporary": True},
                                  {"text": "Alex loves building with spruce.", "importance": 7}]})
        now = await m.context({}, "how are you")
        assert "sad about losing" in now and "spruce" in now
        t[0] += 2 * 24 * 3600  # two days later
        later = await m.context({}, "how are you")
        assert "sad about losing" not in later and "spruce" in later
    asyncio.run(run())


def test_her_origin_is_a_mystery_until_she_discovers_it():
    async def run():
        m = memory()
        await m.open_world("sp:A")
        assert "you don't know yet" in await m.context({}, "hi")
        await m.learn({"origin": [{"text": "I think I was born from the light of the first beacon.", "importance": 9}]})
        await m.learn({"origin": [{"text": "The old stones hum when I'm near them, like family.", "importance": 9}]})
        text = await m.context({}, "hi")
        line = next(l for l in text.splitlines() if l.startswith("Where you come from"))
        assert line.index("beacon") < line.index("old stones"), "her story, in the order she discovered it"
        assert "still a mystery" in line
    asyncio.run(run())
