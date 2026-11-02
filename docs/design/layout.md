# Layout

## The app shell
```
┌──────┬───────────────────────────────────────────────────────────┐
│ rail │ top bar: ◆ Emberwild EMW  [ search cards…  ]  ● saved [+ New card] ⋯ │
│      ├───────────────────────────────────────────────────────────┤
│ Cards│ toolbar: [Rows|Matrix] Group by ▾ Sort ▾  [Grid|Stacks] [Filters·2] ─○─ │
│ Mech │───────────────────────────────────────────────────────────│
│ Cycl │ workspace (scrolls)                                        │
│ Arch │   White · 5 / 6 ─────────────────────────────────          │
│ Hlth │   ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢   (tiles fill the row)                    │
│      │                                                            │
│ ⚙ Set│                                                            │
│ ← Sets│                                                           │
└──────┴───────────────────────────────────────────────────────────┘
```
- **Rail:** 64px collapsed (icons only, labels in tooltips) or 220px expanded (icons and
  labels). It's toggled with the chevron at its foot and remembered in Settings. The
  `--surface-1` rail has a 1px right border.
- **Top bar:** 52px, `--surface-1`, with a 1px bottom border. From left to right:
  - the set symbol (24px) and set name (display font), then the code (muted);
  - the search field (grows, max 480px);
  - the status (dot and text);
  - the primary action;
  - the overflow menu.
- **Toolbar:** 44px, on `--bg`. It belongs to the workspace, not to the shell.
- **Workspace:** fills the rest of the window and is the only region that scrolls.

The window itself never scrolls. Every region that can overflow has its own scroll area.

## Fluid rules
1. **No `max-width` on work areas:** lists, tables, forms, grids and dashboards.
   - Prose (help text, descriptions) caps at `68ch`.
   - Form fields cap at a sensible width *per field* through the grid track, not by
     capping the container.
2. **Grids:** `repeat(auto-fill, minmax(<min>, 1fr))`. The minimum is the smallest width at
   which the content still reads.
   - Card tiles use the card-size setting as their minimum, so the tiles grow a little to
     fill the row rather than leaving a gap. Never use `space-between`.
3. **Side columns** use `clamp()`.
   - Card list: `clamp(220px, 18vw, 300px)`.
   - Preview: `clamp(300px, 28vw, 460px)`.
   - The middle column takes the rest.
4. **Tables** use `minmax()` tracks.
   - Name columns: `minmax(160px, 2fr)`.
   - Numbers: `minmax(48px, auto)`, right-aligned.
5. **Fields in a form** go in a `responsive_grid(min)`:
   - short fields (P/T, number) at 120;
   - normal fields at 220;
   - long fields span the full row.

## Breakpoints
The app is a desktop window, but it must work down to **1100×700** with no horizontal
scrolling.
| Width | Changes |
| --- | --- |
| ≥ 1600 | The rail can stay expanded. Health has 2 columns. The editor shows all three columns |
| 1100–1600 | The rail collapses by default. Health has 1 column. The editor's card list collapses to a toggle |
| < 1100 | The editor preview moves above the form. The modal becomes full-window |

## Modal geometry
| Size | Width | Height | Used for |
| --- | --- | --- | --- |
| `sm` | 440px | auto | Confirmations |
| `md` | 720px | auto (max 85vh) | Set settings, New set, Tune checks |
| `lg` | min(1080px, 92vw) | max 88vh | Archetypes, card lists |
| `workspace` | 94vw | 92vh | Card editor, Mechanics, Cycles, Health |

A modal has a header (52px: title, context, actions, close), a body that scrolls, and an
optional footer (actions aligned right). Workspace modals have no footer, because they
save as you go.
