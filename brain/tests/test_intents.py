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


def test_stop_guiding():
    assert acts("ok you can stop now") == [{"move": "stop"}]
    assert acts("we're here, thanks") == [{"move": "stop"}]


def test_plain_questions_do_nothing():
    assert acts("how do I find diamonds?") == []
    assert acts("what's around me?") == []


def test_clear_requests_require_their_tool():
    from kindred.intents import action_hint
    allowed = ["place_torch", "protect", "find_ore", "locate", "guide", "give_item"]
    assert action_hint("It's dark, can you place a torch?", allowed) == "place_torch"
    assert action_hint("help, push these zombies away!", allowed) == "protect"
    assert action_hint("any diamonds near me?", allowed) == "find_ore"
    assert action_hint("where is the nearest village?", allowed) == "locate"
    assert action_hint("can you take me there?", allowed) == "guide"
    assert action_hint("give me 5 bread", allowed) == "give_item"
    assert action_hint("give me 5 bread", ["find_ore"]) is None, "not allowed: the AI explains instead"
    assert action_hint("how do I craft a torch?", allowed) is None
