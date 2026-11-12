# A deeper heart for Pip: research and proposal

Research and a written proposal only. No code was changed. This is based on `brain/kindred/heart.py`
and `docs/HEART.md` as they are on main (cc1c99a). The proposal fits the existing pieces: the regard
tags, the mood score, pride, the doubt meter, core memories that "still hurt", and Systems 0/1/2.

## In short

- **Today:** one number (bond 0–100) does everything, and each message moves it by a fixed amount.
  Ten insults spread over ten days cost exactly what ten insults in one evening cost, and both are
  undone by enough "sorry"s and time.
- **Research and good game systems agree on four things:**
  1. Relationships have **several dimensions** that can disagree. Liking, trust, respect and
     familiarity are separate, and distrust or resentment is not just "low trust".
  2. Feelings run on **two clocks**: a fast sting that fades in minutes, and slow stocks that only
     move when something keeps happening.
  3. **Bad weighs more than good.** A *pattern* of harm sensitizes. One slip from a trusted friend
     gets the benefit of the doubt.
  4. **Forgiveness and trust repair are different things.** An apology can soften resentment fast,
     but trust only comes back through evidence over time. Repairing a deliberate hurt takes more
     than words.
- **Proposal:** five slow dimensions (affection, trust, respect, familiarity, resentment), a fast
  layer (the mood you already have plus an acute "sting"), and an **incident ledger** that
  remembers each hurt and how far it has been repaired.
  - Each event is *appraised* (was it deliberate? is it part of a pattern?) before it moves anything.
  - Her behaviour comes from a named **stance** derived from the dimensions (warm, guarded fondness,
    wounded, cool reliance, bitter...), not from a single level.
  - Every change carries a human-readable reason, so the dashboard can always say *why* she feels
    the way she does.
- **The old bond number stays** as a derived value, for the heart meter and for compatibility.

---

## 1. What the research and games say

### 1.1 Emotion models: appraisal, mood, personality

**Appraisal theories: emotion comes from how an event is judged, not from the event itself.**

