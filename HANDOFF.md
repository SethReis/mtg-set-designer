# Project handoff: Set-first Magic: The Gathering custom set designer

Exported from a claude.ai design conversation (Oct 18, 2026) for continuation in Claude Code.
Read this first. Everything under "Settled decisions" was agreed with the user; everything under
"Not verified" should be checked before relying on it.

## 1. Goal and context

A **personal, local desktop app** for designing custom MTG **sets** (not just single cards), for the
user and friends to draft together. Never sold. The **code is public** on GitHub (GPL v2, the same
license as MSE); **MSE templates, fonts, MSE-rendered images and the user's own sets are not**.
They are git-ignored, and `tools/sync_packages.py` fills `resources/` from each user's own MSE install.

Why: existing card-maker tools feel dated and clunky (creating mechanics, uploading a set symbol,
checking formatting). No set-level tools exist. The app's primary object is the **set**; a card is a
part of it.

User is on **Windows**, comfortable with Python and HTML/CSS, **no Rust experience**, and wants to
**review and refine the code themselves**. Prefer plain, readable Python; keep UI thin; keep logic in
testable modules.

## 2. Settled decisions

**Stack**
- Python + **NiceGUI** (UI in Python, native window). Not Tauri/Rust.
- **pydantic** for the data model, **Pillow / Pycairo (+Pango)** for rendering, **reportlab or Pillow** for print PDFs.
- Storage: project folder of human-readable **JSON** (git-friendly), one file per card.
- **One renderer for both live preview and print export** (guarantees preview = print). Cards are rendered in Python, not HTML/CSS; HTML/CSS is only for the interface.

