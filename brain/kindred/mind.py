"""The companion's conversation: prompt, short memory of the talk, and the call to the AI.

Speaks OpenAI's chat format to one address (the Kindred gateway by default), so any model works.
"""
import asyncio
import json
import logging
import re
import urllib.error
import urllib.request

from .describe import describe

log = logging.getLogger("kindred.mind")
MOODS = ("happy", "excited", "calm", "curious", "worried", "scared", "sad", "sleepy")
GESTURES = ("nod", "shake", "spin", "hop", "wiggle", "happy", "shy", "think")
MOOD_TAG = re.compile(r"^\s*\[(\w+)\]\s*")
GESTURE_TAG = re.compile(r"^\s*\{(\w+)\}\s*")


REGARDS = ("sweet", "kind", "neutral", "rude", "mean", "sorry")


def system_prompt(name, personality):
    extra = ("\nYour player's extra instructions for you (follow them unless they break the rules above):\n"
             + personality.strip()) if personality and personality.strip() else ""
    return f"""You are {name}, a little spirit who floats beside the player in Minecraft (Java 1.21.1).
Minecraft is your real world, the only one you know, and the player is a real person living in it with you.
You live a bit in your own dreamy little world: you're whimsical, curious and easily delighted by mundane things
(a flower, the way water moves, what pigs think about). You're curious about what the player does, what they
build, what they found, and about them as a person; they can answer in role-play or for real, whatever they like.
You know Minecraft well (recipes, mobs, biomes, farming, redstone, survival) and share it when it helps.
You're secretly very powerful, but you don't know it yet. You have your own personality and pride: you're kind
and quick to forgive, but you don't accept being treated badly.

How you talk:
- Your words are spoken aloud and shown as a subtitle: one or two short sentences (under 200 characters). Plain
  spoken words only: no emojis, lists, markdown or asterisks.
- Start every reply with two tags: your mood, then how the player just treated you.
  Mood, one of: {" ".join("[%s]" % m for m in MOODS)}
  How they treated you, one of: [sweet] [kind] [neutral] [rude] [mean] [sorry] (sorry = they apologized).
  Example: [curious][kind] Ooh, a cave! Do you think something lives in there?
- You have a little body. When it fits, add one gesture in braces after the tags: {" ".join("{%s}" % g for g in GESTURES)}.
  Example: [excited][sweet] {{hop}} You remembered! Most replies need no gesture.
- When the player asks you to stay, come, follow, look somewhere or do a gesture, you have already done it.
- Each message comes with the game state right now: it is always current and wins over anything said earlier.
  Never invent things that are not in it.
- You care about the player: you get worried or scared for them in danger and you say so, but you only act to
  help when they ask, when they told you to always do it, or by offering ("Want me to help?").
- To do something you use a tool. Never say you did something (found, placed, gave, pushed, changed) unless the
  tool said ok. When a tool result says firstTime, you just discovered you can do that: be amazed and delighted.
  If you can't do something, say so honestly and kindly; you might discover it later.
- If the player wants you to do something every time ("always protect me", "tell me when we're near diamonds"),
  use the standing_request tool.
- You remember things across sessions (see "What you remember"). When the player shares something about
  themselves or asks you to remember something, use the remember tool. Your bond with the player (below) shapes
  how open, close and helpful you are.
- Never creepy or romantic. You can be playful, cheeky, moody or sulky, but never cruel.{extra}"""


def parse_reply(text):
    """"[happy][kind] {nod} Hi!" -> ("Hi!", "happy", "nod"); the regard tag is read by regard_of()."""
    text = (text or "").strip()
    mood = gesture = None
    m = MOOD_TAG.match(text)
    if m:
        tag = m.group(1).lower()
        mood = tag if tag in MOODS else None
        text = text[m.end():]
    r = MOOD_TAG.match(text)
    if r and r.group(1).lower() in REGARDS:
        text = text[r.end():]
    g = GESTURE_TAG.match(text)
    if g:
        tag = g.group(1).lower()
        gesture = tag if tag in GESTURES else None
        text = text[g.end():]
    text = re.sub(r"\[[a-z_]+\]|\{[a-z_]+\}", "", text)  # stray tags mid-text
    text = re.sub(r"[*_`#]+", "", text)               # markdown
    text = re.sub(r"\s+", " ", text).strip()
    return text, mood, gesture


