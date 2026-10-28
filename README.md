# MTG Set Designer

A private, local desktop app for designing custom Magic: The Gathering **sets**.
See `HANDOFF.md` for the design decisions and roadmap.

## Setup (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install --no-cache-dir -e .[dev]
```

Or just run `run.bat`, which does the above on first launch.

## Running the app

```
python -m setdesigner             # opens its own window (or double-click run.bat)
python -m setdesigner --browser   # in a browser tab at http://localhost:8765 instead
```

The start page creates a new set folder (default `sets/<code>/`) or opens an
existing one; recently opened sets are listed there. An open set lands on the
overview: every card, grouped in rows or a matrix (color, rarity, archetype, ...)
with counts against your targets (`docs/overview.md`). Clicking a card opens the
editor: the card list, the card form and a live preview drawn by Magic Set
Editor. Every change is saved automatically to `cards/<id>.json`, so there is
no Save button (`docs/editor.md`). Card art (pick, drop or paste, then crop) and
the set symbol (Set button in the overview) are covered in `docs/art.md`.
Mechanics (keywords with reminder text, word forms, renaming) are in `docs/mechanics.md`.

## MSE packages

Card templates come from Magic Set Editor packages in `resources/mse_packages/`
(all packages as siblings). To (re)populate them from an MSE install:

```
python tools/sync_packages.py "Full-Magic-Pack-main"
```

## Tests and tools

```
pytest
python tools/check_reader.py resources/mse_packages
python tools/survey_scripts.py
python tools/check_script_parse.py
python tools/mse_oracle.py        # re-record real-MSE results for tools/oracle_cases/*.txt
python tools/show_oracle.py builtins replace    # browse recorded results
```

The MSE script interpreter lives in `src/setdesigner/mse/script/`; see
`docs/interpreter_stages.md` for what is implemented so far. Cards are drawn by
`src/setdesigner/render/` (see `docs/renderer.md`):

```
python tools/render_cards.py out/                 # render the fixture set (or pass a project folder)
python tools/compare_renders.py out/              # ours | real MSE | difference
```
