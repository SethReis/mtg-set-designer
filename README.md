# MTG Set Designer

A private, local desktop app for designing custom Magic: The Gathering **sets**.
See `HANDOFF.md` for the design decisions and roadmap.

## Setup (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

Or just run `run.bat`, which does the above on first launch.

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
