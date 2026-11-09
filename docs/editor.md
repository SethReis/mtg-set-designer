# The card editor

Edit a set's cards with a live preview. It is a workspace modal over the set overview
(`overview.md`): click a card, press **New card** (Ctrl+N), or follow a card link from
Mechanics, Cycles or Health. Close it with × or Esc; a card opened from one of those
returns to it. The URL (`/set?card=<id>`) follows the card shown.
Double-faced card editing and the problems panel come in a later stage.

## Where the code is

All behaviour is plain Python under `src/setdesigner/app/` and is tested without a UI.
The NiceGUI modules in `src/setdesigner/ui/` only arrange widgets and call into it.

| Module | What it does |
| --- | --- |
| `app/session.py` | `SetSession`: one open set. Create/open, list/search, new/duplicate/delete, `update(card, field, value)`, autosave, preview renders |
| `app/text_input.py` | Typing helpers as pure functions: `suggestions(text, caret, mechanics)`, `apply`, `insert` |
| `app/settings.py` | Recent sets, window size, theme, overview layout, in `%APPDATA%/setdesigner/settings.json` |
| `model/project.py` | `save_card`, `delete_card`, `save_info`, `new_card_id` (card ids never change on rename) |
| `ui/app.py` | Startup (`main`), native window or `--browser` |
| `ui/start_page.py` | `/`: recent sets, new set, open a folder |
| `ui/editor_page.py` | `editor_panel`: card list, form, preview, in a modal over `/set` |

## Behaviour

- **Autosave.** Each edit marks the card as unsaved. A 0.1 s timer on the page writes cards
  that have gone 0.5 s without an edit (`SetSession.flush_due`). Switching cards, leaving
  the editor and closing the app write everything (`flush`). The modal's header shows
  "Saving…" or "All changes saved".
- **Preview.** The preview is rendered 0.3 s after the last edit, off the UI thread. A
  generation counter drops renders that finished after a newer one started. It uses real
  MSE (see `renderer.md`). A "built-in renderer" note appears only if MSE wasn't available.
- **Typing helpers.**
  - After an unclosed `{` in the mana cost or rules text, symbol suggestions appear (`{W}`,
    `{2}`, `{T}`, `{W/U}`, …). After two letters that start one of the set's mechanics,
    that mechanic is suggested.
  - Click a suggestion, or press Tab for the first one. Tab moves focus as usual when no
    suggestions are shown.
  - The symbol palettes and the CARDNAME button insert at the caret.
  - The caret position reaches Python with every keyup and click. QInput doesn't pass
    native `input` events on. Tab's own keyup is skipped, because it would report the
    caret from before the accepted suggestion.
- **Type line.** Edited as two fields, Types and Subtypes (`session.update(card, "types", ...)`).
  The card still stores one `type_line`. The "—" is added only when both are filled, so
  nobody has to type it.
- **Planeswalkers.** Write one ability per line, with its cost: `+1: Draw a card.`,
  `−2: ...`. A planeswalker type line switches the card to that frame's planeswalker
  version (see `mse/frames.py`), and the costs go to MSE's loyalty cost fields.
- **Two-faced cards.** The row at the top of the form sets the layout: *Single*,
  *Transform* or *Modal DFC* (`session.set_layout`). A two-faced card gets a
  **Front · Back** switch: the form, the art and the preview show that face (the flip
  button on the preview and Ctrl+. switch too), and face fields save to it
  (`session.update(card, field, value, face=1)`). The **Card** section (rarity, number,
  frame, status, archetypes, print copies) is shared by both faces. Backs get a **color
  indicator** (W U B R G toggles); transform backs have no mana cost, so that field is
  hidden. Transform cards pick a **transform symbol** on the front (Triangle, Sun / Moon,
  Moon / Eldrazi, Fan, Spark, Comedy / Tragedy) and MSE gives the back its pair. Making a
  card single again, or a transform card from an MDFC with a back cost, asks first. The
  list and the title show "Front // Back". Problems from `validate_card` (a back with no
  name, ...) show above the form.
- **Spelling.** In the desktop window, right-click a text field for spelling suggestions.
  pywebview turns WebView2's right-click menu off, so `ui/native_window.py` turns it back on
  for text fields only.
- **Layout.** Three columns filling the modal, each scrolling on its own: the card list
  (hide it with the list button; hidden below 1100 px wide), the form in sections
  (Identity, Text, Art, Stats, Card, Notes), and the preview at the card's ratio.
- **Keyboard.** Ctrl+N new card, Ctrl+D duplicate, Ctrl+F search the list, Ctrl+[ / Ctrl+]
  previous / next card in the overview's order, Ctrl+. the other face, Esc closes.

## Testing

- `tests/app/`: the session and typing helpers.
- `tests/ui/test_editor_page.py`: NiceGUI's simulated `user` (no browser). Creates a set,
  adds and edits a card, reopens a set from the recent list.
- `tests/ui/test_shell.py`: previous / next, and returning to Mechanics after a card.
- For a manual check, run `python -m setdesigner --browser`.
