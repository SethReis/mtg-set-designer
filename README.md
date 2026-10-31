# MTG Set Designer

A local desktop app for designing custom Magic: The Gathering **sets**: plan the set,
write cards with a live preview drawn by Magic Set Editor, and see the whole set grouped
by color, rarity, archetype or mechanic. See `HANDOFF.md` for the design decisions and
roadmap.

> Unofficial fan content. Not approved or endorsed by Wizards of the Coast. Magic: The
> Gathering, its card frames and mana symbols are property of Wizards of the Coast. This
> repository contains **no** card templates, frame images or fonts; you supply them from
> your own Magic Set Editor install (see Setup).

## Setup (Windows)

1. **Python 3.11+**, then in the project folder:

   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install --no-cache-dir -e .[dev]
   ```

   Or just run `run.bat`, which does this on first launch.

2. **Magic Set Editor with the Full Magic Pack.** Download the
   [Full Magic Pack](https://github.com/MagicSetEditorPacks/Full-Magic-Pack), a ready-to-run
   MSE install with the community templates. Unzip it into the project folder as
   `Full-Magic-Pack-main/`, which is git-ignored. Elsewhere works too: set
   `SETDESIGNER_MSE` to its `magicseteditor.com`. The app uses MSE to draw cards, and falls
   back to its own renderer without it.

3. **Copy the templates and fonts the app reads** into `resources/` (git-ignored):

   ```
   python tools/sync_packages.py "Full-Magic-Pack-main"
   ```

## Running the app

```
python -m setdesigner             # opens its own window (or double-click run.bat)
python -m setdesigner --browser   # in a browser tab at http://localhost:8765 instead
```

The start page creates a new set folder (default `sets/<code>/`, git-ignored) or opens
an existing one; recently opened sets are listed there.
- **Overview:** an open set lands here. Every card is grouped in rows or a matrix
  (color, rarity, archetype, ...), with counts against your targets (`docs/overview.md`).
- **Editor:** clicking a card opens it, with the card list, the card form and a live
  preview drawn by Magic Set Editor. Every change is saved automatically to
  `cards/<id>.json`, so there is no Save button (`docs/editor.md`).
- **Art and set symbol:** card art (pick, drop or paste, then crop) and the set symbol (Set
  button in the overview) are in `docs/art.md`.
- **Mechanics:** keywords with reminder text, word forms and renaming are in
  `docs/mechanics.md`.
- **Cycles:** families of cards across colors (dual lands, Dragonstorm-style cycles),
  generated from one template and kept in step, are in `docs/cycles.md`.
- **Set health:** warnings ("Blue has no common removal"), the mana curve, roles per color,
  mechanic spread and complexity, on their own page and as a chip in the overview header,
  are in `docs/health.md`.

## Tests and tools

```
pytest
```

Without `resources/` and MSE, the tests that need templates, fonts or MSE skip themselves
and the rest run. With them, everything runs. The reference card images that compare our
renderer with MSE aren't in the repository; record them from your own MSE install:

```
python tools/mse_oracle.py        # re-record real-MSE results (tools/oracle_cases/*.txt)
python tools/show_oracle.py builtins replace    # browse recorded results
python tools/check_reader.py resources/mse_packages
python tools/survey_scripts.py
python tools/check_script_parse.py
```

The MSE script interpreter lives in `src/setdesigner/mse/script/`; see
`docs/interpreter_stages.md` for what is implemented so far. Cards are drawn by
`src/setdesigner/render/` (see `docs/renderer.md`):

```
python tools/render_cards.py out/                 # render the fixture set (or pass a project folder)
python tools/compare_renders.py out/              # ours | real MSE | difference
```

## Credits and license

- [Magic Set Editor](https://github.com/twanvl/MagicSetEditor2) (GPL v2) draws the cards.
  Its template scripts are run by our own interpreter; no MSE code is included.
- The card templates come from the
  [MagicSetEditorPacks](https://github.com/MagicSetEditorPacks) community. Some template
  images are from [CardConjurer](https://cardconjurer.com/).
- The code in this repository is © Seth Reis, under the GNU General Public License
  version 2 (`LICENSE`), the same license as Magic Set Editor.
