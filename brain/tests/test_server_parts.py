from kindred.server import sentences


def test_sentences_stream_in_useful_pieces():
    assert sentences("Oh! A creeper is right behind you. Run away now!") == [
        "Oh! A creeper is right behind you.", "Run away now!"]
    assert sentences("One short line") == ["One short line"]
    assert sentences("Hi. Yes. No.") == ["Hi. Yes. No."]


def test_speech_cleaner_cleans_one_line():
    import importlib.util
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "..", "services", "speech_cleaner.py")
    spec = importlib.util.spec_from_file_location("speech_cleaner", path)
    sc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sc)
    assert sc.clean(" Hey Pip\nwhat now? [BLANK_AUDIO]") == "Hey Pip what now?"
    assert sc.clean("Where is iron? What should I do first? What should I do first?") == \
        "Where is iron? What should I do first?"
    assert len(sc.clean("a" * 400)) == 256
