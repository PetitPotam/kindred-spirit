# The demo video

The demo is filmed by the game itself, with the same scripted sandbox used for testing, so anyone
can re-record it after a change and get the same shots. Pip's answers are live (real speech-to-text
and AI), so every take is a little different.

```bash
scripts/start.sh --background                       # the brain and voices
cd demo && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ..
brain/.venv/bin/python demo/make_voices.py          # the player's lines (a second Kokoro voice)
cd mod && ./gradlew :1.21.1:runClient -PdevScript=../demo/demo-script.txt -PvideoSize=960x540 && cd ..
demo/.venv/bin/python demo/make_video.py            # -> demo/out/kindred-spirit-demo.mp4
```

Needs ffmpeg (`brew install ffmpeg`). `-PvideoSize=960x540` gives 1920x1080 on a Retina screen.
`-PplayerName=Sam` gives the dev player a name (otherwise a random "Player123", which she reads and remembers), and
`-PguestVideoSize=640x360` sizes the second game (`runGuest`) when both record. Each recording's `events.jsonl`
starts with `"wall"`, the computer's clock at video time 0, to line up a dashboard recording made at the same time.

**The tour** (`tour-script.txt`, about 5 minutes) is the long version: Pip's journey from a first
meeting to old friends, and everything she does on the way (finding, guiding, chopping, warnings,
protecting, staying out of your swing, the knowledge base, feelings, spam, power modes, night glow,
skins). Part 1 is filmed in one world; part 2 in another, after `/kindred memory import` brings in
her memories of a longer journey with a made-up player, written by `seed_journey.py`:

```bash
brain/.venv/bin/python demo/seed_journey.py         # her memories "weeks later" (made up, its own world)
brain/.venv/bin/python demo/make_voices.py t_       # the player's lines for the tour
cd mod && ./gradlew :1.21.1:runClient -PdevScript=../demo/tour-script.txt -PvideoSize=960x540 && cd ..
demo/.venv/bin/python demo/make_video.py tour       # -> demo/out/kindred-spirit-tour.mp4
```

**The showcase** (`showcase-script.txt`, about 4 minutes) is what she does in singleplayer today:
meeting her, finding and leading, mining and chopping with your tools, crafting help, a cottage from a
blueprint, effects and enchanting, warnings and protection, taking you back to a place she remembers,
feelings, her glow at night, skins, and a card about playing with friends on LAN:

```bash
brain/.venv/bin/python demo/make_voices.py s_       # the player's lines for the showcase
cd mod && ./gradlew :1.21.1:runClient -PdevScript=../demo/showcase-script.txt -PvideoSize=960x540 && cd ..
demo/.venv/bin/python demo/make_video.py showcase   # -> demo/out/kindred-spirit-showcase.mp4
```

| File | What it does |
|---|---|
| `demo-script.txt` | the shots: world setup, camera moves, what the player says, `mark` chapters |
| `tour-script.txt` | the long tour (two worlds; `caption` lines become notes in the edit) |
| `showcase-script.txt` | the singleplayer showcase (a fresh world each take: a /fill is at most 32768 blocks, so the stage is cleared in strips) |
| `seed_journey.py` | her prepared memories for the tour's "weeks later" |
| `make_voices.py` | the player's spoken lines (sent through the real push-to-talk path) |
| `make_music.py` | a cozy background track made from scratch (no samples, no copyright) |
| `make_video.py` | the edit: chapters, captions, title and end cards, crossfades, voices, music ducking, -14 LUFS |

The recorder (`mod/.../record/FrameRecorder.java`) reads each finished frame and pipes it to ffmpeg
at a steady 30 fps of real time, and saves every line the companion says with its time, so the
voices land exactly where they happened. Script steps for filming (`video`, `record`, `mark`, `turn`,
`track`, `walk`, `voice`) are listed in `DevScript.java`.
