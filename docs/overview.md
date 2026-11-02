# The set overview

The home of an open set (`/set`): every card, grouped so you can see the shape of the set
and its gaps. It sits in the app shell (the left rail and the top bar, see
`design/layout.md`), and everything else opens over it as a modal: clicking a card opens
the editor (`/set?card=<id>`), and closing it returns here with the grouping, filters and
collapsed sections unchanged.

The toolbar holds the view (Rows / Matrix), Group and Sort, the layout (Grid / Stacks),
what tiles show (Images / Text), the **Filters** popover and the card size. Active filters
show as removable chips under it. The card search is in the top bar (Ctrl+K).

## What it shows

- **Rows:** one section per group of the chosen factor, e.g. "White · 12" or
  "Common · 41 / 60". Empty groups are shown too, because a gap is information. Sections
  collapse.
- **Matrix:** rows by one factor and columns by another, e.g. archetype × rarity. Each cell
  shows its count, in the warning color when below target, and small tiles. Clicking a
  count shows just that cell's cards in Rows mode; remove the chip to go back to all of
  them.
- **Factors:** color (W, U, B, R, G, multicolor, colorless, land), rarity, archetype (a card
  can be in several), card type, mana value (0–6, 7+) and status. Like the planned set
  health rules, they look at the front face.
- **Targets:** "count / target" appears where you set a target. Rarity groups use the
  set's `rarity_slots`. Archetype groups use the sum of the archetype's targets, and
  archetype × rarity cells use the target for that rarity. Targets are hidden while a
  filter is active, because the counts are then partial.
- **Filters:** text (name, type, rules), status, rarity, color. **Sort:** collector number,
  name, mana value.
- **Layout:** *Grid* fills each row with tiles (each at least the card size, all growing
  alike, so rows reach the window's edge). *Stacks* overlaps them so only each name
  bar shows; hovering a card slides the cards below it down to reveal it fully. In Rows
  mode each group is a column (long groups split into several stacks), and in the matrix
  each cell is one stack.
- **Show:** *Images* shows the real MSE render. *Text* shows the name, cost, type, rules,
  P/T, rarity, number, a status dot and a border in the card's color. The text tile is
  also the starting point for the planned printer-friendly print mode (HANDOFF.md,
  "Printing"). Choose a size with the slider; the layout, what is shown and the size are
  all remembered between sessions.
- **Archetypes** (in the rail): name, colors, description and targets per rarity, saved
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
| `ui/overview_page.py` | the workspace: toolbar, tiles, matrix; hosts the modals and the `/set?…` deep links |
| `ui/shell.py` | the rail and the top bar |
| `ui/archetypes.py` | the archetype manager (an `lg` modal) |
| `ui/widgets.py` | the text tile, rarity letters, `served_url`, `responsive_grid` |
| `ui/components.py` | the design's building blocks (buttons, modals, tables, pips, …; `design/components.md`) |

Tests: `tests/app/test_overview.py`, `tests/app/test_thumbnails.py`,
`tests/ui/test_overview_page.py`, `tests/ui/test_shell.py` (rail, deep links, filters), and
`test_batch_equals_single_renders` in `tests/render/test_mse_service.py`.
