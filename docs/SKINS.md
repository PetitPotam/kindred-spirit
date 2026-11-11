# Making a skin

A skin decides how your companion looks: its **shape**, an optional **texture** wrapped around it,
and a few **colors**. The face (eyes, mouth, cheeks) is drawn by the mod on top, so a plain texture
already gets a cute face. Switch skins in game with `/kindred skin <name>`; `/kindred skins` lists them.

## The quickest way: drop a PNG

1. Make an image twice as wide as it is tall, for example **64×32** (bigger works too).
2. Put it in your game folder under **`config/kindredspirit/skins/`**, e.g. `config/kindredspirit/skins/peach.png`.
3. In game: `/kindred skins reload`, then `/kindred skin peach`.

How the image wraps: like a world map around a globe. Left to right goes once around the body,
top to bottom goes from the top of its head to the bottom. **The face is a quarter of the way across
from the left, in the middle vertically**; the back is three quarters across.

## More control: add a JSON file

Next to `peach.png`, create `peach.json` (same name) to choose the shape and colors. Every field is
optional:

```json
{
  "name": "Peach",
  "shape": "ball",
  "texture": "peach.png",
  "tint": "none",
  "shell": false,
  "face": true,
  "eyes": "#2B1B17",
  "mouth": "#5A2A2A",
  "cheeks": "#FF9E9E",
  "size": 1.0,
  "glow": false
}
```

| Field | Values | What it does |
|---|---|---|
| `name` | text | shown in `/kindred skins` |
| `shape` | `ball`, `cube`, `wisp`, `fairy` | the body. `cube` has soft corners; `wisp` floats instead of hopping, glows and is a bit smaller; `fairy` floats, glows softly and has wings |
| `texture` | a PNG in the same folder, or `namespace:path.png` from a resource pack | wrapped around the body |
| `tint` | `mood`, `none`, `"#RRGGBB"` | `mood`: the color follows its mood (green happy, pink scared...). `none`: your texture as is |
| `shell` | `true` / `false` | a glassy outer shell with a darker core inside (the slime look) |
| `shellOpacity` | 0.05 – 1 | how see-through the shell is |
| `face` | `true` / `false` | turn the drawn face off if your texture has its own |
| `eyes`, `mouth`, `cheeks` | `"#RRGGBB"`; cheeks can be `"none"` | face colors. It still blushes when shy, even with no cheeks |
| `size` | 0.3 – 3 | 1 is about a slime's head |
| `glow` | `true` / `false` | ignores darkness, like a little lantern |
| `wings` | `true` / `false` | two pairs of fluttering wings on its back (on by default for fairies; any shape can have them) |
| `wingColor` | `"#RRGGBB"` or `"mood"` | `mood`: the wings take a pastel version of its mood color |
| `wingOpacity` | 0.05 – 1 | how see-through the wings are |

A JSON without a texture is fine too: `{"shape": "cube", "tint": "#7FB3FF"}` is a blue cube.

## In a resource pack (to share skins)

Put the JSON in `assets/kindredspirit/skins/<id>.json` and the texture anywhere in the pack, referenced
as `"texture": "yourpack:textures/whatever.png"`. Enable the pack and press F3+T. Skins with the same id
as a built-in one replace it.

## Built-in skins

| id | look |
|---|---|
| `slime` | the classic: glassy, color follows its mood |
| `slime_cube` | the same in a soft cube |
| `wisp` | a small glowing orb with a halo |
| `strawberry` | a textured example (`mod/src/main/resources/assets/kindredspirit/textures/skins/strawberry.png`) |
| `starry` | a glowing wisp with a starry-night texture |
| `fairy` | a pink fairy whose wings show its mood |
| `pixie` | a green fairy with sky-blue wings |

The built-in textures are drawn by `scripts/make_art.py`: a good place to see how a texture maps.
