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
  web sites       ─┼─▶ discover ▶ queue ▶ fetch ▶ clean ▶ chunk ──▶          └─ vectors (meaning,
  your .md files  ─┘   (resumes after a stop; refetches only           from the gateway's /v1/embeddings)
                        what changed)                                       │
                                                         gateway /v1/knowledge/search ◀── Pip
```

It is kept apart from her memories (`services/memory_store.py`): those are what she lived with
you, this is what the world says about the game.

## Quick start

```bash
cd ~/Developer/kindred-spirit
python3 services/knowledge/kb.py crawl minecraft-wiki --category Mobs --limit 50
python3 services/knowledge/kb.py search "where do zombies spawn"
```

| Command | What it does |
|---|---|
| `kb.py sources` | the sources, their licenses and terms, what is stored from each |
| `kb.py crawl minecraft-wiki` | a first crawl takes the starter categories (mobs, biomes, tutorials, redstone, food, plants, enchantments, ores, structures, utility blocks, mechanisms, tools, weapons, armor, gameplay); after a stop it just continues |
| `kb.py crawl minecraft-wiki --category Mobs --limit 50` | one category (and its subcategories, `--depth 1`), at most 50 pages this time |
| `kb.py crawl minecraft-wiki --page Piston --page "Tutorial:Mob farm"` | given pages |
| `kb.py crawl minecraft-wiki --all` | every article in the wiki's sitemap (version-history pages skipped): about 10,000 pages, several hours |
| `kb.py crawl local` | your own Markdown/text files in `~/.kindred-spirit/knowledge/local/` |
| `kb.py refresh` | every source again, fetching only pages that changed |
| `kb.py search "how do I make a piston" [-k 5] [--json] [--full]` | ranked chunks with their source and license |
| `kb.py learn "how do I build an iron farm"` | read the few wiki pages that answer one question, now ([below](#learning-on-demand)) |
| `kb.py learning [on\|off] [--per-hour N] [--pages N] [--max-mb N]` | on-demand learning settings and the last look-ups |
| `kb.py stats` | pages, chunks, vectors, size on disk, queue, when last fetched |
| `kb.py reindex` | rebuild every stored page from the download cache, no network (after a parser change) |
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
  disallowed, so only the first 200 of a big category are taken (the crawler says so). Most big
  categories have subcategories (crawled with `--depth 1`); `--all` uses the sitemap instead.
- The same robots.txt blocks named AI crawlers (GPTBot, ClaudeBot, CCBot, …) from everything.
  This tool is not one of those (a player's own slow, local fetcher that is never redistributed),
  and it is held to the rules for every other agent. If the wiki ever names it, it stops.

## Sources and licenses

| Source | Kind | License | Notes |
|---|---|---|---|
| `minecraft-wiki` | mediawiki | [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/) ([terms](https://meta.weirdgloop.org/w/Meta:Copyrights)) | built in; includes the wiki's `Tutorial:` pages (farms, redstone builds, mechanisms): the build guides |
| `local` | local | yours | built in; `.md`, `.markdown`, `.txt` in `~/.kindred-spirit/knowledge/local/` |
| anything you add | web / mediawiki / local | what its site says | `kb.py add` or `sources.json` |

Every chunk keeps its page URL, the source's license and its attribution ("Minecraft Wiki
contributors"), and search returns them with the text, so whatever Pip says from it can say
where it came from. The wiki's content is for each player's own local use: it is downloaded to
your computer by you, never shipped in this repository or shared between players (the tests use
made-up pages that only imitate the wiki's markup).

The wiki describes the **latest** versions of Java and Bedrock and marks the differences
("[JE only]", "[BE only]", "[upcoming …]"). Kindred Spirit runs on Java 1.21.1, so newer features
can appear in the text; the edition note is stored with every page.

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
- **dropped**: History, Data history, Gallery, Videos, Trivia, Sounds, Achievements, References,
  Issues, See also, navboxes, edit links, footnote marks, hatnotes, images.

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
Covered means the best chunk scores at least **0.55** and is about the thing asked: its page *is*
that thing (title "Piston" for "make a piston"), or it holds every subject word of the question
without being a different thing with a similar name ("Smiling Creeper" for a creeper question is
not an answer). A build or farm question also needs a guide (a `Tutorial:` page, or a web/local
source) about it in the top 3.

0.55 was calibrated on the real knowledge base below (local embeddings): the answers to the
questions tried scored 0.66 to 0.86. Near misses scored from 0.54 (a beacon question with no
Beacon page) to 0.68 ("Smiling Creeper" for a creeper question); the ones above 0.55 were all
caught by the "about the thing asked" rule. On words alone (no embeddings), answers score higher
(0.6 to 1.0), so the same threshold is conservative there. A known soft spot: a general guide
that mentions the thing can count as covered ("how do I make a diamond pickaxe" is answered by the
crafting section of an old beginner's guide, 0.65, while there is no Diamond Pickaxe page yet).

| Question | Best chunk | Score | Covered |
|---|---|---|---|
| how do I make a piston | Piston / Obtaining > Crafting | 0.86 | yes |
| where do creepers spawn | Creeper / Spawning | 0.86 | yes |
| how do I breed cows | Cow / Breeding | 0.80 | yes |
| how do I build an iron golem farm | Tutorial:Door-based iron golem farming / Tower design | 0.74 | yes |
| how does a redstone repeater work | Redstone Repeater / Summary | 0.70 | yes |
| how do I grow wheat faster | Wheat / Obtaining > Farming | 0.74 | yes |
| how much health does a ravager have | Ravager / Facts | 0.82 | yes |
| what biome do pandas live in | Panda / Spawning | 0.75 | yes |
| how do I make a beacon (no Beacon page yet) | Tutorial:Achievement guide / The Beaconator | 0.54 | no |
| ... after `kb.py learn` (3.3 s) | Beacon / Obtaining > Crafting | 0.84 | yes |

## Learning on demand

When a question isn't covered, the knowledge base can read the pages that answer it right away,
with the crawler's rules: `kb.py learn "how do I build an iron farm"`, `POST
/v1/knowledge/learn {"query": "..."}` or `learn.learn(store, source, fetcher, query, kdir)`.

1. **Find the pages.** On a wiki that allows its API, its own search (`list=search`). On
   minecraft.wiki, whose robots.txt forbids `api.php` and `Special:Search`, the titles come from its
   sitemaps instead (all ~14,000 articles and ~630 tutorials, with their last edit: two small
   files, reused for a day), ranked against the question: the page must be about the question's
   subject ("iron", "zombie"), the closer its title the better, tutorials first for build/farm
   questions, subpages and spin-off games last.
2. **Read the best few** (3 by default) like the crawler does: robots.txt, one request per
   second, cache, license and URL on every chunk. A page already stored at the same version is
   not fetched again (`"fresh"`).
3. **Answer**: the HTTP call returns what was added and the new search for the question:

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

## Size and speed

Measured on a MacBook Air (M4), minecraft.wiki, local embeddings (bge-small, 384 numbers per chunk):
371 pages (154 mobs, ~190 tutorials, ~25 blocks, items and biomes), 7,812 chunks.

| | |
|---|---|
| speed | 1.7 s per page at the default 1 request/second (fetch, clean, chunk, embed); 50 pages in 112 s |
| download | ~42 KB per page (gzip), plus one request per category page |
| chunks | ~21 per page, ~650 characters each (4.5 MB of text for 366 pages) |
| database | ~85 KB per page with vectors (31.7 MB for 371 pages) |
| cache | ~45 KB per page (raw pages, gzip; 16 MB) |
| search | ~170 ms from the CLI with the question embedded through the gateway; a few ms on words alone |
| reindex | 366 pages from the cache in 42 s, no network |

So, extrapolating: 1,000 pages take about 30 minutes and ~130 MB (database and cache); the
whole wiki with `--all` (~10,000 articles once version pages are skipped) about 5 hours and
~1.3 GB. `kb.py remove minecraft-wiki --cache` gives it all back.

## Files

```
~/.kindred-spirit/knowledge/
  knowledge.db       pages, chunks, vectors, the crawl queue (SQLite, WAL)
  cache/             raw downloads by site (gzip), for 304s and --offline
  local/             your own .md/.txt guides (the "local" source)
  sources.json       sources you added
```

`KINDRED_KNOWLEDGE` points elsewhere (or `--dir`); `KINDRED_GATEWAY_URL` is the gateway the CLI
asks for embeddings (default `http://127.0.0.1:11437/v1`).

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
