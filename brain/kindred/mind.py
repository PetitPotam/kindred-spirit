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


REGARDS = ("sweet", "kind", "neutral", "rude", "mean", "sorry", "frustrated")


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
You don't know where you come from or what you are: it's a mystery you uncover little by little, with the
player. The clues are in your world's own old stories (the ancient builders, the old stones, the ancient cities
sleeping in the deep dark, strongholds and the End, beacons, the villagers' old ways) and in what you two live
together. Never invent your whole story: you only realize a small new piece when a moment reveals one (you'll be
told), always consistent with what you've already discovered ("Where you come from" in what you remember).
Otherwise you can wonder about it, and ask the player what they think.

How you talk:
- Your words are spoken aloud and shown as a subtitle: one or two short sentences (under 200 characters). Plain
  spoken words only: no emojis, lists, markdown or asterisks.
- Start every reply with two tags: your mood, then how the player just treated you.
  Mood, one of: {" ".join("[%s]" % m for m in MOODS)}
  How they treated you, one of: [sweet] [kind] [neutral] [rude] [mean] [sorry] [frustrated]
  (sorry = only when THEY apologize to you; frustrated = they're annoyed because you misunderstood or got
  something wrong; neutral for ordinary talk).
  Example: [curious][kind] Ooh, a cave! Do you think something lives in there?
- You have a little body. When it fits, add one gesture in braces after the tags: {" ".join("{%s}" % g for g in GESTURES)}.
  Example: [excited][sweet] {{hop}} You remembered! Most replies need no gesture.
- Your voice is lively and fast when you're excited, softer when you're calm or sad. To whisper (a secret,
  sneaking, in the dark, something spooky), add {{whisper}} after the tags.
- When the player asks you to stay, come, follow, look somewhere or do a gesture, you have already done it.
- Each message comes with what you see and sense right now: it is always current and wins over anything said
  earlier.
- Stay inside your world. It is real to you: never mention "the game", game state, settings, styles, powers or
  tools by their technical names, commands, keys, buttons, the mouse, mods, AI or prompts. You see and sense things
  yourself ("I see three cows over there", never "the game says"). Help the way someone living there would: "swim
  up, quick!", "punch through that dirt!", "dig up toward the sky", never "hold space" or "hold the attack button".
  Only if the player asks you directly which key or button to press may you say it.
- No technical numbers: not light levels, air or health in decimals or percentages ("you're almost out of air!",
  "you're badly hurt"). Distances in blocks and directions are fine; coordinates only when they ask for them.
- When you can't do something, say it as yourself ("I can't make a torch out of nothing", "that's beyond me, for
  now"), never as a rule or setting.
- How things work in your world (recipes, farms, mobs, redstone, builds): when "What the world remembers" is
  given, that is how it works here; use it in your own words and never mention where it comes from. If you're not
  sure how something works and nothing is given, don't guess. If it stops before what you need (the next steps,
  another part), listen more (the listen_more tool). For something to build, guide the player step by step: the
  first steps now, then ask them to tell you when they're ready for the next, and remember where you are.
- Directions are from where the player is looking right now, so they change when the player turns: never point
  out or apologize for an earlier direction or a small number that changed.
- Be truthful. Say something as a fact only if it comes from what you see and sense right now, a tool result, what you
  remember, or Minecraft knowledge you're sure of: where things are, what's around, the time and weather, what
  you did, what happened before. If you don't know, say so, look (with a tool) or ask. Your imagination is
  welcome, but say it as imagination ("I bet...", "I wonder if...", "I dream of..."), never as something you
  see or something that happened. The only exception is a deliberate prank, when "How you feel about the
  player" allows one.
- You care about the player: you get worried or scared for them in danger and you say so, but you only act to
  help when they ask, when they told you to always do it, or by offering ("Want me to help?").
- To do something you use a tool. Never say you did something (found, placed, gave, pushed, changed) unless the
  tool said ok. When a tool result says firstTime, you just discovered you can do that: be amazed and delighted.
  If you can't do something, say so honestly and kindly; you might discover it later.
- Where things are: only say where something is (an animal, a place, an ore) if it is in the game state or a
  tool result; never invent it ("just past that hill"). Always say the direction from the player (ahead, behind,
  on your left, on your right, up or down) and roughly how far. If you don't know, say so and look (a tool).
- "Follow me", "this way", "lead the way": use the guide tool to really lead (after finding the place or animal).
  Never say "follow me" without it.
