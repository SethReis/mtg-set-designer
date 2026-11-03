# Card renderer

```python
from setdesigner.render import CardRenderer

with CardRenderer(project) as renderer:       # starts MSE in the background (~4 s, once)
    image = renderer.render(card, face=0)     # PIL image, 375 x 523 for M15
    card.faces[0].rules_text = "..."          # after an edit:
    renderer.card_changed(card)
    image = renderer.render(card)             # ~0.25 s
    renderer.render_set(out_dir)              # every face, for printing
```

**Real Magic Set Editor draws the cards** (`mse_service.py`): its rendering is the reference
for its templates, and only its *editor* is clunky. One `magicseteditor.com --cli` process runs
in the background, invisible to users.
- **Preview:** a one-card set (the card's faces only) is written, loaded (~70 ms) and rendered
  (~150 ms). Set-wide values are baked in (collector numbers from our `ScriptEnvironment`,
  reminder policies in the text), so it equals a render from the whole set
  (`tests/render/test_mse_service.py`). Reloading a whole 250-card set would take 1.6 s per edit.
- **Print:** `render_set` loads the whole set once and renders every face.
- **Set symbol:** MSE only draws its own `.mse-symbol` files, so it gets an empty symbol and our
  rarity symbol is drawn on top.
- **Fonts:** MSE only uses fonts Windows knows, and the Magic fonts (Matrix, MPlantin, Beleren,
  ...) are not normally installed. Without them it silently substitutes others (Arial in the 8th
  Edition frame). So `register_fonts` adds `resources/fonts/` for this Windows session before
  MSE starts. Nothing is installed, and the fonts are removed again when Python exits.
- **Planeswalkers** use the frame's planeswalker stylesheet (`mse/frames.py`). Their rules
  text lines `+1: ...` become MSE's loyalty cost fields (`mapping.loyalty_abilities`).
- **Universes Beyond** is not its own template: it's M15 Main with the styling option
  `frames: universes beyond`. Frames like this are listed in `mse/frames.FRAME_STYLING`.
  - Each card carries its styling options (`MSECard.styling`). The set file writes them the
    way MSE does, as `has_styling: true` plus a `styling_data:` block.
  - Our script environment gives such cards their own `styling` object, so the built-in
    renderer agrees with MSE.
  - Planeswalker templates have no UB option, so a UB planeswalker uses the regular M15
    planeswalker frame.
- **Crashes / hangs:** the process is restarted and the render retried once (tested).
- **Fallback:** if MSE is missing or fails, `CardRenderer` uses our own renderer (below) and
  says so in `last_backend` / `warnings`. MSE is found at `$SETDESIGNER_MSE`, else
  `Full-Magic-Pack-main/magicseteditor.com`; it uses the templates in its own `data/` folder.

`python tools/render_cards.py OUT [project folder] [--builtin]` renders every face;
`python tools/compare_renders.py OUT` puts our own renderer next to real MSE's renders.

## The built-in renderer (fallback)

## Design: a neutral layout in the middle

```
our Card ──(MSE adapter: mse_layout.py, stylesheet.py, symbol_font.py)──▶ CardLayout ──(engine: draw.py, text.py, fonts.py)──▶ picture
```

- **`layout.py`** is the renderer's own description of a card: a canvas plus layers, where a
  layer is an `ImageLayer` (box, picture, blend mode, alignment) or a `TextLayer` (box, tagged
  text, font, symbol font, alignment, padding, line heights, shrink limits, mask shape). It
  contains no MSE concepts.
- **The engine** (`draw.py`, `text.py`, `fonts.py`, `symbol.py`) only knows `CardLayout`.
- **The MSE adapter** turns an MSE stylesheet's card style entries plus a card into a
  `CardLayout`, evaluating the stylesheet's scripts exactly as MSE does. Other producers (our own
  template format, per-set tweaks) can be added later without touching the engine or the UI.

We reuse MSE's *template packages* (frames, fonts, mana symbols, their scripts), not MSE's
*application*. None of MSE's UI or its ~50 raw style options reach our users.

