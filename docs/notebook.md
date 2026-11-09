# The design notebook

**Notebook** in the rail (`/set?open=notebook`) holds ideas before they become cards. It is
kept in the set folder's `notebook.json`.

## Ideas
- **Kinds:** card idea, mechanic idea, thought, or design problem ("Blue needs a common
  answer to fliers").
- **Fields:**
  - a title and notes;
  - tags, colors and archetypes;
  - for card ideas, a rough card: name, mana cost, type line, rules text, power and
    toughness. Any of these may stay empty.
- **Author:** each idea records who wrote it, from the app settings' `author`.

## The board
- **Lanes:** Inbox, Promising, Used and Parked. Drag an idea between lanes, or within a
  lane to reorder it.
- **Filters:** by kind, tag, color, or text in the title, notes, tags or sketch.
- **Editing:** click an idea to edit it on the right. Fields save when you leave them.
- **Badge:** the rail item counts the ideas in the Inbox.

## Catching ideas
- **Quick capture:** Ctrl+Shift+N or the lightbulb in the top bar, anywhere in a set. Save
  with Ctrl+Enter, or use **Save & another**.
- **From a card:** **Spin off an idea…** in the card editor's ⋯ menu starts an idea linked
  to that card.
- **From an empty slot:** **Add idea** in the slot's popover starts an idea with the slot's
  colors, type and archetype, linked to the slot.

## Making something of an idea
**Make it…** on an idea offers three choices:
- **New card:** a card with status Idea, filled in from the rough card. Its archetypes come
  from the idea, and its notes get the idea's notes. The editor opens on it.
- **Fill a skeleton slot…:** the empty slots, best fit first. The first choice is the
  idea's colors (or else the rough card's), then its type and archetype. The new card
  goes in the chosen slot and takes the slot's rarity.
- **New mechanic:** named after the idea, with its notes as the reminder text, for
  example "Flurry". The Mechanics view opens on it.

The idea moves to **Used** and links to what it became. A card made from an idea shows
"From idea: …" in the editor. Deleting that card, slot or mechanic removes the link.

## Code
| Module | What it does |
| --- | --- |
| `model/notebook.py` | `Idea`, `IdeaSketch`, `IdeaLink`, the lanes and kinds (saved by `save_notebook`) |
| `app/session.py` | `new_idea`, `update_idea`, `move_idea`, `delete_idea`, `promote_to_card`, `slots_for_idea`, `promote_to_mechanic`, `ideas_for` |
| `ui/notebook_page.py` | the board and the idea panel |
| `ui/notebook_capture.py` | quick capture |

Tests: `tests/app/test_notebook.py` and `tests/ui/test_notebook_page.py`.
