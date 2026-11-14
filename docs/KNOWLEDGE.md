# What Pip knows about Minecraft

Pip must never invent facts. She says only what comes from the game, a tool, her memory or real
Minecraft knowledge, and the knowledge base is where that knowledge comes from: recipes, mobs,
biomes, mechanics, redstone, farming and build guides, fetched from a few sources into one local
SQLite file she can search. When she says "a piston takes 3 planks, 4 cobblestone, an iron ingot
and redstone dust", that sentence comes from a page anyone can check (its URL and license stay
with it, for the logs and the dashboard; Pip herself never talks about pages, see Integration).

Code: `services/knowledge/` (standard library only; numpy is used if present). Tests:
`brain/tests/test_knowledge.py` (no network: hand-recorded responses).

```
  sources                      crawler                                knowledge.db
  ─────────                    ───────                                ────────────
  minecraft-wiki  ─┐   robots.txt · 1 request/s · cache    pages ── chunks ── FTS5 (words)
  minecraft-data  ─┤   discover ▶ queue ▶ fetch ▶ clean ▶ chunk ──▶          └─ vectors (meaning,
  web sites       ─┤   (resumes after a stop; refetches only           from the gateway's /v1/embeddings)
  your .md files  ─┘    what changed)                                       │
                                                         gateway /v1/knowledge/search ◀── Pip
```

It is kept apart from her memories (`services/memory_store.py`): those are what she lived with
you, this is what the world says about the game.

## Quick start

```bash
cd ~/Developer/kindred-spirit
python3 services/knowledge/kb.py crawl minecraft-wiki --core --grow 600   # the recommended set (~45 min)
python3 services/knowledge/kb.py crawl minecraft-data                     # exact 1.21.1 recipes (seconds)
python3 services/knowledge/kb.py search "where do zombies spawn"
python3 services/knowledge/kb.py eval                                     # how well it answers
```

