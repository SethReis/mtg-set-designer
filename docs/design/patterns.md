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
