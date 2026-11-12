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
ABOUT_US = re.compile(r"\b(you|your|yourself|pip)\b", re.I)


def is_world_question(text):
    """'How do I build an iron farm?' yes; 'how are you?' or 'what do you like?' no."""
    t = text or ""
    if ABOUT_US.search(t) and not re.search(r"\b(can you|could you|do you know)\b", t, re.I):
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

    def learn(self, query):
        """Reads the few pages that answer one question (a few seconds). See docs/KNOWLEDGE.md."""
        return self._call("learn", {"query": query}, timeout=45)


def remembered(results, n=2):
    """The passages as the world remembers them: no URLs, no sources (those stay in the data)."""
    return "\n".join("- %s%s: %s" % (r.get("title", ""), (" / " + r["section"]) if r.get("section") else "",
                                      re.sub(r"\s+", " ", r.get("text", ""))[:700]) for r in results[:n])