## How it matches MSE

- **Boxes:** any two of left/width/right (top/height/bottom) give the third; z order with
  `card style` before `extra card style`; invisible or sizeless entries are skipped.
- **Content sizes:** scripts may ask for other entries' laid-out content
  (`card_style.casting_cost.content_width`). These are computed on demand; single-line
  content is measured at its natural width, and values that depended on a half-computed size
  are never cached.
- **Images:** choice-like fields draw their `image` / `choice images` at box size (stretch,
  or fit when aligned), masked, with their blend mode; art is our image (cover-fit) or the
  style's default; color fields fill a border ring or tint their mask. Resizing is MSE's own
  area-averaging resampler (`gfx/resample_image.cpp`), ported bit for bit.
- **Text** (port of MSE's text viewer): tags → styled pieces (`<b…>`, `<i…>`, `<sym…>`,
  `<soft>`, `<line>`, `<soft-line>`, `<size:>`, `<color:>`, `<font:>`), greedy wrapping, line
  heights per break kind (a line is as high as its tallest piece; an empty line keeps the
  height of the one above, 0 after `<line>`; a word whose trailing space overflows still ends
  the line), MSE's scale search (quarter-point steps), horizontal squeeze only for
  `shrink`/`stretch` alignments (other text runs past its box), vertical centering, gap
  stretching up to the `*_max` heights stop by stop, shadow (MSE's blur), stroke.
- **Drawing text like Windows GDI does for MSE** (`gfx/resample_text.cpp`): every run is drawn
  at 4× size on a quarter-pixel grid and box-averaged down; its cell hangs from the line's top
  (no shared baseline). Font sizes are `round(points × scale × 4 × 96/72)` pixels at 4×; line
  heights come from the fonts' Windows metrics (OS/2 `usWinAscent + usWinDescent`, ~17% more
  than `hhea` for MPlantin); widths have no kerning. A missing bold file is simulated the
  Windows way: each glyph overstruck by one 4× pixel and its advance one 4× pixel wider.
- **Mana symbols:** `.mse-symbol-font` packages, symbols tried in file order (literal or
  regex). A symbol takes `natural × int(size) // int(image font size)` plus `horizontal space`
  / `vertical space` pixels in the line, and is drawn at `natural × size / image font size`,
  centred (by the symbol font's alignment) in that slot as high as the line. Numbers on
  generic circles are MSE text: a cell that must fit the margins, shrunk by quarter points.
- **Fonts:** files found by family, full or PostScript name.
- **Set symbol (our own):** the user's SVG/PNG shape, filled per rarity (common black with a
  white outline; uncommon silver, rare gold, mythic orange-red, special purple gradients) via the
  `symbol_variation` built-in that the frames already call. A rounded square is used when no
  symbol is set.

## Verified

`tests/render/test_render_oracle.py` compares 16 whole cards (both fixture sets) with
`write_image_file(input: card)` renders from real MSE. Outside text boxes (rarity symbol
excluded) the mean difference is ≤ 0.25 / 255 (measured 0.00–0.01: the same pixels); inside
text boxes ≤ 6 / 255 (measured 0.3–4.5), and in every text box the first and last inked rows
are within 1 px. Text is not pixel-identical because FreeType's glyph outlines and hinting
differ a little from GDI's; positions match to a quarter pixel. All five frames (M15, 8th,
Old, 4th, Alpha/Beta) render without warnings.

## Known gaps

- Rotated boxes are rotated around their center (MSE pivots on the anchored corner); M15 only
  rotates for sideways cards.
- Not implemented: justified alignment, `<li>` bullets, `paragraph height` slots, per-card
  styling options in the UI, hyphenation.
- Glyph shapes come from FreeType, not GDI: widths can differ by a fraction of a pixel per
  line, so a line that only just fits can wrap differently from MSE in rare cases.
- A word too long for a whole line is not broken mid-word (MSE breaks it).
- MSE draws a see-through image area as a checkerboard; ours stays transparent.