| Command | What it does |
|---|---|
| `kb.py sources` | the sources, their licenses and terms, what is stored from each |
| `kb.py crawl minecraft-wiki --core --grow 600` | **the recommended set**: ~340 pages survival players ask about (materials, tools, workstations, enchanting, brewing, farming, redstone, villagers, mobs, structures, the key tutorials; `CORE_PAGES` in `sources.py`), then the 600 pages those link to most ([below](#what-to-crawl)) |
| `kb.py crawl minecraft-data` | every crafting recipe, food value and mining need of Java 1.21.1, exactly ([below](#minecraft-data-the-games-own-numbers)) |
| `kb.py crawl minecraft-wiki` | without options, a first crawl takes the starter categories (mobs, biomes, tutorials, ...; only the first 200 members of each, see below); after a stop it just continues |
| `kb.py crawl minecraft-wiki --category Mobs --limit 50` | one category (and its subcategories, `--depth 1`), at most 50 pages this time |
| `kb.py crawl minecraft-wiki --page Piston --page "Tutorial:Mob farm"` | given pages |
| `kb.py crawl minecraft-wiki --all` | every article in the wiki's sitemap (version-history pages skipped): about 10,000 pages, several hours |
| `kb.py crawl local` | your own Markdown/text files in `~/.kindred-spirit/knowledge/local/` |
| `kb.py refresh` | every source again, fetching only pages that changed |
| `kb.py search "how do I make a piston" [-k 5] [--json] [--full]` | ranked chunks with their source and license |
| `kb.py learn "how do I build an iron farm"` | read the few wiki pages that answer one question, now ([below](#learning-on-demand)) |
| `kb.py learning [on\|off] [--per-hour N] [--pages N] [--max-mb N]` | on-demand learning settings and the last look-ups |
| `kb.py stats` | pages, chunks, vectors, size on disk, queue, when last fetched |
| `kb.py reindex` | rebuild every stored page from the download cache, no network (after a parser change); pages the rules now leave out are removed |
| `kb.py eval [-v] [--json FILE]` | score it on 54 questions players ask, with the pages that answer them ([below](#measuring-it)) |
| `kb.py compact` | 16-bit vectors and free space given back (a store from before this change shrinks by ~40%) |
| `kb.py embed` | give vectors to chunks stored while the gateway was off |
| `kb.py remove SOURCE [--cache]` | forget a source (and its cached downloads) |
| `kb.py add NAME --kind web ...` | add a source (below) |

A crawl can be stopped at any time (Ctrl+C): the queue is in the database, and the next
`kb.py crawl SOURCE` continues where it was (in the measured crawl below, a stopped run resumed
its 319 queued pages without asking for anything twice). `--delay 2` slows it down; `--offline` reads only the
download cache.

## Being a good guest

Wikis and sites are run by volunteers, so the crawler behaves:

- **robots.txt is obeyed**, including the `*` and `$` wildcards (Python's own robot parser
  ignores them, so this has its own), per redirect hop. A disallowed URL is never requested.
- **One request at a time per site, at most one per second** by default (`--delay`), slower if
  the site's `Crawl-delay` asks for it. `429`/`503` answers wait (honouring `Retry-After`).
- **Everything is cached** (gzip, `~/.kindred-spirit/knowledge/cache/`), and pages are asked
  again with `If-None-Match`/`If-Modified-Since`, so an unchanged page costs a tiny `304`.
- **Incremental refresh**: a MediaWiki page is fetched again only when its revision id (API) or its
  sitemap `lastmod` changed; a web page when its sitemap `lastmod` changed or the server says it
  did; a local file when its modification time or size changed. A page fetched again whose text
  is the same keeps its chunks and vectors; an edited page re-embeds only the chunks that changed.
- **A generic User-Agent** (`KindredSpiritKnowledge/0.1 (local knowledge base for a single-player
  Minecraft companion; slow, cached, obeys robots.txt)`), with no name or email in it.

### minecraft.wiki: pages, not the API

The task first called for the MediaWiki API (`api.php`), but minecraft.wiki's robots.txt says
`Disallow: /*api.php` and `Disallow: /*?action=` for every agent. So on minecraft.wiki the adapter
reads what robots.txt allows: the article pages (`/w/Piston`), the category pages
(`/w/Category:Mobs`) and the sitemaps (`/images/sitemaps/…`, which give each page's last edit
time for cheap refreshes). For any other MediaWiki wiki whose robots.txt allows the API, the same
adapter uses `api.php` (category members with revision ids, then `action=parse`), chosen
automatically (`"mode": "auto" | "api" | "html"` in its config).

Two things follow from that robots.txt:

- A category page shows up to 200 members, and its "next page" links (`?pagefrom=`) are
  disallowed, so only the first 200 of a big category are taken (the crawler says so). That is
  why the first knowledge base had tutorials from A to I only, and almost no items or blocks:
  `--core --grow` (below) doesn't depend on category pages at all.
- The same robots.txt blocks named AI crawlers (GPTBot, ClaudeBot, CCBot, …) from everything.
  This tool is not one of those (a player's own slow, local fetcher that is never redistributed),
  and it is held to the rules for every other agent. If the wiki ever names it, it stops.

## What to crawl

The first knowledge base was crawled by category (mobs, biomes, tutorials...): 381 pages, but
cut by the 200-member limit (tutorials A to I), with April Fools mobs and Education-only entities
in, and no Diamond, Enchanting Table, Potion, Trading or Nether Portal page. Scored on the
questions players ask, a right page was stored for only 30 of 52 ([Measuring it](#measuring-it)).

`kb.py crawl minecraft-wiki --core --grow 600` builds it the way a good reference is used instead:

1. **The core**: ~340 pages a survival player asks about, listed by topic in `CORE_PAGES`
   (`services/knowledge/sources.py`): materials and ores, tools and armor, workstations,
   enchanting and brewing, food and farming, redstone components, villagers and trading, the
   common mobs and pets, structures and dimensions, and the tutorials for farms, trading halls,
   doors, portals, bosses and trial chambers.
2. **Grow along shared links**: every page keeps the articles it links to (`meta.links`, from its
   body, not menus or navboxes). `--grow N` fetches the N pages the stored pages link to most
   (`crawler.linked_titles`, at least `--min-links 4` pages pointing to each): what the core keeps
   pointing at (Iron Ingot, Redstone Dust, Bone Meal, Smithing Template) is what fills the gaps.
3. **Leave out what isn't the player's game**: version pages, how to mod, host or script the
   game (`skip_titles`), April Fools and spin-off pages (dropped once fetched, by their own
   categories: [below](#one-edition-one-version)), single designs among dozens
   (`Redstone circuits/Memory/TFF Z3`; the overview pages stay).

`kb.py refresh` asks for all of it again (only what changed is downloaded), and learning while
playing fills what is still missing.

## Sources and licenses

| Source | Kind | License | Notes |
|---|---|---|---|
| `minecraft-wiki` | mediawiki | [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/) ([terms](https://meta.weirdgloop.org/w/Meta:Copyrights)) | built in; includes the wiki's `Tutorial:` pages (farms, redstone builds, mechanisms): the build guides |
| `minecraft-data` | minecraft-data | [MIT](https://github.com/PrismarineJS/minecraft-data/blob/master/LICENSE) (PrismarineJS); the game data in it is Mojang's | built in, **needs your OK to use** (below); recipes, foods, mining for Java 1.21.1 |
| `local` | local | yours | built in; `.md`, `.markdown`, `.txt` in `~/.kindred-spirit/knowledge/local/` |
| anything you add | web / mediawiki / local | what its site says | `kb.py add` or `sources.json` |

Every chunk keeps its page URL, the source's license and its attribution ("Minecraft Wiki
contributors"), and search returns them with the text, so whatever Pip says from it can say
where it came from. The wiki's content is for each player's own local use: it is downloaded to
your computer by you, never shipped in this repository or shared between players (the tests use
made-up pages that only imitate the wiki's markup).

### minecraft-data: the game's own numbers

[PrismarineJS/minecraft-data](https://github.com/PrismarineJS/minecraft-data) publishes, per game
version, JSON extracted from the game: every crafting recipe, item, block (hardness, the tool it
needs, what it drops) and food. Its license is MIT; its README notes that some of the data was
taken from the game and from wikis, so it is used the same way as the wiki: downloaded by each
player to their own computer, never shipped. `kb.py crawl minecraft-data` reads five small files
for Java 1.21.1 (six requests, ~1.3 MB, from raw.githubusercontent.com, whose robots.txt allows it)
and makes a short page per item, "Piston (Java 1.21.1 data)":

```
Crafting: [Crafting recipe for 1 Piston: top row: any Planks, any Planks, any Planks; middle row:
           Cobblestone, Iron Ingot, Cobblestone; bottom row: Cobblestone, Redstone Dust, Cobblestone. ...]
Mining:   Diamond Ore: hardness 3. It needs at least an Iron Pickaxe to drop anything. Mined, it drops Diamond.
Food:     Bread restores 5 hunger (2.5 drumsticks) and 6 saturation.
Used to make: Redstone Dust is used to make: Clock, Compass, Observer, Piston, ...
```

The wiki explains how and why; this says exactly what, for the player's version (the wiki
describes the latest one: [below](#one-edition-one-version)). 1,146 pages, ~3,300 short passages.
Smelting recipes are not in it (the wiki has them).

### Other sources looked at

- **Minecraft's own help articles and minecraft.net** (Mojang): all rights reserved, no license
  that allows copying them into a knowledge base. Not added.
- **Third-party guide sites**: not added; each one's terms would have to be read and allow this.
  The wiki's own `Tutorial:` pages cover farms, trading halls and redstone builds under a known
  license.
- Anything you add yourself goes through `kb.py add` with its license recorded.

### Adding a build-guide site

No third-party build-guide site is shipped: each site's terms would have to be read and allow
copying for this, and the wiki's own `Tutorial:` pages already cover farms, mechanisms and redstone
builds under a known license (`--category Tutorials`). To add a site whose terms allow it (or your
own site):

```bash
python3 services/knowledge/kb.py add my-guides --kind web \
    --sitemap https://guides.example/sitemap.xml --allow https://guides.example/builds/ \
    --license "CC BY-SA 4.0" --license-url https://creativecommons.org/licenses/by-sa/4.0/ \
    --attribution "Example Guides"
python3 services/knowledge/kb.py crawl my-guides --limit 20
```

or a few pages without a sitemap: `--url https://… --url https://…`. It is saved in
`~/.kindred-spirit/knowledge/sources.json`:

```json
{
  "my-guides": {
    "kind": "web", "title": "Example Guides", "sitemap": "https://guides.example/sitemap.xml",
    "allow": ["https://guides.example/builds/"], "license": "CC BY-SA 4.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/4.0/", "attribution": "Example Guides",
    "delay": 2
  }
}
```

A web page is reduced to its readable part (`<main>`/`<article>`; menus, headers, footers,
sidebars, cookie banners and share buttons dropped), cut by its headings. A new kind of source is
a class in `services/knowledge/sources.py` with `discover()` (what to fetch, with a version
token) and `fetch()` (a `Document` of titled sections), added to `KINDS`.

Your own guides need nothing but a file: write `~/.kindred-spirit/knowledge/local/cherry-house.md`
with `#`/`##` headings, then `kb.py crawl local`.

## One edition, one version

The wiki describes the **latest** Java and Bedrock versions (26.x by now) and marks what differs:
"70%[JE only], 75%[BE only]", "Frostbite[upcoming: JE 26.4]", "[until: JE 1.21.5]". Kindred Spirit
was first made for **Java 1.21.1**, and the knowledge base still targets it (`"edition_filter": "java"`,
`"game_version": "1.21.1"` in the wiki's source config), so:

- **Facts for another edition are left out**: "70%[JE only], 75%[BE only]" is stored as "70%";
  "They are part of the monster family[Bedrock Edition only]." is dropped; a section headed
  "Bedrock Edition" or "Basic Bedrock Edition farms" too (`textify.edition_filter`).
- **Upcoming facts are left out** (not even released); "[until: …]" notes are removed and their
  facts kept (true before that version, so for 1.21.1).
- **Every page gets a status**, from the wiki's own categories and History section
  (`textify.wiki_status`), stored with it and returned with every result (`"status"`):

| Status | From | In search |
|---|---|---|
| `current` | everything else | normal |
| `future` | the first Java release in its History is after 1.21.1 (Happy Ghast 1.21.6, Copper Golem 1.21.9, Creaking 1.21.2), or "Java Edition upcoming" | ×0.45; `"since": "1.21.6"` |
| `outdated` | "Outdated tutorials", or "as it formerly worked" in its first lines | ×0.55 |
| `removed` | "Removed …", "Unused …", "(old)" pages | ×0.5 |
| `other-edition` | only in "Bedrock Edition" | ×0.45 |
| `joke`, `spin-off` | "Joke features", "Minecraft Education mobs", "Minecraft Dungeons items", … | not kept |

Only a `current` page answers a question (`covered`). The others stay searchable so Pip can say
"that isn't in this world" (`not_in_this_world()` in `brain/kindred/knowledge.py`), and
`"outdated": true` (anything not current) keeps them out of her answers.

The first version flagged pages "outdated" by category words, which caught the wiki's
housekeeping categories ("Pages needing historical sounds", "Obsolete information" on one
section): Creeper, Enderman, Skeleton, Redstone Repeater, Comparator and Hopper all ranked ×0.55
and could never answer. Only exact category names count now.

**Your game's version decides, when you ask** (#151). The mod tells her brain which Minecraft you're playing, her
prompt names it, and every search sends it (`"game_version": "26.3"`): a page's `future` status is judged again from
its History (`"since"`) against your version, not the one it was fetched for. On 26.3 the Happy Ghast and the Copper
Golem are `current`; on 1.21.1 they're `future`, whatever version the knowledge base was crawled for. Game data from
another version gets a status of its own:

| Status | From | In search |
|---|---|---|
| `other-version` | a `minecraft-data` page made for another version than yours ("Piston (Java 1.21.1 data)" while you play 26.3) | ×0.9; doesn't answer on its own, so she reads the wiki's page for it |

Still crawl-time: facts the wiki marks "[until: JE 1.21.5]" are kept for the version in the source config (true
before then), and "[upcoming: …]" facts are left out.

What the wiki changed *between* 1.21.1 and its latest version on a current page is only in its
History tables, which are dropped: a detail can still be newer than the player's game. The
`minecraft-data` source is exact for 1.21.1 where it applies (recipes, foods, mining).

## What a wiki page becomes

`textify.wiki_sections()` turns an article into sections named by their headings
("Obtaining > Crafting", "Spawning > Natural generation"):

- **the infobox becomes a "Facts" section** and structured fields: `Health points: 20 HP (10
  hearts)`, `Stackable: Yes (64)`, `Blast resistance: 1.5` …
- **crafting grids become sentences and data**: `[Crafting Table recipe for 1 Piston: top row: any
  Planks, any Planks, any Planks; middle row: Cobblestone, Iron Ingot, Cobblestone; bottom row:
  Cobblestone, Redstone Dust, Cobblestone. Uses 3 any Planks, 4 Cobblestone, 1 Iron Ingot, 1 Redstone
  Dust.]`, and on the chunk `{"recipes": [{"station", "grid", "output", "count", "ingredients",
  "shapeless"}]}`. Empty rows and columns are trimmed (the shape is what matters).
- **tables become rows** (`Bamboo Jungle | 95⁄515 | 18.45% | 4`), with the header row repeated on
  every chunk a long table is cut into.
- **dropped**: History, Data history, Gallery, Videos, Trivia, Sounds, Achievements,
  Advancements (the list every mob page repeats), Data values, Block states and tags (identifiers),
  References, Issues, See also, navboxes, edit links, footnote marks, hatnotes, images, and what
  belongs to another edition. Together about 10% of the text, none of it what players ask.

Sections are cut into chunks of at most ~1,200 characters, between paragraphs, then between lines
(tables, lists), then between sentences.

## Search

`KnowledgeStore.search(query, k=5)` blends, for every candidate chunk:

| Signal | How | Weight (with vectors / words only) |
|---|---|---|
| meaning | cosine of the gateway's embeddings | 0.40 / – |
| keywords | FTS5 BM25 (title ×6, section ×2, text ×1; Porter stemming), tempered by how many of the question's words the chunk has | 0.20 / 0.40 |
| title | the page is what the question is about ("make a **piston**" → Piston, "build a **mob farm**" → Tutorial:Mob farm) | 0.15 / 0.25 |
| kind of question | make/craft → Crafting, Obtaining; where/spawn → Spawning, Generation; breed/tame → Breeding; drop → Drops; health/hearts → Facts; build/farm → tutorials … (and those words are added to the keyword search) | 0.15 / 0.25 |
| recipe | a chunk holding the recipe *for* the thing asked about | 0.10 / 0.10 |

The kind-of-question and recipe signals count only for chunks that are **about** what was asked
(the page's title, or the question's subject words in the chunk): asked "how do I make a piston"
before the Piston page is crawled, the Armor Stand's crafting section must not look like an
answer. Each result carries `"about": true/false` for the same reason, so the companion can tell
"here is how" from "here is something nearby". At most 2 chunks per page are returned, so the
top 5 cover several pages. No recency, no
importance: a recipe does not fade. Without an embedding provider (`"embeddings": "none"` in
the gateway) the same search runs on words alone, which already handles the usual questions
well; vectors help when the question's words differ from the page's ("something bright for my
wall" → lanterns). Vectors carry the model's name, like memories: switching the gateway's model
and running `kb.py embed` re-embeds.

### Using it

- **Python**: `import knowledge; knowledge.search("how do I make a piston", k=5)` (with
  `services/` on the path) returns a list of dicts.
- **HTTP**, through the gateway (crawling whole categories is only done with `kb.py`; the one
  write over HTTP is `learn`, bounded, below):

```bash
curl -s http://127.0.0.1:11437/v1/knowledge/search \
     -d '{"query": "how do I make a piston", "k": 3, "max_chars": 800}'
```

```json
{"count": 3, "covered": true, "best": 0.86, "threshold": 0.55, "results": [
  {"title": "Piston", "section": "Obtaining > Crafting",
   "text": "Ingredients | Crafting recipe\nAny Planks + Cobblestone + Iron Ingot + Redstone Dust | [Crafting Table recipe for 1 Piston: ...]",
   "url": "https://minecraft.wiki/w/Piston", "source": "minecraft-wiki",
   "license": "CC BY-NC-SA 3.0", "license_url": "https://creativecommons.org/licenses/by-nc-sa/3.0/",
   "attribution": "Minecraft Wiki contributors (minecraft.wiki)", "edition": "Java and Bedrock, latest versions ...",
   "score": 0.86, "similarity": 0.79, "about": true, "covers": 1.0, "title_match": 1.0, "guide": false,
   "data": {"recipes": [{"output": "Piston", "ingredients": {"...": 1}}]}},
  ...]}
```

  `POST /v1/knowledge/stats` and `/v1/knowledge/sources` answer the obvious. The route is a few
  lines in `services/kindred_gateway.py` (`knowledge_call`), and the module is
  `services/knowledge/api.py`; questions are embedded with the gateway's own embedder, so they
  match the chunks.

### Is it covered?

Every search (CLI `search`, `KnowledgeStore.ask()`, HTTP) says whether the knowledge base really
answers the question: `"covered": true|false`, with `"best"` (the top score) and `"threshold"`.
Covered means the best chunk scores at least **0.55**, its page is `current`
([above](#one-edition-one-version)), and it is about the thing asked:

- its page *is* that thing (title "Piston" for "make a piston"), or
- its page or section is about it ("Tutorial:Combat / Shields"): every subject word in the title
  or the section name (`"in_heading"`), or
- it names every subject word and matches very well (score ≥ 0.72);
- and it isn't a different thing with a similar name ("Smiling Creeper" for a creeper question).

A build or farm question needs a current guide (a `Tutorial:` page, or a web/local source) whose
*title* names the thing in the top 3 (`"title_subject"`): "Tutorial:Iron golem farming" for an
iron farm, not "Tutorial:Building a metropolis" because it says "mob farms" once.

Covered when it isn't is the costly mistake: she answers from a passage that only mentions the
thing, and never listens for the real answer. With the first rule ("every subject word somewhere
in the chunk") "how do I craft a bed" was covered by the Bone Meal page ("use it next to a bed");
on the old knowledge base 10 of 26 "covered" answers were wrong. With these rules and the
recommended set, 1 of 46 ([Measuring it](#measuring-it)).

What the question is about (`store.parse_question`) is shared by search, coverage and learning:
its words minus the kind of question ("make", "spawn", "build"), how ("simple", "best", "level")
and what one does to the thing ("stop", "open", "cure", "defeat": also left out of guide titles,
so "Tutorial:Defeating trial chambers" is about trial chambers); the thing itself is what comes
before a preposition ("a creeper farm *for gunpowder*"); "xp" means experience. A page answers to
the names it gives itself in bold in its first line too ("redstone comparator, or simply
**comparator**"; not the materials a page lists in bold), and the stemmer meets "endermen" and
"enderman", "trading" and "trade".

0.55 was calibrated on the first knowledge base (local embeddings): answers scored 0.66 to 0.86,
near misses 0.54 to 0.68 (those above 0.55 caught by the "about the thing asked" rules). On the
recommended set, right answers score 0.59 to 0.94. On words alone (no embeddings), answers score
higher, so the same threshold is conservative there.

| Question (recommended set) | Best chunk | Score | Covered |
|---|---|---|---|
| how do I make a piston | Piston / Obtaining > Crafting | 0.86 | yes |
| how do I craft a bed (was: Bone Meal, "covered") | Bed / Obtaining > Crafting | 0.91 | yes |
| what does a comparator do | Redstone Comparator (by its name "comparator") | 0.67 | yes |
| how do I get a librarian with mending | Mending / Obtaining, and Librarian | 0.63 | yes (both) |
| how do I build a creeper farm for gunpowder | Tutorial:Creeper farming | 0.80 | yes |
| how do I stop phantoms | Phantom | 0.63 | yes |
| how do I make a simple wheat farm, step by step | Wheat (no wheat-farm guide on the wiki) | 0.79 | no |
| can I get a happy ghast | Happy Ghast (future: Java 1.21.6) | 0.56 | no, marked |
| how do I make a redstone clock | Clock (the item) | 0.86 | yes: the one wrong answer left |

## Learning on demand

When a question isn't covered, the knowledge base can read the pages that answer it right away,
with the crawler's rules: `kb.py learn "how do I build an iron farm"`, `POST
/v1/knowledge/learn {"query": "..."}` or `learn.learn(store, source, fetcher, query, kdir)`.

1. **Find the question** in what was said: "That thing ignored me. How do I tame a parrot?" is
   about parrots; a chatty message with no question about the world ("...What is the coordinates
   of my base? Can you tell me please?") is not looked up at all (`learn.focus`).
2. **Find the pages.** On a wiki that allows its API, its own search (`list=search`). On
   minecraft.wiki, whose robots.txt forbids `api.php` and `Special:Search`, the titles come from its
   sitemaps instead (all ~14,800 articles and ~630 tutorials, with their last edit: two small
   files, reused for a day), ranked against the question (`learn.rank_titles`):
   - the page must be about the question's subject; words that say *how* ("simple", "step by
     step", "best", "level") are not the subject: "a simple wheat farm" is about wheat, not the
     "Simple Block" page it used to learn;
   - the thing itself counts double: the last subject word ("redstone **door**"), or the one
     before a preposition ("a **librarian** with mending", "a **potion** of night vision");
   - a question about two things gets a page for each (Librarian and Mending);
   - tutorials first for build/farm questions, "X Ore" for where-to-find questions, subpages,
     other games and April Fools pets ("Pet Parrot") last.
3. **Read the best few** (3 by default) like the crawler does: robots.txt, one request per
   second, cache, license and URL on every chunk. A page already stored at the same version is
   not fetched again (`"fresh"`). A page that turns out to be a joke or from another game is not
   kept, and the next candidate is read instead (at most 2 extra requests).
4. **Answer**: the HTTP call returns what was added and the new search for the question:

```json
{"status": "learned", "seconds": 2.49, "requests": 3,
 "added": [{"title": "Conduit", "status": "new", "chunks": 13}, {"title": "Conduit Power", "status": "new", "chunks": 7}],
 "covered": true, "best": 0.84, "results": [{"title": "Conduit", "section": "Obtaining > Crafting", "text": "...", "url": "..."}]}
```

`status` is `learned` (new pages), `known` (the right pages were already there), `nothing` (no
page about it), `recent` (this question, in any word order, was looked up in the last 24 hours),
`off`, `capped`, `full` or `busy` (another look-up is running; one at a time, so the wiki sees
one polite visitor). Measured on minecraft.wiki: 2.5 to 3.3 seconds for one question, 3
requests each (robots.txt or a sitemap check, then the pages).

**Bounds**, in `~/.kindred-spirit/knowledge/settings.json` (`kb.py learning` shows and changes them):

| Setting | Default | |
|---|---|---|
| `enabled` | `true` | on during development; `kb.py learning off`, or `KINDRED_KNOWLEDGE_LEARN=0` |
| `max_per_hour` | 20 | look-ups that may reach the network in an hour; then `capped` |
| `pages_per_learn` | 3 | pages read for one question |
| `max_total_mb` | 1024 | database + download cache; above it, `full` |
| `retry_after_hours` | 24 | the same question is not looked up again sooner |
| `index_max_age_hours` | 24 | how long the sitemap title index is reused |
| `source` | `minecraft-wiki` | where look-ups go |

Every look-up is logged (`learn_log` in the database, `kb.py learning` lists the last ones).

**Is 20 an hour, 3 pages each, the right shape?** Yes, as bounds. In the first afternoon of play
there were 9 look-ups in 3 hours; with the recommended set, most questions are covered before
anyone asks (46 of 52 answered at once, [Measuring it](#measuring-it)), so learning is for the long
tail. 20 an hour only stops a loop (60 requests at most, under the wiki's 1 per second); 3 pages
is what one question needs (the thing, its guide, the second thing asked about). What changed is
*which* 3: the look-ups that went wrong in play ("Simple Block" for a wheat farm, the whole
"Tutorials" index for a redstone door, a chatty sentence) are fixed above.

**Why whole pages, not sections?** On minecraft.wiki a page is one request whatever part of it is
needed (sections can only be asked for through `api.php`, which robots.txt forbids), and a stored
page answers the next question about the same thing at once. The section is what Pip *gets*:
for a how-to, the brain asks for the whole section of the best current guide
([below](#current-information-first-and-whole-guides)).

## Measuring it

`kb.py eval` asks the knowledge base 54 questions players ask a companion, by topic (crafting,
materials, farms, redstone, villagers, enchanting, brewing, mobs, structures, survival, and two
about things added after 1.21.1), each with the wiki pages that answer it
(`services/knowledge/eval_questions.json`; `-v` for one line per question, `--json` to keep them):
is a right page stored, first, in the top 3, and does the store say it's covered, rightly or not.

| | first knowledge base (main) | same store, new code | recommended set | + minecraft-data |
|---|---|---|---|---|
| pages / chunks | 381 / 7,991 | 381 / 7,991 | 1,161 / 19,089 | 2,307 / 22,378 |
| a right page stored | 30 of 52 | 30 | **52** | 52 |
| right page first | 19 | 23 | **47** | 47 |
| right page in the top 3 | 21 | 25 | **49** | 49 |
| covered, rightly | 16 | 19 | **45** | 45 |
| covered, wrongly | 10 | 4 | **1** | 1 |
| after 1.21.1: answered as if current | 2 of 2 | 2 | **0** | 0 |

With minecraft-data, crafting questions get the exact 1.21.1 recipe first ("Piston (Java 1.21.1
data)"), counted as the page it's about. Learning, run for real on a copy of the first knowledge
base: "a librarian with mending" read Librarian and Mending (2.5 s, 3 requests) and became
covered; "a simple wheat farm, step by step" no longer reads "Simple Block"; the 14:49 chatty
message is not looked up.

## Size and speed

Measured on a MacBook Air (M4), minecraft.wiki, local embeddings (bge-small, 384 numbers per chunk).

| | first knowledge base | recommended set (`--core --grow 600`) |
|---|---|---|
| pages, chunks | 381, 7,991 | 1,161, 19,089 (16 per page, ~580 characters each) |
| crawl | 1.7 s per page | the core (271 new pages, big ones) in 10.5 min, 2.3 s each; the 600 more in 14 min, 1.4 s each; ~38 MB downloaded |
| database | 32.5 MB (85 KB per page) | 48.3 MB (42 KB per page: 16-bit vectors, ~10% less text) |
| download cache | 20 MB | 58 MB (`kb.py remove minecraft-wiki --cache` to drop it; refreshes then download again) |
| search, inside the gateway (no numpy) | ~170 ms | ~90 ms warm (pages first, then their chunks); 440 ms for the very first |
| search with numpy | | ~58 ms |
| reindex from the cache | 42 s | ~2 min |
| minecraft-data | | 1,146 pages, 3,289 chunks, 6 requests, 38 s (embedding), +5 MB |

Without numpy (the gateway's Python has none), a store above 4,000 chunks is searched page by
page first: each page's mean vector is compared, then only the chunks of the 60 nearest pages and
the keyword hits (`KnowledgeStore.PURE_FULL_SCAN`, `PURE_PAGES`). On the 54 questions the answers
are the same as comparing every chunk. With numpy every chunk is compared.

## Files

```
~/.kindred-spirit/knowledge/
  knowledge.db       pages, chunks, vectors, the crawl queue (SQLite, WAL)
  cache/             raw downloads by site (gzip), for 304s and --offline
  local/             your own .md/.txt guides (the "local" source)
  sources.json       sources you added
```

`KINDRED_KNOWLEDGE` points elsewhere (or `--dir`); `KINDRED_GATEWAY_URL` is the gateway the CLI
asks for embeddings (default `http://127.0.0.1:11437/v1`; any OpenAI-style `/embeddings` address
works, e.g. a second `services/embed_server.py` with `KINDRED_EMBED_PORT=8992`, to build without
touching the gateway you are playing with).

### Swapping in a rebuilt knowledge base

Build a new one next to the live one, never in it while the game is connected (the gateway keeps
the database open):

```bash
K=~/.kindred-spirit/knowledge; N=~/.kindred-spirit/knowledge-new
mkdir -p $N && cp -R $K/cache $N/ && cp $K/settings.json $N/ 2>/dev/null   # the cache: fewer downloads
sqlite3 $K/knowledge.db ".backup '$N/knowledge.db'"                         # a safe copy of an open database
python3 services/knowledge/kb.py --dir ~/.kindred-spirit/knowledge-new reindex
python3 services/knowledge/kb.py --dir ~/.kindred-spirit/knowledge-new crawl minecraft-wiki --core --grow 600
python3 services/knowledge/kb.py --dir ~/.kindred-spirit/knowledge-new compact
python3 services/knowledge/kb.py --dir ~/.kindred-spirit/knowledge-new eval
```

Then, with the game closed:

```bash
scripts/stop.sh
mv ~/.kindred-spirit/knowledge ~/.kindred-spirit/knowledge-before
mv ~/.kindred-spirit/knowledge-new ~/.kindred-spirit/knowledge
scripts/start.sh --background
```

Pages learned while playing after the copy was made are in `knowledge-before` only:
`kb.py --dir ~/.kindred-spirit/knowledge-before learning` lists the last look-ups, and `kb.py learn
"..."` brings any of them back. `knowledge-before` can be deleted once you're happy.

## Current information first, and whole guides

- **Only current pages answer.** Pages about an older version ("Outdated tutorials", "as it
  formerly worked prior to Java Edition 1.14"), added after the player's version, removed, or only
  in Bedrock stay searchable but score lower, are flagged `"outdated": true` with their `"status"`,
  and never count as covering a question, so she learns the current page instead
  ([One edition, one version](#one-edition-one-version)).
- **A build question needs a real guide.** It counts as covered only by a current guide whose title
  names the thing ("Tutorial:Iron golem farming"), not a paragraph in a general tutorial.
- **Whole sections.** `POST /v1/knowledge/section {"chunk_id": id}` (or `{"page": title, "name":
  "tower", "start": n}`) returns all the passages of a section in order, up to `max_chars`, with
  `more`, `next_start`, `next_section` and the page's `outline`. For a how-to, Pip gets the whole
  section of the best current guide and guides you step by step; her `listen_more` tool fetches the
  next part, or a part by name, instead of guessing. The dashboard's Knowledge tab shows the whole
  section of any result.

## How Pip uses it

Wired in `brain/kindred/knowledge.py` and `Brain.world_answer` / `listen_to_the_world`
(`brain/kindred/server.py`): every question about how the world works (not about her or you, and
not a request for one of her powers) is searched first. Covered: the top passages go to the AI as
"What the world remembers". Not covered: she says she'll listen, looks around while the brain calls
`learn`, and comes back with what the stones told her (about 15 s measured). As planned below:

**She stays in her world.** Minecraft is Pip's real world and she is a spirit of it: she never
mentions books, the internet, a wiki or "looking something up". What the knowledge base holds is,
to her, what the world remembers: the old stones remember everything that's been built, the wind
has passed over every village. Sources, URLs and licenses stay in the data (logs, dashboard),
never in her words.

**1. A tool in her world's terms**, next to `remember`/`forget` in `MEMORY_TOOLS`
(`brain/kindred/tools.py`) and in `TALK_TOOLS` (`brain/kindred/mind.py`) so she can use it while
talking:

```python
_fn("listen_to_the_world", "Listen to what the world remembers about how things work here: what things "
    "are made from, where creatures live, how to breed or tame them, how redstone behaves, how farms "
    "and builds are put together. Use it before saying any such fact you are not sure of.",
    {"query": {"type": "string", "description": "the question, in plain words"}}, ["query"]),
```

handled by `POST {gateway}/knowledge/search {"query": q, "k": 3, "max_chars": 900}` (the brain
already talks to the gateway for `/memory/...` in `GatewayMemory`), giving the AI each result as
`"<title> / <section>: <text>"` (no URL). Her instructions gain one line: *"For how things work in
the world, listen to the world and say only what it tells you; if it is quiet, say so, never
guess."*

**2. Learning while you play**, when the search says `"covered": false`:

1. **She answers at once, in her world**: *"The old stones remember everything that's been
   built... let me listen for a moment."* or *"The wind passes over every village, maybe it
   heard how."* No invented fact, no silence.
2. **She listens**: she drifts off a few blocks and turns slowly, as if listening, while the brain
   calls `POST /v1/knowledge/learn {"query": q}` in the background (a task that doesn't block the
   conversation: 2.5 to 3.3 s measured, up to ~15 s if the wiki is slow).
3. **She comes back with the answer** when it returns `"covered": true`: the brain hands the AI the
   returned `results` as what the world just told her, and she floats back and says it, like her
   slow power awakening: *"The stones told me about iron golems! Villagers who sleep and work
   together, and a golem appears when..."* If it comes back `nothing`/`capped`/`off`/`busy` or still
   not covered: *"The stones are quiet about that one... maybe we'll figure it out together."*,
   once, and she moves on.
4. **Next time she already knows**: the pages stay in the knowledge base, so the same question (or a
   close one) is covered at once and she answers without listening; `learn` refuses to look up
   the same question twice in 24 hours (`"recent"`).

Later, recall can also do it unasked: when the player's message is a question about how the world
works (make, craft, spawn, breed, farm, build, where/how + a game word), the top 2 chunks of a
covered search go into her context next to her memories, under "What the world remembers".