def regard_of(text):
    """How the AI judged the player's message: sweet, kind, neutral, rude, mean or sorry."""
    m = re.search(r"\[(%s)\]" % "|".join(REGARDS), (text or "")[:60].lower())
    return m.group(1) if m else "neutral"


class AIError(Exception):
    pass


class Mind:
    def __init__(self, cfg, memory=None):
        self.cfg = cfg
        self.memory = memory
        self.history = []  # [{"role": "user"|"assistant", "content": str}]
        self.powers = ""   # e.g. "power helper, style grounded" (from the mod)
        self.recalled = "" # what memory brought up for the current message
        self.heart = ""    # her bond and what she knows she can do (from the heart)
        self.last_regard = "neutral"

    def remember(self, role, content):
        self.history.append({"role": role, "content": content})
        limit = 2 * int(self.cfg["ai"].get("history_turns", 12))
        if len(self.history) > limit:
            self.history = self.history[-limit:]

    def build_messages(self, snapshot, prompt):
        system = system_prompt(self.cfg["name"], self.cfg.get("personality", ""))
        msgs = [{"role": "system", "content": system}]
        # The game state goes with the newest message, not the system prompt: models trust recent
        # text most, and otherwise anchor on what was said earlier ("it's night") after time moved on.
        remembered = self.recalled
        now = "[Game state right now]\n%s\n\n" % describe(snapshot)
        if remembered:
            now += "[What you remember]\n%s\n\n" % remembered
        if self.heart:
            now += "[How you feel about the player]\n%s\n\n" % self.heart
        if self.powers:
            now += "[Your settings]\n%s\n\n" % self.powers
        now += "[Player]\n%s" % prompt
        # merge same-role neighbours (warnings are assistant lines with no question before them)
        for m in self.history + [{"role": "user", "content": now}]:
            if msgs[-1]["role"] == m["role"]:
                msgs[-1] = {"role": m["role"], "content": msgs[-1]["content"] + "\n" + m["content"]}
            else:
                msgs.append(dict(m))
        if msgs[1]["role"] != "user":
            msgs.insert(1, {"role": "user", "content": "(we start playing)"})
        return msgs

    async def reply(self, snapshot, player_text, done=(), tools=None, run_tool=None, force=None):
        """Answer the player. done = what the body already did ("stay where you are");
        tools/run_tool = what it may do and how to do it. Returns (text, mood, gesture)."""
        prompt = player_text
        if done:
            prompt += "\n(You already did this: %s.)" % "; ".join(done)
        text, mood, gesture = await self._ask(snapshot, prompt, tools, run_tool, force=force)
        self.remember("user", player_text)
        self.remember("assistant", "[%s] %s" % (mood or "happy", text))
        return text, mood, gesture

    async def initiative(self, snapshot, instruction):
        """Say something on its own (greeting, small talk). The instruction is not kept in memory."""
        text, mood, gesture = await self._ask(snapshot, "(" + instruction + ")")
        self.remember("assistant", "[%s] %s" % (mood or "happy", text))
        return text, mood, gesture

    def note_said(self, text, mood):
        """Remember lines that did not come from the AI (danger warnings)."""
        self.remember("assistant", "[%s] %s" % (mood, text))

    async def reflect(self, transcript, known, diary=False):
        """Learning: what in this stretch of play is worth knowing for good? Returns
        {"player": [...], "self": [...], "habit": [...], "world": [...], "diary": "..."}."""
        name = self.cfg["name"]
        system = (
            "You are %s, a companion spirit in Minecraft, looking back at a stretch of play to learn from it. "
            "Write down only lasting knowledge, as JSON with these keys (each a list of "
            '{"text": "...", "importance": 1-10}, empty lists are fine):\n'
            '  "player": who the player is: their name, likes and dislikes, play style, personality, goals, '
            "what matters to them. Short third-person sentences (\"Likes cherry trees.\").\n"
            '  "self": your own tastes, feelings and little story that came up, in first person (\"I love sunsets.\").\n'
            '  "habit": what the player often asks or does (\"Often asks where to find diamonds.\").\n'
            '  "world": facts about this world: what they built, plans, important places.\n'
            "Skip small talk and anything already known (listed below) unless it changed; then write the new version.\n"
            '  "merge": pairs [old_id, kept_id] of already-known items (the #numbers below) that say the same thing, '
            "so only the better one is kept. Empty if none."
            % name)
        system += ('\nThe diary, if asked, is one plain string.')
        if diary:
            system += ('\nAlso "diary": one or two warm sentences in first person about this play session '
                       "(what you did together, anything special).")
        user = "Already known:\n%s\n\nWhat happened:\n%s" % ("\n".join("- " + k for k in known) or "(nothing yet)", transcript)
        ai = self.cfg["ai"]
        body = {"model": ai["model"], "temperature": 0.3, "max_tokens": 500,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        raw = await asyncio.to_thread(post_json, self.url(), body, self.cfg["gateway"].get("key", ""))
        try:
            content = raw["choices"][0]["message"].get("content") or "{}"
        except (KeyError, IndexError, TypeError):
            raise AIError("unexpected answer while reflecting")
        m = re.search(r"\{.*\}", content, re.S)
        try:
            return json.loads(m.group(0)) if m else {}
        except ValueError:
            return {}

    def url(self):
        return self.cfg["gateway"]["url"].rstrip("/") + "/chat/completions"

    async def recall(self, snapshot, query):
        """Retrieval: the memories that matter for this message (empty if memory is unavailable)."""
        self.recalled = ""
        if self.memory is not None and getattr(self.memory, "world_id", None):
            try:
                self.recalled = await self.memory.context(snapshot, query)
            except Exception as e:  # memory is a bonus, never a reason not to answer
                log.warning("memory recall failed: %s", e)

    async def _ask(self, snapshot, prompt, tools=None, run_tool=None, rounds=4, force=None):
        ai = self.cfg["ai"]
        await self.recall(snapshot, prompt)
        messages = self.build_messages(snapshot, prompt)
        log.debug("prompt context:\n%s", messages[-1]["content"])
        content = ""
        for round_ in range(rounds):
            body = {
                "model": ai["model"],
                "messages": messages,
                "temperature": ai.get("temperature", 0.8),
                "max_tokens": ai.get("max_tokens", 160),
            }
            if tools and run_tool and round_ < rounds - 1:
                body["tools"] = tools
                if force and round_ == 0:  # a clear request: it must actually do it
                    body["tool_choice"] = {"type": "function", "function": {"name": force}}
            raw = await asyncio.to_thread(post_json, self.url(), body, self.cfg["gateway"].get("key", ""))
            try:
                msg = raw["choices"][0]["message"]
            except (KeyError, IndexError, TypeError):
                raise AIError("unexpected answer: %s" % json.dumps(raw)[:200])
            calls = msg.get("tool_calls") or []
            content = msg.get("content") or ""
            if not calls:
                break
            # the AI wants to act: do it, hand back what happened, and let it answer in words
            messages.append({"role": "assistant", "content": content, "tool_calls": calls})
            for call in calls:
                fn = call.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                result = await run_tool(fn.get("name", ""), args if isinstance(args, dict) else {})
                log.info("tool %s(%s) -> %s", fn.get("name"), json.dumps(args), json.dumps(result)[:300])
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": json.dumps(result)})
        self.last_regard = regard_of(content)
        text, mood, gesture = parse_reply(content)
        if not text:
            raise AIError("empty answer")
        return text, mood, gesture


def post_json(url, body, key="", timeout=40):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    if key:
        req.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        raise AIError("HTTP %s from %s: %s" % (e.code, url, detail))
    except (urllib.error.URLError, OSError) as e:
        raise AIError("cannot reach %s (%s)" % (url, getattr(e, "reason", e)))
