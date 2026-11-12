"""What the world remembers: the Minecraft knowledge base (services/knowledge, docs/KNOWLEDGE.md),
as Pip uses it.

To her it isn't a wiki: it's what her world remembers (the old stones, the wind over every village).
When you ask how something in the world works, the brain looks first. If the world remembers it,
she answers from that; if not, she says she'll listen, the brain learns it in the background, and
she comes back with what the stones told her.
"""
import json
import re
import urllib.error
import urllib.request

# questions about how the world works (not about her, or you)
HOW = re.compile(
    r"\b(how (do|does|can|to|should|would)|what('s| is| are| do| does)|where (do|does|can|is|are)|which|can i|"
    r"is there|tell me about|explain)\b", re.I)
WORLD = re.compile(
    r"\b(craft|crafting|recipe|make|build|farm|breed|tame|spawn|smelt|brew|potion|enchant|redstone|piston|"
    r"repeater|comparator|hopper|golem|villager|trade|nether|portal|end|stronghold|elytra|beacon|anvil|mine|"
    r"ore|diamond|netherite|iron|gold|seed|grow|plant|crop|food|eat|biome|mob|creeper|zombie|skeleton|enderman|"
    r"wither|dragon|warden|horse|wolf|cat|axolotl|bee|sheep|cow|pig|chicken|fish|boat|rail|minecart|bed|"
    r"armor|sword|pickaxe|axe|shovel|bow|crossbow|trident|shield|map|compass|clock|book|lectern|furnace|"
    r"chest|torch|lantern|glass|concrete|terracotta|wool|dye|block|item)s?\b", re.I)
ABOUT_US = re.compile(r"\b(you|your|yourself|pip|my|mine|our|coordinates?|where am i|where are we)\b", re.I)


def is_world_question(text):
    """'How do I build an iron farm?' yes; 'how are you?' or 'what do you like?' no. Several
    sentences are judged one by one: "That thing ignored me. Can you tell me please?" is not one."""
    sentences = [x for x in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if x.strip()]
    if len(sentences) > 1:
        return any(_world_sentence(x) for x in sentences)
    return _world_sentence(text)


# "can you place this block for me?" asks her to do something (her powers), not how the world works
REQUEST = re.compile(r"^\W*(please )?(can|could|would|will) you (please )?(?!(tell|show|explain|teach|remind)\b)\w+",
                     re.I)


def _world_sentence(text):
    t = text or ""
    if REQUEST.search(t) and not re.search(r"\b(how|what|where|which|why|when)\b", t, re.I):
        return False
    if ABOUT_US.search(t) and not re.search(r"\b(can|could) you (tell|show|explain|teach|remind|help)\b|"
                                            r"\bdo you know (how|what|where|which|why)\b", t, re.I):
        return False
    if re.search(r"\bhow (do|does) (i|we|it|this|that) (look|seem|feel|sound)\b", t, re.I):
        return False  # "how do I look?" is about you, not about the world
    howto = re.search(r"\b(how (do|does|can|to|should) (i|we|you|it|they|one|a|an|the)?|what (is|are|does|do) (a|an|the)?|"
                      r"where (do|does|can) (i|we|you)? ?(find|get)?|what'?s the (recipe|way|best))\b", t, re.I)
    # the knowledge base itself says whether it's covered; this only keeps chit-chat out
    return bool(howto) or bool((HOW.search(t) or t.strip().endswith("?")) and WORLD.search(t))


class Knowledge:
    def __init__(self, cfg):
        self.base = cfg["gateway"]["url"].rstrip("/") + "/knowledge/"
        self.key = cfg["gateway"].get("key", "")

    def _call(self, op, body, timeout):
        req = urllib.request.Request(self.base + op, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        if self.key:
            req.add_header("Authorization", "Bearer " + self.key)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, OSError, ValueError) as e:
            return {"error": str(getattr(e, "reason", e))}

    def search(self, query, k=3):
        """{"covered": bool, "results": [...]} (covered False and an "error" when it isn't there)."""
        r = self._call("search", {"query": query, "k": k, "max_chars": 900}, timeout=5)
        r.setdefault("covered", False)
        r.setdefault("results", [])
        return r

    def section(self, chunk_id=None, page=None, name=None, start=0):
        """A whole section of a guide, in order (see services/knowledge/store.py section())."""
        return self._call("section", {"chunk_id": chunk_id, "page": page, "name": name, "start": start,
                                      "max_chars": 4500}, timeout=5)

    def learn(self, query):
        """Reads the few pages that answer one question (a few seconds). See docs/KNOWLEDGE.md."""
        return self._call("learn", {"query": query}, timeout=45)


HOWTO = re.compile(r"\b(how (do|can|to|should) (i|we|you)? ?(build|make|craft|farm|get|breed|set up|start|grow|"
                   r"automate|design)|build|farm|tutorial|step|guide|design|setup|set up|automatic)\b", re.I)


def best_guide(results):
    """The best result that is current (not about an older version), else the best one."""
    return next((r for r in results if not r.get("outdated")), results[0] if results else None)


def as_guide(sec):
    """A whole section of a guide, for her: in order, with where it goes on (no URL)."""
    head = "%s / %s (part %d to %d of %d)" % (sec.get("title"), sec.get("section"), sec.get("part", 1),
                                           (sec.get("next_start") or sec.get("parts", 1)), sec.get("parts", 1))
    more = []
    if sec.get("more"):
        more.append("it goes on in this section")
    if sec.get("next_section"):
        more.append("next section: %s" % sec["next_section"])
    tail = ("\n(%s: listen more to hear it.)" % "; ".join(more)) if more else ""
    outline = ", ".join(s for s in (sec.get("outline") or [])[:14] if s)
    return "%s:\n%s%s\n(This guide's parts: %s.)" % (head, sec.get("text", ""), tail, outline)


def elsewhere(r):
    """Why a passage isn't about the player's world, for the AI (never her words), or ""."""
    st = r.get("status") or ("outdated" if r.get("outdated") else "current")
    if st == "future":
        return "not in this world: it came later%s, after the player's version" % (
            " (Java %s)" % r["since"] if r.get("since") else "")
    return {"outdated": "how it worked in an older version", "removed": "no longer in the world",
            "other-edition": "only in another edition, not in this world", "joke": "an April Fools joke, not real",
            "spin-off": "from another game, not this world"}.get(st, "")


def not_in_this_world(results):
    """When the best match is the very thing asked about but it isn't in the player's world (the
    Happy Ghast for a 1.21.1 player): what to tell the AI, so she says it isn't here rather than
    listening for it. "" otherwise."""
    top = results[0] if results else None
    if not top or top.get("title_match", 0) < 1 or not elsewhere(top) or top.get("status") == "outdated":
        return ""
    return "%s: %s." % (re.sub(r"\s*\(.*?\)$", "", top.get("title", "")), elsewhere(top))


def remembered(results, n=2):
    """The passages as the world remembers them: no URLs, no sources (those stay in the data). A
    passage that isn't about this world says so."""
    out = []
    for r in results[:n]:
        why = elsewhere(r)
        out.append("- %s%s%s: %s" % (r.get("title", ""), (" / " + r["section"]) if r.get("section") else "",
                                     (" (%s)" % why) if why else "", re.sub(r"\s+", " ", r.get("text", ""))[:700]))
    return "\n".join(out)
