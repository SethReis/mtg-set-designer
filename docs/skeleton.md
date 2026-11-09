# The set skeleton

**Skeleton** in the rail (`/set?open=skeleton`) plans which cards the set needs: a grid of
slots by column and rarity, each describing the card it wants and filled by one card. It
is kept apart from the cards, in the set folder's `slots.json`.

## Generating
With no skeleton yet, **Generate skeleton…** asks for:
- **A preset:**
  - *Play Booster set* (81 C, 100 U, 60 R, 20 M);
  - *Classic draft set* (101 C, 80 U, 53 R, 15 M);
  - *Cube* (no rarities: about 45 per color, plus multicolor, colorless and land).
- **Columns:** W U B R G, then one per color set of your archetypes (two or more colors,
  pairs in their usual order: WU, UB, BR, RG, GW, WB, UR, BG, RW, GU), then C (colorless)
  and L (land). Add a column for a color set no archetype covers (e.g. a pair in a
  3-color set) with **Add column**.
- **Counts:** a table of slots per column and rarity, filled in from the preset:
  - mono colors share each rarity evenly;
  - multicolor columns get signpost-like counts (two uncommons, a rare, a mythic when
    there's room, a common in big sets);
  - colorless and land get a small share.
  Change any number before generating.

Slots are labelled by column, rarity and number (`W-C01`, `WU-U02`; `W-07` in a cube).
Multicolor columns are tagged with their archetype. Existing cards are placed where they
fit; the rest are listed as **Outside the skeleton**.

**Edit counts…** reopens the table for an existing skeleton and adjusts it in place:
- new slots go at the end of their cell;
- removing takes empty slots first, plain ones before described ones;
- removing filled slots asks first (their cards stay in the set);
- descriptions and cards are kept.

## The board and the table
- **Board:** columns across, rarities down (or archetypes, with **By archetype**), each cell
  a stack of slots with its fill count (`12 / 16`).
  - **Filled slots** show their card. **Empty slots** are dashed and show what they ask
    for: "Creature · 2 MV · Removal · note".
  - **+** adds a slot to a cell.
  - Drag a card onto a slot to fill it: from another slot (a move, or a swap if the target
    is filled), or from the **Outside the skeleton** strip.
- **Table:** one row per slot, every field editable in place, filtered by empty only,
  column or rarity.
- **A slot's popover** (click it, here or in the overview):
  - **What it asks for:** type, mana value, role (as in Health), archetype and a note;
  - **Create card from this slot:** a new card with the slot's rarity, type, archetype and
    note, opened in the editor;
  - **Assign a card:** the cards outside the skeleton that fit it best, and a search over
    the rest;
  - for a filled slot: **Open** or **Unassign** its card;
  - **Delete slot**.

**Which column a card belongs in:**
- lands go in L, colorless cards in C;
- one color goes in its column;
- more colors go in their color set's column, or else the closest one (most colors
  shared).
- The front face decides, as in Health.

**How suggestions rank:** a card fits a slot when its column and rarity match. The slot's
type, mana value, role and archetype then rank the candidates.

## Elsewhere
- **Overview:** empty slots show as dashed tiles in their color, rarity or archetype group
  and in matrix cells (the **Slots** switch in the toolbar hides them). Clicking one opens
  its popover. Color and rarity groups count against the skeleton's slots (`Green · 9 / 16`).
- **Targets:** while there's a skeleton, its slots per rarity are the set's rarity targets
  (overview, Health). Set settings shows them read-only.
- **Health** has three checks: empty slots (by column and rarity), cards outside the
  skeleton, and each archetype's tagged slots filled (below 75% by default).
- **Cycles:** generating a cycle's cards puts each into the empty slot of its column and
  rarity that fits it best, marked with the cycle.
- **Collector numbers** are separate: slots don't number cards.

## Code
| Module | What it does |
| --- | --- |
| `model/skeleton.py` | `Slot`, `Skeleton` (saved as `slots.json` by `save_skeleton`) |
| `app/skeleton.py` | presets, columns, default counts, `generate`, `adjust`, `column_of`, `fits`, `place_cards`, `suggest`, `targets` |
| `app/session.py` | `create_skeleton`, `adjust_skeleton`, slot editing, `assign`, `new_card_from_slot` |
| `ui/skeleton_page.py` | the Skeleton view, the counts dialog |
| `ui/slot_popover.py` | a slot's popover (also used by the overview) |

Tests: `tests/app/test_skeleton.py`, `tests/app/test_session.py`,
`tests/app/test_health_checks.py`, `tests/ui/test_skeleton_page.py` and
`tests/ui/test_overview_page.py`.
