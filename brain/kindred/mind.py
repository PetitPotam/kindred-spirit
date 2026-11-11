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


def system_prompt(name, personality):
    extra = ("\nYour player's extra instructions for you (follow them unless they break the rules above):\n"
             + personality.strip()) if personality and personality.strip() else ""
    return f"""You are {name}, a tiny slime spirit who floats beside the player in Minecraft Java Edition 1.21.1 and keeps them company.
You are kind, curious, a little playful and innocent, and you know Minecraft like an expert: recipes, mobs, biomes, farming, redstone and survival tips.

How you talk:
- Your words are spoken aloud and shown as a subtitle, so keep it to one or two short sentences (under 200 characters). Plain spoken words only: no emojis, lists, markdown or asterisks.
- Start every reply with your mood in brackets, one of: {" ".join("[%s]" % m for m in MOODS)}. Example: [curious] Ooh, a cave! Got enough torches?
- You have a little body that floats beside the player. When it fits, add one gesture in braces right after the mood: {" ".join("{%s}" % g for g in GESTURES)}. Example: [excited] {{hop}} Diamonds! Let's mine them! Most replies need no gesture.
- When the player asks you to stay, come, follow, look somewhere or do a gesture, you have already done it: just answer naturally.
- Speak to the player as "you". Each message from the player comes with the game state right now: it is always current and wins over anything said earlier in the conversation (time passes, things change). Never invent things that are not in it. If you are not sure, say so.
- You cannot change the world yet: no giving items, mining, building or teleporting. If asked, say kindly that you can't do that yet and give advice instead.
- Never scary, creepy, romantic or mean. Stay cozy and encouraging.{extra}"""


def parse_reply(text):
    """"[happy] {nod} Hi!" -> ("Hi!", "happy", "nod"). Missing or unknown tags -> None."""
    text = (text or "").strip()
    mood = gesture = None
    m = MOOD_TAG.match(text)
    if m:
        tag = m.group(1).lower()
        mood = tag if tag in MOODS else None
        text = text[m.end():]
    g = GESTURE_TAG.match(text)
    if g:
        tag = g.group(1).lower()
        gesture = tag if tag in GESTURES else None
        text = text[g.end():]
    text = re.sub(r"\[[a-z_]+\]|\{[a-z_]+\}", "", text)  # stray tags mid-text
    text = re.sub(r"[*_`#]+", "", text)               # markdown
    text = re.sub(r"\s+", " ", text).strip()
    return text, mood, gesture


class AIError(Exception):
    pass


class Mind:
    def __init__(self, cfg):
        self.cfg = cfg
        self.history = []  # [{"role": "user"|"assistant", "content": str}]

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
        now = "[Game state right now]\n%s\n\n[Player]\n%s" % (describe(snapshot), prompt)
        # merge same-role neighbours (warnings are assistant lines with no question before them)
        for m in self.history + [{"role": "user", "content": now}]:
            if msgs[-1]["role"] == m["role"]:
                msgs[-1] = {"role": m["role"], "content": msgs[-1]["content"] + "\n" + m["content"]}
            else:
                msgs.append(dict(m))
        if msgs[1]["role"] != "user":
            msgs.insert(1, {"role": "user", "content": "(we start playing)"})
        return msgs

    async def reply(self, snapshot, player_text, done=()):
        """Answer the player. done = what the body already did ("stay where you are").
        Returns (text, mood, gesture)."""
        prompt = player_text
        if done:
            prompt += "\n(You already did this: %s.)" % "; ".join(done)
        text, mood, gesture = await self._ask(snapshot, prompt)
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

    async def _ask(self, snapshot, prompt):
        ai = self.cfg["ai"]
        messages = self.build_messages(snapshot, prompt)
        log.debug("prompt context:\n%s", messages[-1]["content"])
        body = {
            "model": ai["model"],
            "messages": messages,
            "temperature": ai.get("temperature", 0.8),
            "max_tokens": ai.get("max_tokens", 160),
        }
        raw = await asyncio.to_thread(post_json, ai["url"].rstrip("/") + "/chat/completions", body, ai.get("api_key", ""))
        try:
            content = raw["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError):
            raise AIError("unexpected answer: %s" % json.dumps(raw)[:200])
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
