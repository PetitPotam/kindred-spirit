from kindred.intents import match


def acts(text):
    return match(text)[0]


def test_moving():
    assert acts("Pip, stay here please") == [{"move": "stay"}]
    assert acts("come here!") == [{"move": "come"}]
    assert acts("ok follow me") == [{"move": "follow"}]
    assert acts("float on my left") == [{"side": "left"}]
    assert acts("go to the right") == [{"side": "right"}]
    assert acts("stay away from creepers") == [], "not a command to stay"


def test_looking_and_gestures():
    assert acts("look at me") == [{"look": "me", "seconds": 4}]
    assert acts("look at that!") == [{"look": "there", "seconds": 4}]
    assert acts("can you do a spin?") == [{"emote": "spin"}]
    assert acts("dance for me") == [{"emote": "wiggle"}]


def test_several_at_once_but_one_of_each_kind():
    a = acts("come here and look at me, then do a spin and jump")
    assert {"move": "come"} in a and {"look": "me", "seconds": 4} in a
    assert len([x for x in a if "emote" in x]) == 1


def test_plain_questions_do_nothing():
    assert acts("how do I find diamonds?") == []
    assert acts("what's around me?") == []
