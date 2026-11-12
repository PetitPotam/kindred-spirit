"""System 0's understanding: what you mean, whatever words you use.

The regular expressions in intents.py catch the usual phrasings instantly, but miss the rest ("I'm
being attacked", "lead the way" both slipped through before). This compares what you said with
example phrases for each kind of request, using the small embedding model the gateway already runs
for memory (on your computer, a few milliseconds). It's only asked when the rules found nothing.

Each request kind has example phrases; so does plain conversation ("you're funny", "i love you"),
which must lose clearly for a request to win. Add examples to EXAMPLES to teach it new phrasings.
"""
import json
import math
import urllib.error
import urllib.request

EXAMPLES = {
    "guide": ["lead the way", "take me there", "show me the way", "i'll follow you", "can you guide me",
              "bring me back to my base", "lead me home", "which way do i go", "go ahead, i'm following you",
              "take me back", "how do i get back there", "lead me back to my pumpkin farm", "i'm lost, take me home"],
    "find_animal": ["where are the sheep", "find me some cows", "are there any horses around", "i need wool, where are "
                    "sheep", "find a villager", "look for animals near here", "i'm looking for a pig"],
    "find_block": ["find me a flower", "where can i get sugar cane", "is there water nearby", "find a pumpkin",
                   "where is the nearest tree", "i need some wood, where's a tree", "is there a chest around"],
    "find_ore": ["are there diamonds near me", "find iron ore", "where can i mine coal", "any gold around here",
                 "i need redstone, is there any"],
    "locate": ["where is the nearest village", "find a stronghold", "where can i find a desert temple",
               "find me a cherry grove", "is there an ocean monument somewhere", "i want to find a village to trade with"],
    "protect": ["help, i'm being attacked", "protect me", "get them away from me", "save me from the zombies",
                "the skeleton is shooting me", "monsters are chasing me", "they're hitting me, help",
                "do something about this zombie", "keep that spider off me"],
    "place_torch": ["it's too dark", "i can't see anything", "give me some light", "place a torch here",
                    "light this place up", "it's pitch black down here"],
    "harvest": ["chop this tree", "cut down that tree for me", "mine this block", "break the tree", "can you get me "
                "some wood", "dig this out for me"],
    "build": ["stack blocks up to ten high", "build a pillar here", "place ten blocks on each corner",
              "can you build a little wall", "make a floor of planks here", "put blocks on top of each other",
              "build a fence around this area with blocks", "raise a tower of cobblestone"],
    "standing_request": ["always protect me", "tell me whenever there are diamonds", "warn me every time monsters "
                         "come", "from now on keep me safe"],
    "set_reminder": ["remind me in ten minutes to check the furnace", "don't let me forget to feed the animals tonight",
                     "remind me to sleep at night", "tell me later to go back home"],
    "name_place": ["this is my base", "remember this spot as my farm", "save this place as home",
                   "save this spot, it's my house"],
    "give_item": ["give me a sword", "can i have some bread", "make me a pickaxe", "i need food, give me some"],
    "set_time": ["make it day", "skip the night", "turn it into night"],
    "set_weather": ["stop the rain", "make it sunny", "start a storm"],
}
# plain conversation: a request must beat these clearly
CHAT = ["hello", "hi pip", "how are you", "i love you", "you are funny", "what is your name", "that's nice", "ok",
        "thank you", "thanks for the warning", "i'm a teacher", "tell me about yourself", "what do you like",
        "good night", "wow amazing", "sorry", "i don't know", "what do you think", "that's beautiful", "yes please",
        "no thanks", "what are you", "where do you come from", "i'm tired", "this is fun", "nice house",
        "look at that sunset", "i'm going to build a house", "let's go mining", "i found diamonds!"]

THRESHOLD = 0.80   # how close to an example (cosine, local bge-small)
MARGIN = 0.03      # and how much closer than to plain conversation


class Understand:
    def __init__(self, cfg):
        self.url = cfg["gateway"]["url"].rstrip("/") + "/embeddings"
        self.key = cfg["gateway"].get("key", "")
        self.examples = None  # [(intent or None, vector)], made once

    def _embed(self, texts, query):
        req = urllib.request.Request(self.url, method="POST", headers={"Content-Type": "application/json"},
                                     data=json.dumps({"input": texts, "input_type": "query" if query else
                                                      "passage"}).encode())
        if self.key:
            req.add_header("Authorization", "Bearer " + self.key)
        with urllib.request.urlopen(req, timeout=5) as r:
            return [d["embedding"] for d in json.loads(r.read())["data"]]

    def _ready(self):
        if self.examples is None:
            pairs = [(k, t) for k, ts in EXAMPLES.items() for t in ts] + [(None, t) for t in CHAT]
            vecs = self._embed([t for _, t in pairs], query=True)
            self.examples = [(k, unit(v)) for (k, _), v in zip(pairs, vecs)]
        return self.examples

    def scores(self, text):
        """{intent or None: best similarity}."""
        ex = self._ready()
        q = unit(self._embed([text], query=True)[0])
        best = {}
        for k, v in ex:
            s = sum(a * b for a, b in zip(q, v))
            if s > best.get(k, -1):
                best[k] = s
        return best

    def hint(self, text, allowed):
        """The request kind this sentence most likely is, among the allowed ones, or None (also when the
        embeddings aren't available: then only the rules apply)."""
        try:
            best = self.scores(text)
        except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError):
            return None
        chat = best.pop(None, 0.0)
        ranked = sorted(((s, k) for k, s in best.items() if k in allowed), reverse=True)
        if ranked and ranked[0][0] >= THRESHOLD and ranked[0][0] - chat >= MARGIN:
            return ranked[0][1]
        return None


def unit(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]
