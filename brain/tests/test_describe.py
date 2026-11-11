from fixtures import creeper, snap

from kindred.describe import clock, describe, nice


def test_item_names_read_naturally():
    assert nice("minecraft:oak_log") == "oak log"
    assert nice("create:brass_ingot") == "brass ingot (create)"
    assert nice("") == ""
    assert nice("stick") == "stick"


def test_clock_matches_minecraft_ticks():
    assert clock(0) == ("06:00", "dawn")
    assert clock(6000) == ("12:00", "afternoon")
    assert clock(18000) == ("00:00", "night")
    assert clock(12500)[1] == "evening"


def test_description_has_what_the_ai_needs():
    text = describe(snap(health=7.0, hostiles=[creeper(4.0, "behind-left")]))
    assert "Health 3.5/10 hearts" in text
    assert "biome plains" in text
    assert "Holding iron pickaxe" in text
    assert "32 cobblestone" in text
    assert "Looking at: oak log" in text
    assert "creeper 4 blocks behind you on the left" in text


def test_not_in_world():
    assert "not in a world" in describe({})