**Templates**
- Support **Magic Set Editor templates only**, copied from the user's own MSE install into `resources/` (git-ignored; no template library UI required; friends can drop in extra packs).
- Frames wanted: **modern M15** plus **old-border** frames (e.g. retro-style cards like Innistrad Remastered retro / Brothers' War retro artifacts).
- Each template gets a **compatibility report** (parse what we can, warn loudly on unsupported features, never fail silently).
- Frame is a **set-level default with per-card (and per-face) override**; bonus sheets are named card groups with their own frame.

**Scope**
- v1 / build now: set skeleton, card editor with live preview, mechanics, set symbol, set health dashboard, user-defined archetypes, print export.
- **Deferred**: art management, draft simulation.
- **Multi-faced cards from day one**: model faces as a list; **MDFC and transform supported in the model and renderer interface from the start** (the user may design a transform-themed set). Adventure/split/flip later (they put two text sets on one face).

**Multi-face data model choice**: **one record per card containing all faces**, with an `iter_faces()` helper for analysis that treats faces independently. (User did not object to this when asked twice; treat as settled but cheap to revisit before code exists.)

**Printing (simplified by the user)**
- Users print with **duplex off**, as paper proxies in sleeves with bulk-card backing.
- **Every face is cut out as its own card.** The print engine takes a **flat list of face images**. No pair units, no pair-packing, no back-to-back alignment, no mirrored columns, no card-back strategy.
- A card's faces are emitted consecutively (front, then back); pairs may split across rows.
- Sorting operates on cards, then expands to faces.
- Options: paper size, grid (e.g. 3x3), bleed + crop marks, DPI, sort order, single spacing value, optional face/collector-number labels.
- **Printer-friendly mode (planned, user request):** when printing, offer *Rendered* (the real MSE card images) or *Printer-friendly*, styled like playtest cards. It drops the art and the card frame, replaces mana and other symbols with plain characters (e.g. `{2}{W}` → `2W`, `{T}` → `T`), and uses thin borders, to save ink. The overview's text tiles (`ui/widgets.compact_tile`) are a starting point for this layout.
- Card size **varies by template** (e.g. the 4th Edition style is 337x469 @134.98dpi; most are 375x523 @150dpi). The renderer should output at physical size and the print engine scale to **63x88mm**.

**Feature ideas agreed**
- Set skeleton with fillable slots (`slots.json`, separate from the card model).
- Live set health: curve by color/rarity, creature/spell ratio, removal counts, complexity budget, keyword distribution, warnings (e.g. "blue has no common removal"). For MDFC/transform: configurable rules, front-face counting by default, per-face tagging for archetypes/mechanics.
- **Mechanics as first-class objects**: name, kind, parameter, reminder text with placeholders, design intent, reminder policy (e.g. commons only / first appearance per color). Typing "Cycling {2}" expands reminder text; editing the definition updates every card. Reminder text is **rendered, not stored**.
- **Archetypes are user-defined** (any color identity incl. mono/wedge/four-color/colorless/none, description, key mechanics, target counts per rarity), tagged onto cards; dashboard shows coverage for the user's own structure.
- Set symbol: import SVG/PNG, color per rarity (incl. mythic gradient), preview at real size, flag if muddy when small.
- Text-first editor with live preview, `{W}`-style autocomplete, auto name substitution, auto-shrinking text like real frames, linting for templating/overflow.
- Card status (idea -> draft -> playtested -> final), notes, version history.

## 3. Planned project layout

```
mtg-set-designer/
  pyproject.toml  README.md  run.bat  .gitignore
  src/setdesigner/
    __main__.py
    model/        # pydantic (cards, mechanics, archetypes, set)
    mse/          # reader.py (done), schema.py, script/ (to do)
    render/  analysis/  export/  ui/ (thin NiceGUI)
  resources/
    mse_packages/ # all MSE package folders as SIBLINGS (this is the reader's `root`)
    fonts/  CREDITS.md
  tools/          # collect_mse.py, check_reader.py
  tests/
  sets/           # user set projects
```

Project set folder format:
```
my_set/
  set.json  mechanics.json  archetypes.json  sheets.json  slots.json
  cards/ (one JSON per card)   assets/ (symbol, custom frames)
```

Windows setup: `py -m venv .venv`, `.venv\Scripts\activate`, `pip install -e .` (deps: nicegui, pydantic, pillow, later pycairo or similar).

## 4. Data model (latest sketch + pending amendments)

```python
from enum import Enum
from pydantic import BaseModel

class Rarity(str, Enum):
    COMMON="common"; UNCOMMON="uncommon"; RARE="rare"; MYTHIC="mythic"; SPECIAL="special"
class Status(str, Enum):
    IDEA="idea"; DRAFT="draft"; PLAYTESTED="playtested"; FINAL="final"
class Layout(str, Enum):
    NORMAL="normal"   # then: mdfc, transform; later adventure, split, flip

class Face(BaseModel):
    name: str
    mana_cost: str = ""            # "{2}{W}{W}"
    type_line: str = ""
    rules_text: str = ""           # keyword lines like "Cycling {2}" are matched to mechanics.json
    flavor_text: str = ""
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    art_path: str | None = None
    artist: str = ""

class Card(BaseModel):
    id: str                        # stable slug = filename
    layout: Layout = Layout.NORMAL
    faces: list[Face]
    rarity: Rarity
    collector_number: str = ""
    frame: str | None = None       # card-level default override of set default
    sheet: str | None = None       # bonus sheet name; None = main set
    archetypes: list[str] = []
    mechanics: list[str] = []      # derived/cached
    status: Status = Status.IDEA
    notes: str = ""

class Mechanic(BaseModel):
    id: str; name: str; kind: str   # keyword | ability_word | keyword_action
    parameter: str | None = None
    reminder_text: str
    design_intent: str = ""
    reminder_policy: str = "commons_only"

class Archetype(BaseModel):
    id: str; name: str
    colors: str = ""
    description: str = ""
    key_mechanics: list[str] = []
    targets: dict[Rarity, int] = {}

class SetInfo(BaseModel):
    name: str; code: str
    default_frame: str = "m15"
    symbol_path: str | None = None
    rarity_slots: dict[Rarity, int] = {}
```

**Amendments agreed but NOT yet written into code:**
- Move `frame` to `Face` (card-level value is the default); transform fronts/backs often use different frames.
- Add to `Face`: `color_indicator: str` (transform backs have no mana cost) and a face role (`front`/`back`); optional back-face fields (planeswalker/battle backs, day/night).
- Card color identity = union across faces.
- Add `layouts.py` registry: each layout declares face count, required fields, and which style to use per (layout, face role).
- Renderer interface: **a card produces a list of images**.
- Name substitution and cross-face references must be face-aware.
- `iter_faces()` helper; per-face analysis flags.
- Editor: face switcher, "copy from front", validation panel (e.g. transform back with a mana cost, wrong face count).
- MSE stores each face as its **own linked card** (`card.transformation`, linked-DFC flags); map one of our records to two MSE-style cards at render time.
- Field mapping needed between our `Face` and MSE game fields (e.g. MSE splits type into super type/sub type; seen field names include `name`, `rarity`, `super_type`, `card_symbol`, `transformation`).

## 5. MSE findings (verified against the user's files)

Source pack: `github.com/MagicSetEditorPacks/Basic-M15-Magic-Pack` (README is copied from a "Full Magic Pack" and misleading; the extracted repo is a full MSE install with a large `data/` folder; ignore the `.exe` files). Only the `data/` packages are needed.

An MSE package is a folder (or zip renamed) of indentation-based `key: value` text files plus images/fonts. Relevant package types: `.mse-game` (field schema + big script library), `.mse-style` (layout/positions/frames, scripted), `.mse-include` (shared scripts/assets), `.mse-symbol-font` (mana symbols).

- The plain `magic-m15.mse-style` is **deprecated**. The current "M15 Main" is **`magic-m15-altered.mse-style`** (236 files, 3,017-line style, 375x523 @150dpi).
- Retro candidates present: `magic-old` ("Old Main", "Before 8th edition", ~416 lines), `magic-new` ("8th Main", ~411 lines), `magic-veryold` ("4th Ed.", 337x469 @134.98dpi, ~366 lines), `magic-old-abu` ("before revised edition", ~435 lines).
- Dependencies for those 5 styles and `magic.mse-game` are all present once the `.mse-include` packages are included (one harmless upstream typo reference `magic-modues.mse-include`).
- `magic-m15-mainframe-dfc` is deprecated and draws both faces on one 752x523 canvas; ignore it. DFC support in M15 Main comes from `/magic-modules.mse-include/dfc/*`.
- **Almost every style property is a script**, e.g. name box `top: { 30 + name_font_vertical() }`, `left:` as a multi-line `script:` block with `if/else`. These depend on a large library: `magic.mse-game/script` (~7,467 lines), `card_fields` (~3,496 lines), plus `magic-modules`, `magic-blends`, `magic-default-image`, `magic-mainframe-extras`, `magic-pride`.
- Repeated top-level blocks must be **merged** (M15 Main has 9 `card style:` blocks after include expansion, 54 entries total).
- Retro styles are small, share the same game scripts, so once the interpreter handles M15 they should be a modest addition.
- Files use tabs, UTF-8 with BOM, `#` comments.

### Rendering approach (options discussed)
1. **Write a real MSE script interpreter** and run the actual style files (most faithful; largest work; a few thousand lines of Python). *Recommended; the user proceeded without objecting.*
2. Define our own simpler template format reusing only MSE assets (much less work, but drops "supports MSE templating").
3. **Use MSE itself as a test reference**: the repo ships `magicseteditor.com`, which (as recalled, unverified) can generate card images from a `.mse-set`; use it for golden images to compare our renderer against, or as a stopgap renderer.

Build order agreed: data model + load/save (no UI) -> MSE parser + M15 renderer checked against reference renders -> NiceGUI card editor with live preview -> mechanics + set symbol workflows -> skeleton, health dashboard, archetypes -> print PDF -> retro frames.

## 6. Current code state

Written and tested in the claude.ai session (copy these into the repo; they are not in this document):
- `mse_parser/mse/reader.py`: stages 1-2. `expand_includes()` splices `include file:` / `include localized file:` / `key: include file: x` using `/package/path` or package-relative paths; `parse_block()` yields `Node(key, value, block, line)` with lazy `.children()`, `.text()`, `.get(key)`; scripts are kept as raw strings; unresolved includes are recorded in `Stats`, malformed lines raise `MSEReadError` with a line number. `read_file(path, root, lang="en")` is the entry point, where `root` is the folder containing all packages as siblings.
- `mse_parser/check_reader.py`: reads the main file of every package under a root and prints a summary.
- Result: **89 package files read, 0 failures, ~0.1s**. Verified on M15 Main's name box (children `left, top, right, height, alignment, padding bottom, z index, font`; scripts intact).

Not yet written: schema layer (typed Style/TextBox/ImageLayer/SymbolFont, merging repeated blocks), script tokenizer/parser/evaluator, renderer, anything in model/, analysis/, export/, ui/.

## 7. Not verified / caveats

- I never saw the actual image assets or the `fonts` folders; the user's zip had images stripped. Check what fonts the pack ships and where MSE expects them.
- Which retro style corresponds to which real-world frame (1993 / 1997 / 2003) is inferred from names and descriptions only. "Old Main" = "Before 8th edition", "8th Main" = 8th Edition frame. Confirm against rendered output and the Innistrad Remastered / Brothers' War retro references.
- The `magicseteditor.com` CLI image-generation flag is from memory; check `--help`.
- Multi-face print "labels" and exact M15 field-to-model mapping were discussed but not designed in detail.
- Licensing: our code is GPL v2. MSE is GPL v2 and runs as a separate program. Community frames and fonts have varied licenses (several fonts are commercial), so they are never committed. History was rewritten on publishing to remove them from old commits.

## 8. Immediate next steps

1. Scaffold the repo (`pyproject.toml`, `run.bat`, `.gitignore`, folders), move `reader.py` into `src/setdesigner/mse/`, add a first test under `tests/`. Copy the **full** package folders (with images and fonts) from the pack's `data/` into `resources/mse_packages/`.
2. **Survey which script functions/constructs M15 Main and the retro styles actually use** (from `style`, `magic.mse-game/script`, `card_fields`, and the includes) to prioritize the interpreter.
3. Build the MSE script tokenizer/parser/evaluator in stages, tested on real values (`30 + name_font_vertical()`, `if/then/else`, string/list ops, `include`).
4. Write the schema layer, then the M15 renderer; compare against reference renders from MSE.
5. Write the full pydantic model with the amendments in section 4 plus `layouts.py`.

## 9. Appendix: updated collector script

Run to bundle just the text files needed for analysis (images/fonts excluded). Usage:
`py collect_mse.py "C:\path\to\repo-root-containing-data"`

```python
import sys, zipfile
from pathlib import Path

root = Path(sys.argv[1]).expanduser()
data = root / "data"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".mse-symbol",
             ".ttf", ".otf", ".xcf", ".psd", ".dic", ".onetoc2"}

KEEP_STYLES = {"magic-m15-altered", "magic-old", "magic-new", "magic-veryold", "magic-old-abu"}

def wanted(pkg: Path) -> bool:
    n = pkg.name.lower()
    if n.endswith((".mse-game", ".mse-include", ".mse-symbol-font")):
        return True
    return n.endswith(".mse-style") and n[:-len(".mse-style")] in KEEP_STYLES

lines = ["TOP-LEVEL NAMES IN data/", *sorted(p.name for p in data.iterdir()), ""]
packages = [p for p in sorted(data.iterdir()) if p.is_dir() and wanted(p)]

with zipfile.ZipFile("mse_sample.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for pkg in packages:
        files = [f for f in pkg.rglob("*") if f.is_file()]
        lines.append(f"{pkg.name}: {len(files)} files")
        for f in files:
            rel = f.relative_to(pkg)
            lines.append(f"    {rel.as_posix()}")
            if f.suffix.lower() not in IMAGE_EXT:
                z.write(f, f"{pkg.name}/{rel.as_posix()}")
    z.writestr("listing.txt", "\n".join(lines))

print(f"Wrote mse_sample.zip with {len(packages)} packages")
```
