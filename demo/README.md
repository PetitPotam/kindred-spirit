# The demo video

The demo is filmed by the game itself, with the same scripted sandbox used for testing, so anyone
can re-record it after a change and get the same shots. Pip's answers are live (real speech-to-text
and AI), so every take is a little different.

```bash
scripts/start.sh --background                       # the brain and voices
cd demo && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ..
brain/.venv/bin/python demo/make_voices.py          # the player's lines (a second Kokoro voice)
cd mod && ./gradlew runClient -PdevScript=../demo/demo-script.txt -PvideoSize=960x540 && cd ..
demo/.venv/bin/python demo/make_video.py            # -> demo/out/kindred-spirit-demo.mp4
```

Needs ffmpeg (`brew install ffmpeg`). `-PvideoSize=960x540` gives 1920x1080 on a Retina screen.

**The tour** (`tour-script.txt`, about 5 minutes) is the long version: Pip's journey from a first
meeting to old friends, and everything she does on the way (finding, guiding, chopping, warnings,
protecting, staying out of your swing, the knowledge base, feelings, spam, power modes, night glow,
skins). Part 1 is filmed in one world; part 2 in another, after `/kindred memory import` brings in
her memories of a longer journey with a made-up player, written by `seed_journey.py`:

```bash
brain/.venv/bin/python demo/seed_journey.py         # her memories "weeks later" (made up, its own world)
brain/.venv/bin/python demo/make_voices.py t_       # the player's lines for the tour
cd mod && ./gradlew runClient -PdevScript=../demo/tour-script.txt -PvideoSize=960x540 && cd ..
demo/.venv/bin/python demo/make_video.py tour       # -> demo/out/kindred-spirit-tour.mp4
```

| File | What it does |
|---|---|
| `demo-script.txt` | the shots: world setup, camera moves, what the player says, `mark` chapters |
| `tour-script.txt` | the long tour (two worlds; `caption` lines become notes in the edit) |
| `seed_journey.py` | her prepared memories for the tour's "weeks later" |
| `make_voices.py` | the player's spoken lines (sent through the real push-to-talk path) |
| `make_music.py` | a cozy background track made from scratch (no samples, no copyright) |
| `make_video.py` | the edit: chapters, captions, title and end cards, crossfades, voices, music ducking, -14 LUFS |

The recorder (`mod/.../record/FrameRecorder.java`) reads each finished frame and pipes it to ffmpeg
at a steady 30 fps of real time, and saves every line the companion says with its time, so the
voices land exactly where they happened. Script steps for filming (`video`, `record`, `mark`, `turn`,
`track`, `walk`, `voice`) are listed in `DevScript.java`.
