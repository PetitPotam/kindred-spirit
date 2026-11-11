import tempfile

from fixtures import snap

from kindred.memory import Memory, ago, compass


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


def mem():
    c = Clock()
    return Memory(tempfile.mkdtemp(), clock=c), c


def test_facts_about_you_follow_you_to_every_world():
    m, _ = mem()
    m.open_world("sp:World A")
    assert m.remember("Loves cherry trees")
    assert not m.remember("loves cherry trees"), "no duplicates"
    m2 = Memory(m.dir)
    m2.open_world("sp:World B")
    assert "Loves cherry trees" in m2.block(snap())


def test_places_are_described_from_where_you_stand():
    m, _ = mem()
    m.open_world("sp:World A")
    m.name_place("my base", snap())  # at x 12 z -30
    far = snap(where={"x": 12, "y": 70, "z": 70, "dimension": "minecraft:overworld"})
    assert "my base (100 blocks north)" in m.block(far)
    assert "my base (right here)" in m.block(snap())
    nether = snap(where={"x": 0, "y": 70, "z": 0, "dimension": "minecraft:the_nether"})
    assert "in overworld" in m.block(nether)


def test_forget_removes_facts_and_places():
    m, _ = mem()
    m.open_world("sp:A")
    m.remember("My favourite colour is blue")
    m.name_place("blue house", snap())
    assert m.forget("blue") == 2
    assert "blue" not in m.block(snap())


def test_sessions_welcome_back_and_diary():
    m, c = mem()
    m.open_world("sp:A")
    assert m.start_session() is None
    assert "first time" in m.welcome(None)
    c.t += 600
    m.end_session()
    m.write_diary("We built a little birch cabin.")
    c.t += 2 * 86400
    again = Memory(m.dir, clock=c)
    again.open_world("sp:A")
    since = again.start_session()
    w = again.welcome(since)
    assert "2 days" in w and "birch cabin" in w
    assert "played together 2 times" in again.block(snap())
    assert "10 minutes" in again.block(snap())


def test_found_things_are_kept_once():
    m, _ = mem()
    m.open_world("sp:A")
    m.found("diamond ore", 20, -50, 3, "minecraft:overworld")
    m.found("diamond ore", 22, -50, 4, "minecraft:overworld")
    assert len(m.world["found"]) == 1


def test_words():
    assert ago(90) == "1 minute" and ago(3 * 86400 + 5) == "3 days"
    assert compass(0, -5) == "north" and compass(5, 0) == "east"
