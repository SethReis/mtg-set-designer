# Components

Each component is a function in `ui/components.py`, styled only through the tokens. The
names given here are the Python names.

## Buttons: `button(label, kind=…, icon=…, on_click=…)`
| Kind | Look | Use |
| --- | --- | --- |
| `primary` | Accent fill, `--on-accent` text | The one main action of a view |
| `secondary` | `--surface-2` fill, 1px `--border` | Other actions |
| `ghost` | No fill, `--text-muted`; `--surface-2` on hover | Toolbar and row actions, "Cancel" |
| `danger` | Ghost with `--danger` text; filled `--danger` in a confirm | Delete |
| `icon` | 32px square ghost, tooltip required | Close, overflow ⋯, row actions |

Height is 32 (28 when `dense`) with radius `--radius-md` and 13px/500 text in sentence
case, never uppercase (Quasar's `no-caps` everywhere). Icon and label are 6px apart.

## Fields
- **Text field / textarea / select / number:** an outlined field on `--surface-2` with a
  1px `--border` and an accent ring on focus.
  - The label sits above the field, never floating inside it.
  - Dense 32px is the default.
  - Errors use `--danger` for the outline and the helper text.
- **Multi-select** shows chips inside the field.
- **Segmented control** (`segmented(options)`) replaces Quasar toggles. It's a
  `--surface-2` track, and the active segment is `--surface-1` with a shadow and
  `--text`.
- **Slider:** a thin track, with the accent thumb and fill.

## Chips and badges
- **Chip:** 22px, `--surface-3`, `--radius-sm`, 12px text. It can be removable (×) or
  clickable.
  - Used for filters, roles, card references ("017 Cinder Imp") and word forms.
- **Badge:** an 18px pill using the `-soft` background and the full-color text of a
  semantic token.
  - Examples: "3 warnings", "Edited", "Missing".
- **Count:** plain `--text-faint` tabular numbers next to a label ("Hunt 3").

## Mana and color
- `mana_cost("{2}{W}{U}")` renders Mana-font symbols at 1em.
- `pips("WU")` renders 8px color dots in the `--mana-*` colors. They're used in lists and
  tables where a symbol would be too loud.
- `color_label("W")` gives a dot and "White".
- The rarity letter uses its `--rarity-*` color in 11px semibold.

## Lists and tables
- **List row** (`list_row`): 36px, with a 12px horizontal padding.
  - Hover `--surface-2`.
  - Selected `--surface-3` with a 2px accent bar on the left.
  - Leading: pips or a symbol. Trailing: a count or a menu.
- **Data table** (`data_table(columns, rows)`): a CSS grid with `minmax()` tracks.
  - The header is a sticky `--surface-2` row in 11px uppercase `--text-muted` (the only
    uppercase text in the app).
  - Rows are 32px with hairline borders.
  - Numbers are right-aligned and tabular.
  - A cell can be a button, which opens what it counts.

## Panels
- **Section** (`section(title, actions=…)`): `--surface-1`, a 1px `--border`,
  `--radius-lg`, 16px padding. The title is `--text-md` 600, with the actions on the right
  of the title row.
- **Group header** in the workspace: the label in `--text-md`, a mana dot, the count
  "· 5 / 6" in `--text-faint`, and a 1px rule that fills the rest of the row. It collapses
  when clicked.

## Card tiles
- **Image tile:** the rendered card at radius 4.5%.
  - On hover it lifts (`--shadow-1`) and gains a 1px `--border-strong`.
  - A status dot sits at the corner.
  - It's a drop target for art, shown with a dashed accent outline.
- **Compact tile** (Text mode): `--surface-1`, a 3px top border in its `--mana-*` color,
  then the name, `mana_cost`, the type line in muted text, and the rules clamped to
  4 lines.
- **Stack:** overlapping tiles that show only the name bar, and reveal the whole card on
  hover.

## Modals: `with modal(size, title, subtitle=…, actions=…) as m:`
- Backdrop: `--scrim` plus `--blur-backdrop`.
- The panel is `--surface-1` with radius `--radius-xl` and `--shadow-3`. It fades and
  scales in from 98%.
- Header (52px): the title in the display font at `--text-xl`, the subtitle muted, the
  actions, and a close ✕ icon button.
- The body scrolls. The footer is optional, with actions on the right: primary last,
  Cancel as ghost.
- Esc closes the modal. So does a click on the backdrop, except in `workspace` modals,
  where clicking outside does nothing because it's too easy to misclick.

## Confirm: `await confirm(title, message, confirm="Delete", kind="danger", details=…)`
One `sm` modal for every confirmation. It replaces the hand-made copies in the editor,
mechanics and cycles. The "Update N cards" flow uses `details` (see patterns.md).

## Empty state: `empty_state(icon, title, hint, action=…)`
Centered in its region: a 40px muted icon, the title in the display font, a one-line
hint, and one primary or secondary action. Example: "No mechanics yet", "Keywords,
ability words and actions live here", [New mechanic].

## Feedback
- **Status indicator** (top bar): a 6px dot and text.
  - "All changes saved" uses `--success`.
  - "Saving…" uses `--text-muted`.
  - "Drawing 4 cards…" uses `--info`.
  - Errors use `--danger` and open their details when clicked.
- **Toast** (`ui.notify`, themed): bottom-center, `--surface-3`, auto-hides after 3s.
  Used for results such as "Updated 5 card faces". Toasts never carry errors that need
  action.
