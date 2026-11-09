# Patterns

## List + detail (Mechanics, Cycles)
```
┌ Mechanics ─────────────────────────── Emberwild ──── ✕ ┐
│ [+ New mechanic]   │ Hunt                          ⋯   │
│ ▌Hunt          3   │ ┌ Definition ─────────────────┐   │
│  Settled       3   │ │ Name  Kind  Parameter  Roles │   │
│  Flurry        0   │ │ Reminder text …              │   │
│                    │ └──────────────────────────────┘   │
│                    │ ┌ Used on 3 cards ─────────────┐   │
│                    │ │ table                        │   │
└────────────────────┴────────────────────────────────────┘
```
- The list is `clamp(220px, 20%, 300px)`, with the new-item button at its top and an
  `empty_state` when empty.
- The detail fills the rest. Its sections are stacked `section` panels. Fields within a
  section use `responsive_grid`.
- Destructive actions such as "Delete mechanic" go in the detail's ⋯ menu, not as a loose
  red button.
- The first item is selected when the modal opens, unless the deep link names another.

## Saving
- Fields save on blur, and selects and toggles save on change, as today. There is no Save
  button in workspace modals.
- The top bar's status indicator (and the editor modal's header) shows "Saving…" and then
  "All changes saved".
- Dialog forms that change the set as a whole (Set settings, Tune checks) also save as you
  go and have a single **Done**, except where a change is expensive or touches many cards.

## Destructive actions
- Use `confirm()` with `kind="danger"`. Name the thing ("Delete Hunt?") and say what
  happens to linked data ("Its 3 cards keep their text").
- The danger button is on the right and the default focus is on **Cancel**.

## "Update N cards"
For edits that rewrite card text (renaming a mechanic, changing a phrase or a cycle
template):
- `confirm(details=changes)` shows up to 5 before/after pairs. The "before" is struck
  through in `--text-muted`, and the "after" is in `--text`.
- Buttons: **Update N cards** (primary), **Keep card text** (secondary), **Cancel** (ghost).
- The result shows as a toast: "Updated 5 card faces".

## Warnings and health
- Severity "warning" uses `--warning` and severity "info" uses `--info`. Health never uses
  red: red means something is broken, not unbalanced.
- The Health badge on the rail shows the number of warnings. It's hidden when there are
  none, and the Health page then shows a `--success` "Healthy" state.
- A warning that names cards expands to card chips. Clicking a chip opens the editor and
  returns to Health on close.

## Loading and rendering
- Card pictures render in the background. A tile without a picture yet shows its compact
  tile with a shimmer, not a spinner.
- A render error shows as a `--danger` badge on the tile and in the status indicator, never
  as a toast.
- Long operations (creating 10 cycle cards) disable their button and show "Creating…" on
  it.

## Selection and context
- The card that is open in the editor is outlined in accent on the workspace when the
  modal closes, so you can find your place.
- Filters show as removable chips under the toolbar, with "Clear all" at the end.

## Blocked renderer
When Magic Set Editor can't draw the cards (usually because Windows' Smart App Control
stopped trusting it), cards come from the stand-in renderer and look a little off. Say so
wherever cards show, the same way every time: use `ui/renderer_notice.notice`, never
your own wording.
- **Banner:** under the top bar. It leads with what the user sees ("Your cards are being
  drawn by a stand-in renderer and won't look quite right"), then why, then one primary
  action: **Renew Magic Set Editor**. "Not now" puts it away into a top-bar chip; it
  never disappears silently.
- **Compact:** a single line next to a preview (`compact=True`), with the same button.
- **Before an export** that would use stand-in pictures, the action says so ("Export with
  stand-in pictures") and asks first.
- The fix never asks the user to open or close a window when Windows allows otherwise
  (`app/mse_trust.py`). "Why is this needed?" explains it in plain words.

## Edit on the card
When the thing being edited has a picture of itself (a card), the picture is the editor:
- Every part of it is a hotspot placed from its own layout, never from guessed pixels
  (`CardRenderer.field_boxes`). Hover shows the outline and the part's name; the cursor is
  a text cursor.
- A click opens a small popover with just that part's fields, saving as you type while the
  picture redraws behind it. Pickers (symbols, mechanics) open on demand from the popover,
  never as permanent palettes.
- Tab walks the parts in reading order, so a whole card can be typed without the mouse.
- A side panel lists the same parts (reaching ones the picture doesn't show) and holds the
  fields that aren't printed (rarity, status, notes).