- **OCC (Ortony, Clore and Collins, 1988)** is the most used model in game AI. It defines about 22
  emotion types from three questions: is the *event* good for my goals, was the *agent* who caused
  it praiseworthy or blameworthy, and do I like the *object*?
  - The useful part for Pip is the agent branch. The *same* harm produces **anger** when it is
    blamed on someone acting deliberately, and only distress or disappointment when it isn't.
  - GAMYGDALA is a small OCC engine built for NPCs: you give each NPC goals and annotate game events
    with how they affect them. It also tracks like/dislike *relations* between agents, which colour
    the social emotions (gratitude, anger, pity, gloating).
  - [Popescu, Broekens, van Someren 2013 (GAMYGDALA)](https://ii.tudelft.nl/~joostb/files/Popescu_Broekens_Someren_2013.pdf).
    Survey for NPCs: [Start Your EM(otion En)gine, 2023](https://arxiv.org/pdf/2307.10031).
- **Scherer's Component Process Model** runs appraisal as a sequence of checks:
  1. *relevance*: is it new, is it pleasant?
  2. *implications*: who caused it, on purpose or not, does it block my goals?
  3. *coping potential*: can I deal with it?
  4. *normative significance*: does it break my standards or social norms?

  Steps 2 and 4 are exactly what's missing today. A hit from someone fighting a skeleton next to
  her, and a hit from someone standing still and swinging at her, should not feel the same.
  [Component Process Model overview](https://psu.pb.unizin.org/psych425/chapter/component-process-model-cpm/).
- **EMA (Marsella and Gratch, 2009)** frames emotion as a fast reaction plus a slower re-appraisal
  after deliberation. That matches Pip's System 0 (instant "Ow!") and System 2 (later: "was that a
  pattern?").
  [EMA: a process model of appraisal dynamics](https://www.cs.uky.edu/~sgware/reading/papers/marsella2009ema.pdf).

**Layers of time.**

- **ALMA (Gebhard, 2005)** layers affect into *emotions* (seconds), *mood* (hours) and *personality*
  (stable), each with its own decay. Pip has the first layer (valence/arousal with a 2-minute
  half-life) and a static bond, but nothing in between that slowly accumulates.
  [ALMA: A Layered Model of Affect](https://jmvidal.cse.sc.edu/lib/gebhard05a.html).
- **PAD (Mehrabian)** describes mood as pleasure, arousal and dominance, and temperament as the
  *average* emotional state.
  - The Big Five map onto PAD: for example, extraverts are mainly dominant and secondarily pleasant.
  - Pip already has P and A. "Dominance" (feeling in control versus helpless) is a natural fit for
    her pride: being hit repeatedly should make her feel *small*, not only sad.
  - [Mehrabian 1996, PAD temperament model](https://www.cs.uky.edu/~sgware/reading/papers/mehrabian1996analysis.pdf).

**Personality (OCEAN) should set the *gains*, not the script.**

- Agreeableness: how fast she forgives.
- Neuroticism: how hard a hurt lands.
- Extraversion: how fast she warms up.
- Conscientiousness: how much she values reliability, which weights trust.

Each world's Pip could get small, fixed variations of these, so two Pips react differently to the
same treatment.

### 1.2 Relationship dimensions: trust is not liking, and distrust is not low trust

- **Trustworthiness has three parts (Mayer, Davis and Schoorman, 1995)**:
  - *ability*: can you?
  - *benevolence*: do you mean me well?
  - *integrity*: do you keep to principles and to your word?

  For Pip, "trust in the player" is mostly benevolence ("will you hurt me?") and integrity ("does
  your sorry mean anything?"). Ability belongs with *respect*.
  [Summary of Mayer, Davis and Schoorman 1995](https://explore.psychsafety.com/n/mayer-davis-schoorman-1995/).
- **Trust and distrust are separate dimensions (Lewicki, McAllister and Bies; Lewicki, Tomlinson
  and Gillespie, 2006).** They can coexist: you can rely on someone in one area and be wary of them
  in another. This is the research basis for keeping **resentment** as its own stock instead of a
  negative end of affection.
  [Lewicki, Tomlinson and Gillespie 2006](https://www.teletrust.de/fileadmin/_migrated/content_uploads/Lewicki__Tomlinson__Gillespie_2006_Models_of_interpersonal_Trust.pdf);
  [Managing interpersonal trust and distrust](https://www.beyondintractability.org/essay/trust-overview).
- **Trust grows in stages (Lewicki and Bunker, 1996).**
  1. *calculus-based*: costs and rewards
  2. *knowledge-based*: I can predict you
  3. *identification-based*: we share goals

  Deeper trust needs **familiarity**: predictability over time, not just kind words. It is also
  more painful to break.
  [Lewicki and Bunker 1996](https://explore.psychsafety.com/n/lewicki-bunker-1996/);
  [Trust, trust development and trust repair](https://www.beyondintractability.org/artsum/lewicki-trust).
- **Relational agents (Bickmore and Picard, 2005)**:
  - Long-term companions need relationship-appropriate behaviour that *progresses* with the stage of
    the relationship: social dialogue, self-disclosure, shared history.
  - Behaviour that never changes wears thin over repeated meetings.

  This supports tying what she shares to familiarity and trust.
  [Bickmore and Picard, TOCHI 2005](https://www.ccs.neu.edu/~bickmore/publications/toCHI.pdf).

### 1.3 Negativity bias, asymmetry, patterns

- **"Bad is stronger than good"** (Baumeister, Bratslavsky, Finkenauer and Vohs, 2001). Across close
  relationships, feedback and impressions, negative events have more impact than equal positive
  ones. Bad impressions form faster and resist disconfirmation.
  [Baumeister et al. 2001 (PDF)](https://fbaum.unc.edu/teaching/articles/Baumeister_2001.pdf).
- **The asymmetry principle of trust** (Slovic, 1993): trust is easier to destroy than to create.
  Negative events move trust much more than positive ones.
  [Slovic 1993](https://econpapers.repec.org/RePEc:wly:riskan:v:13:y:1993:i:6:p:675-682);
  [Poortinga and Pidgeon 2004 on the asymmetry principle](https://ideas.repec.org/a/wly/riskan/v24y2004i6p1475-1486.html).
- **Gottman's "magic ratio"**: stable couples have about 5 positive interactions for every negative
  one *during conflict*, and far more outside it. Healthy relationships still have negative moments,
  but they are quickly repaired. This is a good calibration target: in the fast layer, one insult
  should take about five kind moments to outweigh.
  [Gottman Institute: the magic relationship ratio](https://www.gottman.com/blog/the-magic-relationship-ratio/).

### 1.4 Forgiveness and trust repair

- **Forgiveness has three motivations (McCullough's TRIM)**: *avoidance* (keep away), *revenge* (get
  back at them) and *benevolence* (goodwill). Forgiving means the first two go down and the third
  goes up, and it unfolds *over time*, not at once.

  These map directly onto Pip's existing behaviours:
  - avoidance: distance, vanishing
  - revenge: "spicy" mischief
  - benevolence: offers, warmth

  [TRIM-18 scoring (McCullough, Root and Cohen 2006)](https://pages.ucsd.edu/~memccullough/Forgiveness-Related%20Stuff/TRIM%2018_Mc_R_C_2006.pdf);
  [Transgression-related motivational dispositions](https://pages.ucsd.edu/~memccullough/Papers/transgression_related_motivational_dispositions.pdf).
- **The kind of violation decides what repairs it** (Kim, Ferrin, Cooper and Dirks, 2004).
  - An apology repairs trust well after a *competence* violation, a mistake: for Pip, an accidental
    hit.
  - It works poorly after an *integrity* violation, something done on purpose. People weigh the bad
    act more than later repentance.
  - Later work (Dirks et al., 2011) shows that **substantive responses** (penance, a real cost, a
    changed situation) help where words don't.

  For Pip: accidents are forgiven on "sorry"; deliberate cruelty needs a sorry *plus* evidence over
  time, or a gesture.
  [Removing the shadow of suspicion (2004)](https://ink.library.smu.edu.sg/context/lkcsb_research/article/3367/viewcontent/RemovingShadowSuspicion_afv.pdf);
  [Substantive responses after a transgression](https://ink.library.smu.edu.sg/lkcsb_research/3096/).

### 1.5 What games do

| Game | What it does | What to take |
|---|---|---|
| **The Sims 2** | Two meters per relationship: *daily* (volatile, decays fast) and *lifetime* (slow to build and slow to decay). Sims 3 merged them; Sims 4 splits *friendship* and *romance*. [Sims 2 social interactions](https://strategywiki.org/wiki/The_Sims_2/Social_Interactions), [Sims wiki: Friendship](https://www.thesimswiki.com/wiki/Friendship) | Two clocks. One bad day dents the daily meter; only a pattern reaches the lifetime one. |
| **Dwarf Fortress** | Personality facets and values. Events become *thoughts* with emotions, and repeated thoughts become long-term *memories* that are revisited and re-trigger feelings. Stress accumulates, and clashing values breed grudges. [Personality facets](https://dwarffortresswiki.org/index.php/DF2014:Personality_facet), [Thoughts and preferences](https://dwarffortresswiki.org/index.php/DF2014:Thoughts_and_preferences), [Stress](https://dwarffortresswiki.org/Stress) | Repeated hurts turn into a memory that keeps hurting. Pip already has "core memories that still hurt"; the heart should feed them and read them. |
| **Crusader Kings III** | Opinion is a *sum of labelled modifiers* ("Imprisoned my friend −40", "Gift +20"), each with its own duration that decays, and personality clashes amplify negatives. ([Paradox forum discussion](https://admin-forum.paradoxplaza.com/forum/threads/the-gameplay-focus-on-stacking-stats-and-modifiers-runs-counter-to-the-core-design-philosophy-of-crusader-kings-3.1735002/); exact numbers are best checked in-game) | **Explainability.** Every number the player sees has a reason and a timer. It also shows the risk: unbounded positive stacking lets players farm opinion, so cap and diminish positives. |
| **Black & White** | The Creature learns from the player's slaps and strokes, using a belief–desire–intention model: feedback reshapes its desires and opinions over time. [Black & White](https://wikiwand.com/en/Black_and_White_(computer_game)) | How you treat her *changes her*, not only a score. Treatment should shape her temperament and her beliefs about you. |
| **Façade** | Grace and Trip read each player utterance as a small set of discourse acts (agree, criticize, praise, flirt...) and update *affinity* (zero-sum between them) and tension. [Mateas and Stern, GDC 2003](https://faculty.cc.gatech.edu/~isbell/classes/reading/papers/MateasSternGDC03.pdf) | This is what Pip's regard tags already are. Façade shows that a richer act vocabulary (teasing ≠ insulting) matters more than finer numbers. |
| **Versu** | Characters evaluate each other against social practices and norms, remember the *conclusions* they drew about each other, and can share them. [Evans and Short 2014](https://www.cs.uky.edu/~sgware/reading/papers/evans2014versu.pdf), [Emily Short on Versu](https://emshort.blog/2013/02/26/versu/) | Store **beliefs with evidence** ("they get mean when they're losing", from 3 incidents), not just numbers. Readable by System 1 and in the dashboard. |
| **Prom Week / Comme il Faut** | A "social physics engine": numeric networks (buddy, romance, cool), status (friends, enemies, dating), and a **social facts database** of what happened. Thousands of rules read that history ("has been mean to me several times"). [Prom Week: social physics as gameplay](https://bibtex.github.io/FDG-2011-McCoyTSMW.html), [Social story worlds with Comme il Faut](https://cs.uky.edu/~sgware/reading/papers/mccoy2014cif.pdf) | History is a first-class input: the same act means something different depending on the past. That's the incident ledger. |

**LLM agents.** Generative Agents (Park et al., 2023) show that a periodic *reflection* step over
stored memories produces higher-level beliefs ("Klaus is dedicated to his research"), which then
shape behaviour. That is Pip's System 2, applied to the relationship.
[Generative Agents](https://arxiv.org/abs/2304.03442).

---

## 2. Non-linear dynamics Pip needs

| Phenomenon | What it means for Pip | Mechanism (section 4) |
|---|---|---|
| Negativity bias | An insult outweighs a compliment | Negative base values about 2× positive; trust is moved only by evidence on the positive side |
| Pattern > sum | The 5th insult this week hurts more than the 1st | *Sensitization*: hurts are multiplied by a recent-pattern score |
| Benefit of the doubt | A trusted friend's single slip is shrugged off | A *buffer* that shrinks as trust falls and as the pattern grows |
| Expectancy violation | Cruelty from someone she loves stings *more* in the moment, even if it lasts less | The acute sting is scaled by affection; lasting damage is scaled by the buffer |
| Diminishing returns | Sweet words saturate; you can't buy love in a minute | Gains × (1 − level), repetition discount, per-minute cap (already partly there) |
| Slow vs fast | Mood swings in minutes; who you are to her changes over sessions | Two layers: fast (mood, sting) and slow (five dimensions) |
| Decay | Words fade; scars don't, until healed | Resentment fades with time without hurts, but down to a floor set by painful core memories |
| Grudges | A pattern becomes "this is who they are" | A System 2 belief plus a scar (core memory) that keeps a resentment floor |
| Forgiveness ≠ trust | "I forgive you, but I'm keeping my distance for a bit" | The apology lowers resentment; trust returns only through *probation* (time without hurts) |
| Earned repair | Deliberate harm needs more than words | Apology value depends on intent, sincerity and history; gestures count as substantive repair |
| Hollow apologies | Sorry, hit, sorry, hit... | Already there (`insincere`); generalized as an apology credit that halves with each broken probation |
| Time heals words, not everything | A week away softens resentment, but she remembers | Resentment decays in real time; trust and scars don't decay from absence |

---

## 3. How the dimensions should change her (Systems 0, 1, 2)

### System 0: instinct (no AI, milliseconds)

| | Today | Proposed |
|---|---|---|
| **Distance** | `closeness = bond/100` | `min(affection, trust)`: you snuggle up to someone you both like *and* feel safe with. The acute sting still pushes her away. |
| **Flinch** | — | When trust < 40 and the player swings a weapon within 3 blocks of her: a small back-off and a flinch gesture, no line. Players *see* distrust. |
| **Petting** | Always +1.5 | With trust < 30 she startles first (half a second, a little dodge), then accepts. It counts for less until trust is back. |
| **Hit appraisal** | First hit in 30 min with bond ≥ 60 counts as an accident | **Accident**: a hostile within 6 blocks, the player hit a mob within the last 3 s, or she drifted into their swing. **Careless**: a single hit with no fight. **Deliberate**: 2+ hits in 10 s, or a hit with no fight during an open incident. |
| **Vanishing** | 3 hits in a minute, or mean while bond < 12 | Driven by *avoidance* = f(resentment, 100 − trust, sting). |
| **Mischief** | `angry()` = low bond or hurt_until | **Spiteful** mischief needs *revenge* = f(resentment, low affection), not just "low bond". Friendly pranks need affection ≥ 55, familiarity ≥ 30 and resentment < 20. |
| **Offers of help** | Not when angry | Driven by *benevolence* = f(affection, respect). With high trust but low affection she still helps when asked, but doesn't offer. |
| **Instinct lines** | Rewritten per bond level | Rewritten per **stance** (section 4.5), so "Ow!" from a guarded Pip differs from "Ow!" from a wounded one. |

### System 1: her words

Today she receives "Your bond: friend (52/100)" plus a paragraph. Proposed:

- A **stance paragraph** (one per stance, written like the current GUIDANCE).
- **Modifiers** for respect and familiarity:
  - low respect: she argues, isn't impressed, won't cheer
  - high respect: impressed, asks how they did it
  - high familiarity: in-jokes, callbacks to shared moments, nicknames
  - low familiarity: doesn't presume
- **One sentence of evidence** from the ledger or a System 2 belief, so she can refer to *why*:

  > "They called you useless yesterday and again twice today. They apologised a few minutes ago; you
  > want to believe it, so you're watching whether they mean it."

- **No numbers in the prompt.** Words carry better than "52/100", and numbers invite the AI to
  quote them.
- **Repair state:**
  - open: still hurt
  - apologised, on probation: softer, but watchful
  - repaired: she can say so, once, warmly ("We're okay, you know.")

Richer **regard tags** (the Façade lesson), replacing today's single judgement:

| Tag | Meaning |
|---|---|
| `teasing` | Banter. Counts as kind when trust and familiarity are high, as rude between strangers. |
| `dismissive` | Ignoring or brushing her off. Mild; it builds up. |
| `rude` | As today. |
| `mean` / `cruel` | As today. |
| `threat` | "I'll kill you". Hits trust hardest. |
| `sorry` | A plain apology. |
| `sorry_real` | An apology that names what they did and makes no excuse. |
| `thanks` | Gratitude. It raises affection *and* respect-for-her, which she notices. |

### System 2: what she reflects on (in the background)

1. **Patterns into beliefs, with evidence** (Versu, Generative Agents). From the ledger, write at
   most a few short beliefs about the player, each citing its incidents:
   - "They get mean when they lose something."
   - "They always come back for me when I wander off."

   Positive beliefs count as trust evidence. Beliefs are shown in the dashboard and expire when the
   evidence ages out.
2. **Re-appraisal.** Was that "idiot" banter? Was that hit an accident? System 2 sees the context,
   so it may reclassify an incident within a few minutes. It is logged and reversible, and it can
   only soften one notch or harden one notch, never invent incidents.
3. **Scars.** When an incident or pattern crosses a threshold, it becomes a core memory with
   `pain` (which already exists). While it is painful, it holds a resentment floor. System 2 marks
   it `healed` (which also already exists) only after sustained repair, for example 3 sessions with
   no deliberate hurt, at least one of them with a repair gesture.
4. **Choosing a repair gesture** for a serious incident (section 4.4): something small, in her
   world, that the game can check.
5. **Her portrait** ("who she's become lately") includes how she sees the player now, from the
   stance and the beliefs.
6. **Temperament drift** (Black & White, Dwarf Fortress). Very slowly, how she's treated shapes her:
   - A long history of kindness nudges her sensitivity down and her warmth up.
   - A long history of cruelty does the opposite.

   Bounded to ±20% of the defaults and shown in the dashboard.

---

## 4. The proposal for Pip

### 4.1 State (per world, saved in the heart document)

| Variable | Range, start | What it means | Moves fast? |
|---|---|---|---|
| `affection` | 0–100, 30 | How much she likes being with you | slow |
| `trust` | 0–100, 40 | She feels safe with you; your word means something (benevolence + integrity) | slow; drops fast, rises only with evidence |
| `respect` | 0–100, 50 | How she regards how you act: competence, how you treat the world and her boundaries | slow |
| `familiarity` | 0–100, 0 | Time and shared moments; predictability | slow, nearly monotonic |
| `resentment` | 0–100, 0 | Unresolved hurt: a grudge stock, separate from affection | medium (fades over about an hour of quiet play, down to a floor) |
| `sting` | 0–1 | Acute hurt right now; replaces the `hurt_until` booleans | fast (half-life 3 min) |
| valence, arousal (+ dominance) | as today | Mood | fast (as today) |
| `incidents` | list | The ledger (4.3) | — |
| `beliefs` | ≤ 5 | System 2's conclusions with evidence | — |
| `temperament` | 4 gains | sensitivity, forgiveness, warmth, pride (4.6) | very slow |

**Derived values (never stored, always explainable):**

```
bond        = clamp(0.45·affection + 0.35·trust + 0.20·familiarity − 0.35·resentment)  # the heart meter, old thresholds
closeness   = min(affection, trust) / 100, reduced by sting
avoidance   = (resentment + (100 − trust)) / 200 + 0.5·sting       # distance, vanishing
revenge     = resentment/100 · (1 − affection/100)                  # spiteful mischief
benevolence = (0.7·affection + 0.3·respect) / 100                   # offers, help, warmth
pattern     = Σ deliberate incidents: severity · 0.5^(age / 72 h)   # real time, so "every day" counts
```

### 4.2 Appraisal: event → impact

Every event first gets **intent** (accident, careless or deliberate: System 0 rules for hits, the
regard tag for words, System 2 may revise it) and a **target** (her, the world, herself). Then a
base vector (Δaffection, Δtrust, Δrespect, Δresentment, sting):

| Event | ΔA | ΔT | ΔR | ΔG (resentment) | sting | severity |
|---|---|---|---|---|---|---|
| sweet | +3 | (evidence) | | −1 | | |
| kind / thanks | +1.5 | (evidence) | thanks: +0.5 | −0.5 | | |
| teasing (trust ≥ 50, familiarity ≥ 30) | +1 | | | | | |
| teasing (otherwise) | as dismissive | | | | | |
| pet | +1 (×0.5 if trust < 30) | | | | | |
| did her favour | +1.5 | +1 | +0.5 | | | |
| dismissive | −1 | | −0.5 | +1 | 0.1 | 0.3 |
| rude | −3 | −1 | −1 | +3 | 0.3 | 1 |
| mean / cruel | −6 | −4 | −2 | +8 | 0.6 | 2.5 |
| threat | −3 | −6 | −2 | +5 | 0.5 | 2 |
| hit, accident | | | | | 0.15 | 0 |
| hit, careless | −1 | −2 | | +1 | 0.3 | 0.5 |
| hit, deliberate | −3 | −8 | −1 | +6 | 0.6 | 2 |
| hurt during probation ("betrayal") | ×1.5 | ×2 | | ×1.5 | +0.2 | +2 |
| killed a villager | −2 | −2 | −8 | +2 | 0.3 | (world, not her) |
| kill spree | | | −3 | | | |
| advancement, beat the dragon... | | | +1..+4 | | | |
| spam (as today) | −1..−5 | | −0.5 | | annoyance | |

**Multipliers on negatives** (these make a pattern more than the sum of its parts):

```
sensitization = 1 + min(1.5, 0.25 · pattern) · temperament.sensitivity
buffer        = 1 − 0.5 · (trust/100) · e^(−pattern)          # benefit of the doubt, gone once there's a pattern
lasting part  (ΔA, ΔT, ΔR, ΔG) × sensitization × buffer
acute sting   × (0.7 + 0.6 · affection/100)                    # it stings more from someone she loves
```

**Multipliers on positives** (these stop farming):

```
gain × (1 − X/110) for the dimension X it raises, × repetition discount (as today), capped per minute (as today)
words never raise trust directly
```

**Trust evidence** is the only way trust grows. Every 10 minutes together with no deliberate hurt:

```
trust += 0.8 · (1 − trust/100) · (2 during probation) · (0.5 if pattern > 3)
```

Doing her favours, keeping a standing promise, and coming back for her when she wanders add +1
each.

### 4.3 The incident ledger

Each hurt with severity > 0 opens an incident:

```
{id, t, kind: "mean", words: "you're useless", intent: "deliberate", severity: 2.5,
 multipliers: {sensitization: 1.5, buffer: 0.9}, impact: {A: -8.1, T: -5.4, G: +10.8},
 state: open | apologised | probation | repaired | scar, apology: {t, sincerity}, repaired_t}
```

States:
- **open**: still hurt.
- **apologised**: a sorry was received; its value depends on intent, sincerity and history.
- **probation**: time without hurts is being counted.
- **repaired**: trust is mostly back and its resentment is cleared.
- **scar**: a pattern or a severe incident, held as a painful core memory until System 2 heals it.

Incidents older than 30 days that are repaired are folded into a one-line summary, so the ledger
stays small.

### 4.4 Forgiveness and repair: earned

1. **Sorry for an accident or a careless act** (a competence violation, after Kim et al. 2004):
   - The incident is closed, its trust loss is restored, its resentment is cleared, and the sting
     goes away.
   - This is today's "quick to forgive", kept for the cases where it's right.
2. **Sorry for something deliberate** (an integrity violation):
   - The apology value is `sincerity × credit`:
     - sincerity: 0.4 for `sorry`, 1.0 for `sorry_real`
     - credit: starts at 1 and is ×0.5 for every broken probation in the last 3 days. This
       generalizes today's `insincere()`.
   - Resentment from the incident drops by `0.5 × value` of its share. The sting halves.
   - The incident enters **probation**: `8 min × severity × sensitization` of play together.
   - Trust does not jump.
3. **Probation passes** (no deliberate hurt):
   - The incident is repaired: 70% of its trust loss is restored and the rest of its resentment is
     cleared.
   - The other 30% only comes back through ordinary trust evidence. That's the "she remembers".
4. **Hurt during probation**: a betrayal. Bigger impact (see the table above), the credit is halved,
   and the pattern grows.
5. **Gestures** (substantive repair, after Dirks et al. 2011):
   - When to ask: the incident severity × sensitization ≥ 3, or the pattern is ≥ 3.
   - System 2 may choose **one** small ask in her world that the game can check: a flower, a sapling
     planted, staying still with her at sunset, a little spot built for her.
   - Completing it ends probation at once and adds +3 affection.
   - Rules: she asks at most once per incident, never anything costly or humiliating, and repair is
     always possible without it.
6. **Scars**:
   - A scar forms when the pattern reaches 6, or after a betrayal of severity ≥ 4.
   - The worst incident becomes a painful core memory. Each painful scar holds a resentment floor
     of 12.
   - System 2 heals it after 3 sessions in a row without a deliberate hurt, with at least one
     gesture or a `sorry_real` that names it.
7. **Time**:
   - Resentment above its floor halves every 60 minutes of play without a new hurt (×
     temperament.forgiveness), and every 24 hours of real time apart.
   - Affection slowly loses `0.02 × resentment` every 10 minutes: a grudge slowly poisons liking.
   - Time together raises affection a little: `+0.3 × (1 − A/100)` every 10 minutes without an open
     incident (mere exposure).
   - Respect drifts toward 50 (half-life about a day of play).
   - Familiarity rises: +1 every 10 minutes together, +2 for each shared first (new dimension, boss,
     biome). It never drops below 70% of its peak.

### 4.5 Stances: how the numbers become behaviour

The first rule that matches wins. Respect and familiarity are modifiers on top.

| Stance | When | How she is (System 1) | Body (System 0) |
|---|---|---|---|
| **new** | familiarity < 15 | Curious about the world more than about you; polite, doesn't presume | medium distance |
| **bitter** | resentment ≥ 60 and affection < 40 | Short and sharp; won't do favours; spiteful mischief allowed | far; may vanish |
| **cold** | affection < 30 and trust < 30 | Minimal, factual, no small talk | far |
| **wounded** | affection ≥ 50 and resentment ≥ 35 | Cares about you and is hurt *by* you: quieter, takes things the wrong way, may bring it up, wants to believe your apology | middle; looks away |
| **guarded fondness** | affection ≥ 55 and trust < 40 | Likes you but doesn't feel safe: warm in words, keeps out of reach, checks your intentions | flinches, out of swinging range |
| **cool reliance** | trust ≥ 55 and affection < 35 | Dependable and polite; helps when asked, doesn't offer or share | ordinary distance |
| **warm** | affection ≥ 60, trust ≥ 60, resentment < 20 | The current friend, close and best friend guidance, chosen by `bond` | close |
| **easy** | everything else | The current wary or friend guidance | as today |

Modifiers:
- Respect < 30: argues, unimpressed, may refuse to help with what she disapproves of.
- Respect ≥ 75: admiring, asks how you did it.
- Familiarity ≥ 60: callbacks and in-jokes.
- Any open incident: one evidence sentence.
- Probation: watchful.
- Just repaired: "we're okay".

The heart meter keeps showing `bond`. The **stance** becomes what `/kindred status` says ("she
likes you, but she's wary of you").

### 4.6 Temperament: personality as gains

| Gain | Default | OCEAN analogue | What it scales |
|---|---|---|---|
| sensitivity | 1.0 | neuroticism | sensitization and sting |
| forgiveness | 1.0 | agreeableness | how fast resentment decays; probation length |
| warmth | 1.0 | extraversion | affection gains; familiarity gains |
| pride | 1.0 | (low) agreeableness, dominance | how much hollow or repeated apologies are discounted |

- Each new world's Pip gets ±15% jitter on each gain, so each world's Pip differs.
- System 2 drift is bounded to ±20%.
- Players can set them in `[heart]`, for example `temperament = "thick-skinned"`, `"sensitive"` or
  `"forgiving"`.

### 4.7 Explainability (dashboard and logs)

- **Every change goes through one function**, `impress(event, base, multipliers, why)`. It logs a
  line like:

  > `mean "you're useless" — deliberate · pattern 2.4 (3 hurts in 2 days) ×1.6 · buffer ×0.93 →
  > affection −8.9, trust −5.9, resentment +11.9, sting 0.7`

- **Heart tab:**
  - five bars with a 1-hour trend arrow
  - a stance chip with its sentence
  - the open incidents with state and probation progress ("4 of 20 min")
  - beliefs with their evidence
  - scars
  - temperament
  - a sparkline per dimension across sessions
- **Replay:** the heart is a pure function of (start state, events, clock), so the ledger can be
  replayed to rebuild the state and to test (see section 5).

### 4.8 Guardrails (players include kids)

- She never guilt-trips about real-life absence: time apart only *heals*.
- There is always a path back. Scars heal, and gestures are small and kind.
- Hurt is shown in her world and in her manner (rain, distance, a flinch, quietness), never with
  harsh words aimed at the player.
- The existing caps stay: no destruction, mischief is reversible, nothing during danger.
- A `fresh start` command (or setting) for players who want to reset her heart in a world, with the
  old one kept in history.

### 4.9 Migration and phasing

- **Migration:** `affection = bond`, `trust = bond`, `familiarity = min(60, memories/2)`, and
  `resentment = 0`, or 15 per painful core memory.
- **Compatibility:** `bond` stays derived, so existing thresholds keep working until each is moved
  to its dimension (pranks → affection and familiarity, play-fights → trust, vanish → avoidance).

**Phases:**
1. Dimensions, appraisal, ledger, derived bond, logging, dashboard bars. Behaviour is unchanged
   except distance and the stance in guidance.
2. System 0 mapping: flinch, petting, hit intent, avoidance and revenge. The new regard tags.
3. System 2: beliefs, re-appraisal, gestures, scars and healing, temperament drift.

---

## 5. Test scenarios (with a fake clock; assertions as ranges, not exact numbers)

| # | Scenario | Expected |
|---|---|---|
| 1 | **Kind for an hour, then one insult** (start A 50, T 50; 20 kind/sweet messages and pets over 60 min, then one `rude`) | Before: A about 65–70, T about 55. After the insult: sting > 0.3 and mood sad for 2–5 min; ΔA between −1.5 and −2.5; ΔT ≥ −0.8; resentment < 3 and back under 1 within 30 min. Stance stays warm. After a `sorry`: the incident closes fast (it was rude, not cruel, and the buffer is high). |
| 2 | **Insults every day** (5 days; each day 30 min of play with 2 `rude` + 1 `mean`, each followed by `sorry`) | Day 1 is roughly like scenario 1 ×3. By day 3: sensitization ≥ 1.6, buffer ≥ 0.95, T < 30, resentment ≥ 35, stance wounded or guarded fondness. Apologies are worth less and less (credit ≤ 0.25 by day 4). By day 5: a scar exists and the resentment floor is ≥ 12. **The total damage is much greater than in a single evening with the same 15 events** (pattern > sum). |
| 3 | **Same 15 events in one evening, then nothing for 5 days** | Lower lasting damage than scenario 2. After 5 days apart, resentment is near its floor, but trust hasn't come back by itself (trust needs time *together*). |
| 4 | **An accident between friends** (T 70, hit while a zombie is 3 blocks away) | intent = accident; ΔT = 0; a small sting; an "Oof!" line; maybe a bonk if play-fights are on. |
| 5 | **Deliberate hit, sorry, hit again within probation** | The second hit is a betrayal: ΔT is at least twice the first; credit halved; the next `sorry` is worth less than half of the first. |
| 6 | **Like but don't trust** (many sweet words, plus a deliberate hit every session) | A ≥ 55, T < 40 → stance guarded fondness. She flinches when the player swings near her and keeps out of reach, but her words stay warm. |
| 7 | **Trust but resent** (never hits, keeps promises and does her favours, but mocks her often: `rude` and `dismissive` without apology) | T ≥ 55, A < 40, resentment ≥ 35 → cool reliance, or bitter if resentment ≥ 60. She helps when asked but doesn't offer. |
| 8 | **Earned repair** (scenario 2, then `sorry_real` naming it, a completed gesture, and 3 calm sessions) | The incident is repaired at once on the gesture; the scar is healed by System 2 after session 3; resentment back under 10; T rising but still below its pre-pattern level ("she remembers"). |
| 9 | **Farming affection** ("i love you" ×50) | Diminishing returns, annoyance from spam, ≤ 8 affection per minute; trust unchanged. |
| 10 | **Respect** (kills a villager, then defeats the Ender Dragon later) | Respect falls 8 → she argues and is unimpressed. The dragon adds respect +4, and drift recovers the rest over about a day. Affection and trust are barely touched. |
| 11 | **Banter between close friends** (`teasing` "you're such a goof" with T 70, F 60) | Counts as kind (+1 A), no incident. The same line at F 5 counts as dismissive. |
| 12 | **Replay** | Rebuilding the state from the ledger and events gives exactly the saved state. |

---

## 6. Open questions for the user

1. **How long should a grudge last?** The proposal: words fade in an hour of play, a pattern leaves
   a scar that needs about 3 good sessions. Gentler for younger players?
2. **Should trust really never come back from time apart alone?** That's realistic, but a player who
   was mean once and came back a month later might find her more wary than expected.
3. **Gestures:** fine as small in-world asks, or does it feel like a quest you have to grind?
4. **Show the dimensions** to the player in-game (the heart meter becomes five little icons) or only
   in the dashboard?
5. **Temperament jitter per world:** desirable (each Pip is different) or surprising?
