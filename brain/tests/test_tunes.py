"""Her hums as music: taken out of her spoken words and played as a little tune."""
from kindred import tunes


def test_a_hum_is_played_not_spoken():
    spoken, hums = tunes.split("La-dee-dum, a pig in the moonlight, dum-dee-doo... that tune again!")
    assert hums == ["La-dee-dum", "dum-dee-doo"] and spoken == "a pig in the moonlight, that tune again!"
    assert tunes.split("Dum-dee-doo, dum-dee-doo, la-la-lee.")[0] == "", "only a hum: nothing to say aloud"
    assert tunes.split("I like the doodle of that dumpling.") == ("I like the doodle of that dumpling.", []), \
        "words that only contain hum syllables aren't hums"


def test_the_same_words_make_the_same_tune():
    a, b = tunes.melody("dum-dee-doo, dum-dee-doo"), tunes.melody("dum-dee-doo, dum-dee-doo")
    assert a == b and len(a) == 6 and a[-1][0] == 0, "it comes home at the end"
    assert tunes.melody("la-la-lee") != tunes.melody("bzz-dee-bum")
    msg = tunes.tune_message(["la-dee-dum", "dum-dee-doo"], "calm")
    assert msg["type"] == "tune" and msg["instrument"] == "flute"
    assert {"semi": None, "beats": 2} in msg["notes"], "a breath between two hums"
    assert all(n["semi"] is None or -12 <= n["semi"] <= 12 for n in msg["notes"])
