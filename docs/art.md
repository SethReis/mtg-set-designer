# Card art and the set symbol

## Adding art

In the card editor's **Art** section:
- click the drop zone to choose a file;
- drop an image onto the drop zone or the card preview;
- or paste an image with Ctrl+V (pasting text into fields works as usual).

In the overview you can also drop an image onto any card. All three ways go through
`app/assets.import_art`:
- the file is **copied into the set** as `assets/art/<card id>.<ext>` (a back face gets
  `<card id>-2.<ext>`), replacing that card's earlier art;
- PNG, JPEG and WebP files are kept as they are; other formats are converted to PNG;
- the card stores the path relative to the set folder (`Face.art_path`), so the set folder
  can be moved or shared.

Dropped and pasted files are sent with `fetch` to `POST /api/art/<card id>` (`ui/uploads.py`)
rather than over the page's websocket, which limits message sizes. The route can't reach the
page that sent the file, so it bumps `session.art_version` and leaves a
`session.art_notice`; both pages check these in their timers.

## Choosing what shows (the crop)

The editor shows the whole image with the frame's art box as a yellow rectangle. Drag it
to move it and use the Zoom slider; **Reset** returns to the default. The crop is saved
as `Face.art_crop` (`x`, `y` = the crop's centre within the image, from 0 to 1;
`zoom` ≥ 1). `None` means the default: the largest rectangle of the box's shape, centred.
The original file is never changed. The maths is in `app/art.py`.

The box's shape depends on the frame (M15's art box is 316 × 231, 8th Edition's 311 × 228,
...). `SetSession.find_art_box` looks it up once per stylesheet.

## How the renderers draw it

- **MSE** only reads art stored inside the `.mse-set` archive, and stretches it to the art
  box. So before each preview or batch, `render/mse_service.art_files` crops every face's
  art to its box (at twice the box size), packs it in as `art-<uid>.png`, and sets the
  card's `image` value. The art and its crop travel with each MSE card as `MSECard.art`.
- **Built-in renderer**: `mse_layout.art_image` applies the same `crop_art`, so both
  renderers frame the art identically (checked against real MSE in
  `tests/render/test_mse_service.py`).
- **Overview pictures**: the cache key includes the art file and the crop, so changed art
  is redrawn.

## The set symbol

Use the **Set** button in the overview header for set-wide settings: name, code, default
frame, default artist, copyright line, and cards wanted per rarity (the targets in "18 / 20").
It also holds the symbol:
- drop or choose an image; it is copied to `assets/symbol.png`;
- a **black-and-white symbol** works as it is, including a ready-made common symbol (black
  with a white outline). `render/symbol.ink` reads the background from the image's border:
  - on transparent or white, the dark parts are the symbol;
  - on black, the light parts are;
  - white outlines and inner details become gaps, drawn in each rarity's outline color, so
    a common symbol's white lines turn black on uncommon and up.
- only the shape is used: it's filled with each rarity's colors and outlined, and the panel
  previews common, uncommon, rare and mythic, enlarged and at card size;
- silver, gold, mythic and the other metallic fills are diagonal gradients with a bright
  band across the middle, for the sheen of printed symbols. The colors are the stops in
  `render/symbol.VARIATIONS`;
- **SVG** symbols need the optional `cairosvg` package plus the Cairo library, which aren't
  installed. The panel says so if you add one; use a PNG.
- **Small-size advice** (`app/symbol_check.py`): at card size (about 20 px tall) the symbol
  is checked for strokes about a pixel wide ("thin lines may disappear") and for detail that
  merges ("fine detail is lost"). It's advice only.

Changing set-wide settings restarts the renderer's script environment, so every card picks
them up. Text fields save when you leave them, not on every keystroke.
