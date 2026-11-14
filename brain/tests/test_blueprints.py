"""Finding the blueprint the player means in the catalogue the mod writes (catalogue.json)."""
import json
import os

from kindred import blueprints


def entry(name, category, style, what, w, l, h, blocks, beds=0, size="small", tags=()):
    return {"file": name + ".nbt", "name": name, "category": category, "style": style, "what": what, "width": w,
            "length": l, "height": h, "blocks": blocks, "beds": beds, "size": size, "tags": list(tags)}


ENTRIES = [
    entry("village_desert_small_house_1", "house", "desert", "a small desert house (a bed)", 6, 5, 6, 116, 1),
    entry("village_desert_medium_house_1", "house", "desert", "a desert house (beds for 2)", 6, 7, 6, 158, 2, tags=["small"]),
    entry("village_plains_small_house_1", "house", "plains", "a small plains house (a bed)", 7, 7, 7, 120, 1),
    entry("village_plains_big_house_1", "house", "plains", "a big plains house (beds for 3)", 7, 11, 11, 339, 3, "medium"),
    entry("village_plains_armorer_house_1", "workshop", "plains", "a plains smithy (the armorer's), with a blast furnace",
          9, 8, 8, 239, tags=["smithy", "armorer"]),
    entry("village_desert_armorer_1", "workshop", "desert", "a desert smithy (the armorer's), with a blast furnace",
          7, 7, 7, 201, tags=["smithy", "armorer"]),
    entry("village_snowy_library_1", "workshop", "snowy", "a snowy library, with a lectern", 13, 7, 10, 434, size="medium"),
    entry("shipwreck_with_mast", "ship", "wreck", "a shipwreck with its mast", 9, 28, 21, 726, size="big"),
    entry("pillager_watchtower", "tower", "pillager", "a pillager watchtower", 15, 15, 21, 1155, size="big"),
    entry("circle_10x10", "shape", "circle", "a circle 10 blocks across", 10, 10, 1, 24, size="small"),
]


def folder(tmp_path, entries=ENTRIES, extra=()):
    for e in entries:
        (tmp_path / e["file"]).write_text("x")
    for f in extra:
        (tmp_path / f).write_text("x")
    (tmp_path / "catalogue.json").write_text(json.dumps({"entries": entries}))
    return [str(tmp_path)]


def names(r, n=3):
    return [m["name"] for m in r["matches"][:n]]


def test_the_way_people_ask(tmp_path):
    d = folder(tmp_path)
    assert names(blueprints.search("a small desert house", d), 1) == ["village_desert_small_house_1"]
    assert names(blueprints.search("the plains smithy", d)) == ["village_plains_armorer_house_1"]
    assert names(blueprints.search("a house for three", d), 1) == ["village_plains_big_house_1"]
    assert names(blueprints.search("something big", d), 2) == ["pillager_watchtower", "shipwreck_with_mast"]
    assert names(blueprints.search("a boat", d)) == ["shipwreck_with_mast"]
    assert names(blueprints.search("snow library", d)) == ["village_snowy_library_1"]
    assert blueprints.search("a castle", d)["matches"] == []


def test_she_asks_when_several_fit_and_confirms_big_ones(tmp_path):
    d = folder(tmp_path)
    houses = blueprints.search("a house", d)
    assert "ask which one" in houses["say"]
    one = blueprints.search("the plains smithy", d)
    assert one["say"].startswith("One fits best")
    m = one["matches"][0]
    assert m["what"].startswith("a plains smithy") and m["size"] == "9 x 8, 8 high" and m["blocks"] == 239
    big = blueprints.search("a ship", d)
    assert big["matches"][0]["big"] and "confirm before building" in big["say"]
    assert "make up a cottage" in blueprints.search("a house for 3", d)["say"]


def test_what_kinds_there_are_and_new_files(tmp_path):
    d = folder(tmp_path, extra=["my_castle.schem"])
    r = blueprints.search("", d)
    assert r["total"] == 11 and r["kinds"]["house"] == 4 and r["kinds"]["not described yet"] == 1
    new = blueprints.search("castle", d)["matches"]
    assert new[0]["name"] == "my_castle" and "not described yet" in new[0]["note"]


