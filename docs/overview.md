# The set overview

The home page of an open set (`/set`): every card, grouped so you can see the shape of
the set and its gaps. Clicking a card opens it in the editor (`/set/card/<id>`). The
editor's back button returns here, with the grouping, filters and collapsed sections
unchanged.

## What it shows

- **Rows:** one section per group of the chosen factor, e.g. "White · 12" or
  "Common · 41 / 60". Empty groups are shown too, because a gap is information. Sections
  collapse.
- **Matrix:** rows by one factor and columns by another, e.g. archetype × rarity. Each cell
  shows its count, in orange when below target, and small tiles. Clicking a count shows
  just that cell's cards in Rows mode; remove the chip to go back to all of them.
- **Factors:** color (W, U, B, R, G, multicolor, colorless, land), rarity, archetype (a card
  can be in several), card type, mana value (0–6, 7+) and status. Like the planned set
  health rules, they look at the front face.
- **Targets:** "count / target" appears where you set a target. Rarity groups use the
  set's `rarity_slots`. Archetype groups use the sum of the archetype's targets, and
  archetype × rarity cells use the target for that rarity. Targets are hidden while a
  filter is active, because the counts are then partial.
- **Filters:** text (name, type, rules), status, rarity, color. **Sort:** collector number,
  name, mana value.
- **Tiles:** *Images* shows the real MSE render. *Compact* shows text: name, cost, type,
  rules, P/T, rarity, number, a status dot and a border in the card's color. Choose a
  size with the slider; the tile mode and size are remembered between sessions.
- **Archetypes** (header button): name, colors, description and targets per rarity, saved
  as you type. Deleting an archetype removes its tag from cards. You tag cards in the
  editor's Archetypes field.

## Card pictures

`app/thumbnails.py`: pictures are made in the background and cached on disk outside the
set folder, in `%LOCALAPPDATA%/setdesigner/thumbnails/` (or `$SETDESIGNER_CACHE_DIR`).
Until a card's picture exists, its tile shows the compact version.

- **Cache key** (`render_keys`): a hash of exactly what a preview set for the card would
  contain, i.e. its fields, its collector number, the set info and the keywords. A card is
  drawn again only when its picture would change. Changing set-wide things, such as the set
  name, redraws every card. Bump `CACHE_VERSION` after a renderer change.
- **Batches:** `render_many` loads one MSE set holding up to 20 missing cards. That is one
  load per batch, rather than per card, and it gives exactly the preview's pictures (tested
  against real MSE). The renderer lock is taken per batch, so an editor preview waits at
  most one batch.
- **Timing** (30-card set): the first fill takes about 10 s, including MSE starting.
  Reopening the set takes about 2 s, which is mostly loading the templates.

## Code

| Module | What it does |
| --- | --- |
| `app/overview.py` | factors, `group`, `matrix`, `Filters` / `apply`, `sort`, `target` (no UI) |
| `app/thumbnails.py` | `ThumbnailCache`, `ThumbnailWorker` |
| `app/session.py` | archetype editing, `thumbnails`, `using_renderer` |
| `render/mse_service.py` | `render_keys`, `MSERenderer.render_many` |
| `ui/overview_page.py` | the page |
| `ui/archetypes.py` | the archetype manager dialog |
| `ui/widgets.py` | the compact tile, color pips, rarity letters (shared with the editor) |

Tests: `tests/app/test_overview.py`, `tests/app/test_thumbnails.py`,
`tests/ui/test_overview_page.py`, and `test_batch_equals_single_renders` in
`tests/render/test_mse_service.py`.
