from kindred import intents
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


def test_asking_her_to_build_but_not_talking_about_your_own_building():
    allowed = ["build", "harvest", "place_torch"]
    assert intents.action_hint("can you place 10 blocks on top of each other on each corner", allowed) == "build"
    assert intents.action_hint("pip, build a pillar 10 blocks high", allowed) == "build"
    assert intents.action_hint("could you make a floor of planks here", allowed) == "build"
    assert intents.action_hint("i'm going to build a wall", allowed) is None, "that's them building, not a request"
    assert intents.action_hint("build a wall here", ["harvest"]) is None, "not when she can't"


def test_a_trip_home_is_not_pushing_monsters_away_and_one_block_is_not_a_field():
    """Found by the eval set (brain/evals): "can you get me back to the house?" was forced to protect (the
    "get ... back" rule) and "remove this block" to clearing land with no size."""
    a = ["protect", "guide", "harvest", "build", "command", "give_item"]
    assert intents.action_hint("Can you get me back to the house? Oh, the whole house.", a) == "guide"
    assert intents.action_hint("take us home", a) == "guide"
    assert intents.action_hint("get them away from me", a) == "protect"
    assert intents.action_hint("push them back", a) == "protect"
    assert intents.action_hint("get me some bread", a) == "give_item"
    assert intents.action_hint("Can you remove this block for me please?", a) == "harvest"
    assert intents.action_hint("remove this block and everything around it", a) == "build"
    assert intents.action_hint("flatten the land above y 64", a) == "build"


def test_flat_ground_end_portals_and_farms():
    """From the 2026-11-13 singleplayer session: "take me to a flat plain field" went to locate (a biome),
    and the end portal and the crop farm weren't recognised as building."""
    a = ["find_flat", "build", "locate", "guide", "give_item", "harvest"]
    assert intents.action_hint("Take me to a flat plain field, a flat plain field.", a) == "find_flat"
    assert intents.action_hint("No, it is not flat. I need a flat plane field, please.", a) == "find_flat"
    assert intents.action_hint("find a spot that's flat for my house", a) == "find_flat"
    assert intents.action_hint("Can you create an end portal for me please?", a) == "build"
    assert intents.action_hint("Can you build please a farm here?", a) == "build"
    assert intents.action_hint("Pip, plant some seeds here", a) == "build"
    assert intents.action_hint("could you make a wheat farm", a) == "build"
    assert intents.action_hint("i'm going to make a farm", a) is None, "that's them farming"
    assert intents.action_hint("Take me to a flat field", ["guide"]) != "find_flat", "not when she can't"
