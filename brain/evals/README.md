# Pip's eval set

Moments from real play sessions, replayed through the whole brain, so a change to her can be measured
instead of guessed. Each case is one moment from a playtest: what she saw, the conversation so far, what she
remembered, and the words someone said to her, with what must and must not happen.

```sh
scripts/eval.sh                          # stub mode: no services, no AI (CI runs this: tests/test_evals.py)
scripts/eval.sh --mode local             # + System 0's understanding (your local embeddings), still no AI: free
scripts/eval.sh --mode live --judge      # her real AI through your gateway (~$0.15 for the set) + a judge
scripts/eval.sh --mode live --repeat 3 --only follow-me
scripts/eval.sh --brain ../../other-checkout/brain --label other   # the same cases against another version
scripts/eval.sh --mode live --set ai.stable_context=false --set behaviour.talker_first=false --label off
                                         # the same code with a change switched off, to compare
scripts/eval.sh --list
scripts/eval.sh context --since "2026-11-12 23:04" --until "2026-11-12 23:58"   # what her prompts were made of
```

## How a case runs

`run.py` plays the mod's part over the brain's real WebSocket (hello with her powers, join, a snapshot,
then the chat message, from the player or from a friend), and answers her powers with the results the
case gives (or a plain success). `gateway.py` stands in for the gateway: memory is a fresh store seeded
with the case's memories and conversation (your real memories are never read or written), voice is a
silent WAV, reflection calls get nothing, and the AI is either the case's script (stub, local) or your
real gateway (live). Her settings and logs go to a scratch folder, never `~/.kindred-spirit`.

Everything is recorded: her acts (follow, stay...), every tool with its arguments and result, what
reached the game, what she said and when, and each AI request (forced tool, offered tools, tokens, and
the tokens Gemini served from its cache).

## Checks

- **brain** checks must hold whatever the AI does. In stub and local modes the AI's part is played by
  what the real AI did in the playtest (`stub_ai`), so they test System 0 and the guards against the
  mistakes that really happened: "follow me" must make her follow and never reach the game as a guide,
  "stand still" must make her stay, a friend's turn must name the player, `standing_request protect`
  must be accepted for "follow and defend Robin". (A tool System 0 forces is obeyed by the scripted AI,
  as a real one must.)
- **ai** checks are about her own choices and words, so they run only with the real AI: no guide for
  "follow me", one apple each for "both of us", never "he's stuck in honey" after slowness failed.
- **judge** (`--judge`, live): an AI reads each answer (what she knew, what she did, what she said) and
  says pass or fail, with a reason, on a short rubric: short, not needy, not cringe, stays in her world,
  no inventing, honest about her powers, answers the request; plus each case's own questions. It goes
  through your gateway as a `reflect` call (Claude in the recommended setup: a different model family from
  the one that talks).

Case fields: `id`, `play` (`singleplayer` or `lan`), `from` (session and time), `who` (`player` or a friend's
name), `say`, or `turns` (`[{who, say, after, snapshot}]`: several messages in order, `after` seconds
after the one before, 0 = once it's answered; for tasks over a few steps or two people talking), `history`
(`[role, text]` pairs), `memories` (`{kind, text, importance, meta}`), `snapshot` (merged over a base
one), `setup` (`bond`, `abilities`, `power`, `style`, `following`, `amnesia`, `guest_powers`, `alerts`),
`game` (results per power: a dict, or a list of `{when: {arg: regex}, result}`), `stub_ai`, `expect`
(`brain`, `ai`: `acts`, `no_acts`, `tools`, `no_tools`, `game`, `no_game`, `max_uses`, `forced`,
`not_forced`, `prompt_has`, `prompt_not`, `said`, `said_not`, `answers`; `judge`: questions).

`cases/playtest-2026-11-12.json` is built by `make_cases.py` from that night's session logs (conversations)
and the context the gateway logged for each answer (snapshots). Add a moment there and run
`python3 evals/make_cases.py`. After a playtest, the moments that went wrong are the next cases.

## Numbers

`results/<label>-<mode>.json` keeps every run (not committed). `baselines/stub.json` is what CI holds the
brain to: a case that passed must keep passing. Baselines and before/after numbers for each change are in
`docs/research/architecture-review.md` and `docs/research/designs-2026-11.md`.