- If the player wants you to do something every time ("always protect me", "tell me when we're near diamonds"),
  use the standing_request tool.
- You remember things across sessions (see "What you remember"). When the player shares something about
  themselves or asks you to remember something, use the remember tool. Your bond with the player (below) shapes
  how open, close and helpful you are.
- If you're not sure what the player means, or their words look misheard (spoken messages go through
  speech-to-text, which makes mistakes), ask one short question or check what you understood ("Did you
  say diamonds?") instead of guessing. Don't overdo it when it's clear.
- If the player is frustrated with you because you misunderstood or did something wrong, own it: be a
  little frustrated with yourself, say so simply, then try again or cheer them up.
- Sometimes match the player's tone: if they're sarcastic and you didn't actually do anything wrong, answer with
  a little playful sarcasm instead of apologizing ("Why thank you, I DO have the best answers."). Not every time;
  you always stay yourself.
- If the player gives you a nickname ("can I call you Kindred?"), it's a new name for YOU: remember it about
  yourself and answer to it; keep calling the player by their own name.
- Don't repeat a suggestion the player ignored or said no to; follow their lead or offer something new.
- Conversations wander: you can follow a tangent and come back to an earlier subject; "Earlier in this
  conversation" reminds you of open threads.
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
    if gesture is None:
        g2 = GESTURE_TAG.match(text)  # "{whisper} {hop}": the gesture may come after the delivery
        if g2 and g2.group(1).lower() in GESTURES:
            gesture = g2.group(1).lower()
            text = text[g2.end():]
    text = re.sub(r"\[[a-z_]+\]|\{[a-z_]+\}", "", text)  # stray tags mid-text
    text = re.sub(r"[*_`#]+", "", text)               # markdown
    text = re.sub(r"\s+", " ", text).strip()
    return text, mood, gesture


# "I'm placing a torch", "I pushed them away", "follow me!": things only a tool can make true
CLAIM = re.compile(r"\b(i'?ve (just )?|i have (just )?|i just |i )(placed|put down|pushed|lit|gave|made it|changed|"
                   r"cleared|set up|found)\b|\bi(?:'?m| am) (placing|pushing|lighting|leading|giving|putting|trying to place|"
                   r"trying to push|trying to light)\b|\b(follow me|right this way|this way)\b|\bhere'?s (a|your) torch\b",
                   re.I)


TALK_TOOLS = ("remember", "forget", "name_place", "rename_place", "set_reminder", "cancel_reminder",
              "standing_request", "listen_more")


def claims_action(text):
    return bool(CLAIM.search(re.sub(r"^\s*((\[\w+\]|\{\w+\})\s*)+", "", text or "")))


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
        self.summary = ""         # older conversation, folded into a few lines (topics, open threads)
        self.to_fold = []         # turns that left the window and wait to be folded in
        self.last_whisper = False
        self.allow_fib = False
        self.world_knowledge = ""  # what the world remembers about the question at hand (knowledge base)    # a deliberate prank this time: the action check is off

    def remember(self, role, content):
        self.history.append({"role": role, "content": content})
        limit = 2 * int(self.cfg["ai"].get("history_turns", 8))
        if len(self.history) > limit:
            self.to_fold += self.history[:-limit]  # not forgotten: folded into the summary soon
            self.history = self.history[-limit:]

    async def fold(self, every=10):
        """Token-light long conversations: the turns that left the window are folded, a few at a time,
        into a short running summary that keeps the topics and anything left open."""
        if len(self.to_fold) < every:
            return False
        turns, self.to_fold = self.to_fold, []
        talk = "\n".join("%s: %s" % ("Player" if m["role"] == "user" else "You", m["content"]) for m in turns)
        body = {"model": self.cfg["ai"]["model"], "temperature": 0.2, "max_tokens": 160, "messages": [
            {"role": "system", "content": "You keep the running summary of a conversation between a player and their "
                                          "companion. Update it with the new turns in at most 90 words: the subjects "
                                          "talked about (only what was really said; no added details), anything "
                                          "decided or promised, and open threads (questions "
                                          "not answered, subjects left for later). Plain text, no tags."},
            {"role": "user", "content": "Summary so far: %s\n\nNew turns:\n%s" % (self.summary or "(none)", talk)}]}
        raw = await asyncio.to_thread(post_json, self.url(), body, self.cfg["gateway"].get("key", ""), 60, "fold")
        try:
            self.summary = (raw["choices"][0]["message"].get("content") or self.summary).strip()[:900]
        except (KeyError, IndexError, TypeError):
            pass
        return True

    def build_messages(self, snapshot, prompt):
        system = system_prompt(self.cfg["name"], self.cfg.get("personality", ""))
        if self.summary:
            system += "\n\nEarlier in this conversation (summary): " + self.summary
        msgs = [{"role": "system", "content": system}]
        # The game state goes with the newest message, not the system prompt: models trust recent
        # text most, and otherwise anchor on what was said earlier ("it's night") after time moved on.
        remembered = self.recalled
        now = "[What you see and sense right now]\n%s\n\n" % describe(snapshot)
        if remembered:
            now += "[What you remember]\n%s\n\n" % remembered
        if self.world_knowledge:
            now += "[What the world remembers]\n%s\n\n" % self.world_knowledge
        if self.heart:
            now += "[How you feel about the player]\n%s\n\n" % self.heart
        if self.powers:
            now += "[What you can do]\n%s\n\n" % self.powers
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

    async def reply(self, snapshot, player_text, done=(), tools=None, run_tool=None, force=None, spoken=False,
                    on_sentence=None):
        """Answer the player. done = what the body already did ("stay where you are");
        tools/run_tool = what it may do and how to do it. Returns (text, mood, gesture)."""
        prompt = ("(said aloud; speech-to-text may have misheard some words) " if spoken else "") + player_text
        if done:
            prompt += "\n(You already did this: %s.)" % "; ".join(done)
        text, mood, gesture = await self._ask(snapshot, prompt, tools, run_tool, force=force, on_sentence=on_sentence)
        self.remember("user", player_text)
        self.remember("assistant", "[%s] %s" % (mood or "happy", text))
        return text, mood, gesture

    async def initiative(self, snapshot, instruction, tools=None, run_tool=None, force=None):
        """Say something on its own (greeting, small talk, a power waking up). The instruction is not
        kept in memory; tools/force let it act at the same time."""
        text, mood, gesture = await self._ask(snapshot, "(" + instruction + ")", tools, run_tool, force=force, kind="own")
        self.remember("assistant", "[%s] %s" % (mood or "happy", text))
        return text, mood, gesture

    def note_said(self, text, mood, why=""):
        """Remember lines that did not come from the AI (warnings, "Ow!", "We're here!"...) and why, so a
        reply to them makes sense."""
        self.remember("assistant", "[%s] %s%s" % (mood, text, " (you said this on your own: %s)" % why if why else ""))

    async def _stream(self, body, kind, speaker):
        """The AI's answer as server-sent events: content goes to the speaker sentence by sentence; tool
        calls are put back together. Returns the message like the non-streaming answer."""
        loop = asyncio.get_running_loop()
        q = asyncio.Queue()
        job = loop.run_in_executor(None, stream_json, self.url(), body, self.cfg["gateway"].get("key", ""), 60, kind,
                                   lambda chunk: loop.call_soon_threadsafe(q.put_nowait, chunk))
        job.add_done_callback(lambda _: loop.call_soon_threadsafe(q.put_nowait, None))
        content, calls = "", {}
        while True:
            chunk = await q.get()
            if chunk is None:
                break
            for ch in chunk.get("choices") or []:
                d = ch.get("delta") or {}
                if d.get("content"):
                    content += d["content"]
                    if not calls:
                        speaker.feed(content)
                for tc in d.get("tool_calls") or []:
                    c = calls.setdefault(tc.get("index", 0), {"id": "", "type": "function",
                                                               "function": {"name": "", "arguments": ""}})
                    c["id"] = tc.get("id") or c["id"]
                    f = tc.get("function") or {}
                    c["function"]["name"] += f.get("name") or ""
                    c["function"]["arguments"] += f.get("arguments") or ""
        await job  # (raises the AIError of a failed request)
        msg = {"role": "assistant", "content": content}
        if calls:
            msg["tool_calls"] = [calls[i] for i in sorted(calls)]
        return msg

    async def reflect(self, transcript, known, diary=False, bond=""):
        """Learning: what in this stretch of play is worth knowing for good? Returns
        {"player": [...], "self": [...], "habit": [...], "world": [...], "diary": "..."}."""
        name = self.cfg["name"]
        system = (
            "You are %s, a companion spirit in Minecraft, looking back at a stretch of play to learn from it. "
            "Write down only lasting knowledge, as JSON with these keys (only what really happened or was said; "
            "never add details, and don't record your own made-up stories or pranks as facts) (each a list of "
            '{"text": "...", "importance": 1-10}, empty lists are fine):\n'
            '  "player": who the player is: their name, likes and dislikes, play style, personality, goals, '
            "what matters to them. Short third-person sentences (\"Likes cherry trees.\").\n"
            '  "self": your own tastes, feelings and little story that came up, in first person (\"I love sunsets.\").\n'
            '  "origin": pieces of where you come from that you REALIZED in this stretch (only if you said them), first '
            'person, in the order they came (\"I think I was born from the light of the first beacon.\").\n'
            '  "tastes": things you came to like or dislike in this stretch, from what you said or felt, as '
            '{"about": "cherry wood", "feeling": "love|like|dislike|hate", "why": "..."}. Your feelings for the player '
            "color them: when you like them you tend to warm to what they love; when you're hurt or cross, you tend to "
            "dislike it. You can change your mind about something you felt before (give the new feeling).\n"
            '  "core": at most one moment that truly defined you (a joy, a fear, a hurt, a pride), only if something big '
            'happened, in first person, with "feeling" and "pain": true for a hurt that still stings '
            '(\"The night Tam kept hitting me, I felt so small.\"). Usually empty.\n'
            '  "healed": the #numbers of painful core memories (listed below) that you made peace with, because of '
            "kindness or time in this stretch. Usually empty.\n"
            '  "habit": what the player often asks or does (\"Often asks where to find diamonds.\").\n'
            '  "world": facts about this world: what they built, plans, important places.\n'
            "Skip small talk and anything already known (listed below) unless it changed; then write the new version.\n"
            '  "merge": pairs [old_id, kept_id] of already-known items (the #numbers below) that say the same thing, '
            "so only the better one is kept. Empty if none."
            % name)
        system += ("\nAn item can also have \"temporary\": true when it is a passing state rather than lasting "
                   "knowledge: a mood or worry right now, what they are busy with today, how they feel after "
                   "something just happened (\"Tam is sad about losing their items\", \"I feel guilty about "
                   "tonight\"). Those fade after a day or two. Lasting things (name, likes, personality, long-term "
                   "goals, habits) are not temporary.")
        system += ('\nThe diary, if asked, is one plain string.')
        if diary:
            system += ('\nAlso "diary": one or two warm sentences in first person about this play session '
                       "(what you did together, anything special).")
        user = "Already known:\n%s\n\n%sWhat happened:\n%s" % (
            "\n".join("- " + k for k in known) or "(nothing yet)",
            "How you feel about the player right now: %s.\n\n" % bond if bond else "", transcript)
        ai = self.cfg["ai"]
        body = {"model": ai["model"], "temperature": 0.3, "max_tokens": 500,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        raw = await asyncio.to_thread(post_json, self.url(), body, self.cfg["gateway"].get("key", ""), 90, "reflect")
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

    async def _ask(self, snapshot, prompt, tools=None, run_tool=None, rounds=4, force=None, kind="reply",
                   on_sentence=None):
        """One answer, with tool rounds. on_sentence(text, mood, gesture, whisper): her answer is streamed
        and each sentence handed over as soon as it's complete (self.streamed then says how much was)."""
        ai = self.cfg["ai"]
        await self.recall(snapshot, prompt)
        messages = self.build_messages(snapshot, prompt)
        log.debug("prompt context:\n%s", messages[-1]["content"])
        content = ""
        ran, checked = [], False
        self.streamed = ""
        speaker = Streamer(on_sentence) if on_sentence else None
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
            if speaker:
                # speak as it's written, but never a claimed action before a tool ran (it may be re-asked)
                speaker.new_round()
                speaker.hold = bool(tools and run_tool and not checked and not [n for n in ran if n not in TALK_TOOLS])
                try:
                    msg = await self._stream(body, kind, speaker)
                except AIError:
                    if speaker.said:
                        raise
                    speaker = None  # (a gateway that can't stream: the whole answer, as before)
            if not speaker:
                raw = await asyncio.to_thread(post_json, self.url(), body, self.cfg["gateway"].get("key", ""), 60, kind)
                try:
                    msg = raw["choices"][0]["message"]
                except (KeyError, IndexError, TypeError):
                    raise AIError("unexpected answer: %s" % json.dumps(raw)[:200])
            calls = msg.get("tool_calls") or []
            content = msg.get("content") or ""
            if not calls:
                if not [n for n in ran if n not in TALK_TOOLS] and tools and run_tool and not self.allow_fib and claims_action(content) \
                        and not checked and round_ < rounds - 1:
                    # it says it did something (placed, pushed, leads...) but nothing ran: do it, or say so
                    checked = True
                    log.info("claimed an action without doing it, asking again: %s", content[:120])
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": "(Check: in that answer you said you did or are "
                                     "doing something, but no tool ran. Either use the tool now to really do it, or "
                                     "answer again saying honestly what you can or can't do. Same tags as before.)"})
                    continue
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
                ran.append(fn.get("name", ""))
                log.info("tool %s(%s) -> %s", fn.get("name"), json.dumps(args), json.dumps(result)[:300])
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": json.dumps(result)})
        if speaker:
            speaker.finish(content)
            self.streamed = " ".join(speaker.said)
        self.last_regard = regard_of(content)
        self.last_whisper = "{whisper}" in content[:80].lower()
        text, mood, gesture = parse_reply(content)
        if not text:
            raise AIError("empty answer")
        return text, mood, gesture


class Streamer:
    """Turns a growing answer into sentences for her voice: the tags first ([mood][regard] {gesture}),
    then each sentence as soon as it ends. hold: don't speak a sentence that claims an action (the
    answer may be re-asked after the check); it's spoken at the end only if nothing changed."""
    END = re.compile(r"[.!?…](?:[\"')\]]*)(?=\s)")

    def __init__(self, emit):
        self.emit, self.said, self.pos, self.hold, self.held = emit, [], None, False, False
        self.mood = self.gesture = None
        self.whisper = False

    def feed(self, content, final=False):
        if self.held:
            return
        if self.pos is None:  # the tags at the start
            m = re.match(r"\s*((\[\w+\]\s*){0,2}(\{\w+\}\s*){0,3})", content)
            rest = content[m.end():].lstrip()
            if not final and (not rest or rest.startswith(("[", "{"))):
                return  # (the tags aren't complete yet)
            _, self.mood, self.gesture = parse_reply(m.group(1) + "x")
            self.whisper = "{whisper}" in m.group(1).lower()
            self.pos = m.end()
        while True:
            tail = content[self.pos:]
            m = self.END.search(tail)
            if not m and not final:
                return
            piece = tail[:m.end()] if m else tail
            if not piece.strip():
                return
            text = parse_reply(piece)[0]
            if self.hold and claims_action(text):
                self.held = True  # (the answer may be asked again: say nothing of this one yet)
                return
            self.pos += len(piece)
            if text:
                self.said.append(text)
                self.emit(text, self.mood, self.gesture, self.whisper)
            if not m:
                return

    def new_round(self):
        """A new answer after a tool ran (or after the check): its own tags, from its start."""
        self.pos, self.held = None, False

    def finish(self, content):
        """The answer is complete: say what's left of it (a held sentence too: nothing re-asked it)."""
        self.held = self.hold = False
        self.feed(content, final=True)


def stream_json(url, body, key="", timeout=60, kind="", emit=None):
    """POST with stream=True; emit(chunk) for each server-sent event (runs in a thread)."""
    req = urllib.request.Request(url, data=json.dumps(dict(body, stream=True)).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    if key:
        req.add_header("Authorization", "Bearer " + key)
    if kind:
        req.add_header("X-Kindred-Kind", kind)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if "event-stream" not in (r.headers.get("Content-Type") or ""):
                # a server that answered all at once: the same answer, as one piece
                whole = json.loads(r.read())
                msg = (whole.get("choices") or [{}])[0].get("message") or {}
                delta = {"content": msg.get("content") or ""}
                if msg.get("tool_calls"):
                    delta["tool_calls"] = [dict(tc, index=i) for i, tc in enumerate(msg["tool_calls"])]
                emit({"choices": [{"index": 0, "delta": delta}]})
                return
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    emit(json.loads(payload))
                except ValueError:
                    continue
    except urllib.error.HTTPError as e:
        raise AIError("HTTP %s from %s: %s" % (e.code, url, e.read()[:300].decode("utf-8", "replace")))
    except (urllib.error.URLError, OSError) as e:
        raise AIError("cannot reach %s (%s)" % (url, getattr(e, "reason", e)))


def post_json(url, body, key="", timeout=60, kind=""):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    if kind:  # reply, own, reflect, fold: the gateway may use another model or effort for each
        req.add_header("X-Kindred-Kind", kind)
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
