# The card editor

Stage one of the app: open or create a set and edit its cards with a live preview.
Double-faced card editing and the problems panel come in a later stage.

## Where the code is

All behaviour is plain Python under `src/setdesigner/app/` and is tested without a UI.
The NiceGUI modules in `src/setdesigner/ui/` only arrange widgets and call into it.

| Module | What it does |
| --- | --- |
| `app/session.py` | `SetSession`: one open set. Create/open, list/search, new/duplicate/delete, `update(card, field, value)`, autosave, preview renders |
| `app/text_input.py` | Typing helpers as pure functions: `suggestions(text, caret, mechanics)`, `apply`, `insert` |
| `app/settings.py` | Recent sets and window size, in `%APPDATA%/setdesigner/settings.json` |
| `model/project.py` | `save_card`, `delete_card`, `save_info`, `new_card_id` (card ids never change on rename) |
| `ui/app.py` | Startup (`main`), native window or `--browser` |
| `ui/start_page.py` | `/`: new set, open folder, recent sets |
| `ui/editor_page.py` | `/set`: card list, form, preview |

## Behaviour

- **Autosave.** Each edit marks the card as unsaved. A 0.1 s timer on the page writes cards
  that have gone 0.5 s without an edit (`SetSession.flush_due`). Switching cards, leaving
  the page and closing the app write everything (`flush`). The header shows "Saving…" or
  "All changes saved".
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
- **Keyboard.** Ctrl+N new card, Ctrl+D duplicate, Ctrl+F search.

## Testing

- `tests/app/`: the session and typing helpers.
- `tests/ui/test_editor.py`: NiceGUI's simulated `user` (no browser). Creates a set,
  adds and edits a card, reopens a set from the recent list.
- For a manual check, run `python -m setdesigner --browser`.
