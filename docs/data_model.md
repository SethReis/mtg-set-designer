# Data model and MSE mapping

## Our model (`src/setdesigner/model/`)

| Class | What it is |
|---|---|
| `SetProject` | info + mechanics + archetypes + cards; `iter_faces()` yields every face |
| `SetInfo` | name, code, default frame, symbol, artist, copyright, language, rarity slots |
| `Card` | one record per card with **all its faces**; layout, rarity, collector number, card-level frame, sheet, archetypes, status, notes; `color_identity` = union over faces |
| `Face` | name, role (front/back), mana cost (`{2}{W}{W}`), color indicator, type line, rules/flavor text, P/T, loyalty, art, artist, per-face frame override |
| `Mechanic` | name, kind, parameter, reminder text with `{param}` placeholders, design intent, reminder policy |
| `Archetype` | name, colors (any, including none), description, key mechanics, target counts per rarity |

`layouts.py` lists each layout's face roles and rules; `validate_card()` returns readable problems
(wrong face count, a transform back with a mana cost, P without T, ...).

### On disk (`model/project.py`)

```
my_set/
  set.json  mechanics.json  archetypes.json
  cards/<card id>.json        one card per file (all faces inside)
  assets/                     symbol, frames, art (referenced by path)
```
JSON is indented, UTF-8, in model field order; unchanged files are not rewritten. Cards load in
id order (a card's place in the set comes from its collector number).

## How MSE sees it (`src/setdesigner/mse/`)

MSE's magic game has one card **per face**. `mapping.card_to_mse()` turns each face into an MSE card
with raw field values; a double-faced card's two MSE cards are linked like MSE 2.6 links them:

| Ours | MSE card field |
|---|---|
| `face.name` | name |
| `face.mana_cost` `{2}{W}{W}` / `{W/U}` | casting cost `2WW` / `W/U` |
| `face.type_line` `A B — C D` | super type `A B`, sub type `C D` |
| `face.rules_text`, `flavor_text` | rule text, flavor text |
| `face.power` / `toughness` / `loyalty` | power / toughness / loyalty |
| `face.color_indicator` `U`, `red, green` | indicator `blue`, `red, green` |
| `face.art_path`, `artist` | image, illustrator (empty → MSE's default, the set artist) |
| `card.rarity` (`mythic`) | rarity (`mythic rare`) |
| `card.notes` | notes |
| card id (+ `/1`, `/2` per face) | uid |
| DFC front / back | `linked card 1` = the other face, `linked relation 1` = "Back Face" / "Front Face" |
| face/card/set frame `m15`, `old`, `8th`, `4th`, `abu` | stylesheet (`frames.py`) |
| `SetInfo` name, code, artist, copyright, language | set fields title, set code, artist, copyright, card language |

In rules and flavor text, mana symbols `{2}{W}` become MSE's `<sym>2W</sym>` tags.

### Mechanics (`mse/mechanics.py`)

Each `Mechanic` is one of the set's own MSE keywords (also written into exported `.mse-set`
files): `match` = name, plus ` <atom-param>TYPE</atom-param>` when `parameter` names one of the
game's keyword parameter types (`cost`, `number`, `name`, …); the reminder text's `{cost}` /
`{param}` becomes `{param1}`; mode = custom (keyword), pseudo (ability word) or action
(keyword action). Reminder policies are applied per card by wrapping each mention in
`<kw-1>` (show) or `<kw-0>` (hide), which MSE's own keyword expansion honors:

| Policy | Reminder shown on |
|---|---|
| always | every card |
| never | no card |
| commons_only | commons |
| first_per_color | the first card (collector-number order) of each of its colors that uses it |

Everything else (card color, cmc, type line with tags, P/T box, card number, color identity, ...)
is **computed by the game's and style's own field scripts** (`objects.py`, `environment.py`):
a field's value is the raw value, else its `default:` script, else its initial value, then its
`script:` applied. `ScriptEnvironment(project).card_values(card, face)` returns all of them.

These values are checked against real MSE: `tools/mse_oracle.py` exports
`tests/fixtures/oracle_project.py` with `export_set.write_mse_set()`, loads it in
`magicseteditor.com --cli` and records the results (`tools/oracle_cases/cards.txt`).

Not mapped yet: per-card styling options, extra-card field overrides, watermarks, card symbols,
custom card numbers.