def test_no_folder_no_blueprints(tmp_path):
    assert not blueprints.search("house", [str(tmp_path / "nope")])["ok"]


# ---------------------------------------------------------------------- the dashboard's folder operations

NBT = b"\x1f\x8b" + b"\x00" * 30  # (gzip magic: what a schematic starts with)


def test_adding_removing_and_restoring(tmp_path):
    d = str(tmp_path / "blueprints")
    assert blueprints.add(d, "my castle.schem", NBT)["added"] == "my castle.schem"
    try:
        blueprints.add(d, "notes.txt", NBT)
        raise AssertionError("a text file")
    except ValueError as e:
        assert ".nbt" in str(e)
    assert blueprints.add(d, "../../evil.nbt", NBT)["added"] == "evil.nbt", "only the base name, inside the folder"
    assert blueprints.add(d, ".hidden.nbt", NBT)["added"] == "hidden.nbt", "never a hidden file"
    for data, why in [(b"", "empty"), (b"hello world", "doesn't look like"), (b"\x0a" * (blueprints.MAX_BYTES + 1), "too big")]:
        try:
            blueprints.add(d, "x.nbt", data)
            raise AssertionError("accepted " + why)
        except ValueError as e:
            assert why in str(e)
    try:
        blueprints.add(d, "my castle.schem", NBT)
        raise AssertionError("overwrote")
    except ValueError as e:
        assert "already" in str(e)
    assert blueprints.add(d, "my castle.schem", NBT, replace=True)["added"]
    blueprints.remove(d, "my castle.schem")
    assert not (tmp_path / "blueprints" / "my castle.schem").exists()
    assert (tmp_path / "blueprints" / ".trash" / "my castle.schem").exists(), "never deleted: to the trash"
    over = blueprints.overview([d])["dirs"][0]
    assert over["trash"] == ["my castle.schem"] and over["new"] == ["evil.nbt", "hidden.nbt"]
    blueprints.add(d, "my castle.schem", NBT)
    second = blueprints.remove(d, "my castle.schem")["trash"]
    assert second != "my castle.schem", "a second one with the same name doesn't replace the first in the trash"
    assert blueprints.restore(d, "my castle.schem")["restored"] == "my castle.schem"
    try:
        blueprints.restore(d, second)
        raise AssertionError("restored over an existing file")
    except ValueError as e:
        assert "already" in str(e)


def test_pictures_only_from_the_pictures_folder(tmp_path):
    (tmp_path / ".catalogue").mkdir()
    (tmp_path / ".catalogue" / "igloo.top.png").write_bytes(b"png")
    (tmp_path / "secret.txt").write_text("no")
    assert blueprints.picture(str(tmp_path), "igloo.top.png") == b"png"
    for bad in ("../secret.txt", "igloo.top.png/../../secret.txt", "secret.txt", "IGLOO.TOP.PNG"):
        assert blueprints.picture(str(tmp_path), bad) is None, bad


def test_the_dashboard_lists_the_catalogue(tmp_path):
    d = folder(tmp_path, extra=["fresh.nbt"])
    (tmp_path / "SOURCES.txt").write_text("- village_*: Minecraft's own")
    over = blueprints.overview(d)["dirs"][0]
    assert len(over["entries"]) == len(ENTRIES) and over["new"] == ["fresh.nbt"]
    assert "Minecraft's own" in over["sources"]


def test_the_games_own_structures_come_after_yours(tmp_path):
    """#181: the game's village houses are copied into a folder of their own; a file of yours with the same name
    is the one she offers, once."""
    mine, game = tmp_path / "blueprints", tmp_path / "blueprints-from-minecraft"
    mine.mkdir()
    game.mkdir()
    (mine / "village_plains_small_house_1.nbt").write_bytes(b"x")
    (game / "village_plains_small_house_1.nbt").write_bytes(b"x")
    (game / "igloo.nbt").write_bytes(b"x")
    found = blueprints.load([str(mine), str(game)])
    assert [(os.path.basename(e["dir"]), e["file"]) for e in found] == [
        ("blueprints", "village_plains_small_house_1.nbt"), ("blueprints-from-minecraft", "igloo.nbt")]
    assert blueprints.DIRS[-1].endswith("blueprints-from-minecraft") or os.environ.get("KINDRED_BLUEPRINTS")
