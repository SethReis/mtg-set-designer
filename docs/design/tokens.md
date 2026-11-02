# Tokens

All values live as CSS custom properties in `ui/theme/tokens.css`. The dark theme is the
default (`:root`), and the light theme is `body.body--light`, which is Quasar's class. Code
refers to a token by name (`var(--surface-2)`) and never by its value.

## Color

### Surfaces and text
| Token | Dark | Light | Use |
| --- | --- | --- | --- |
| `--bg` | `#0e1014` | `#f5f4f0` | Window background, behind the workspace |
| `--surface-1` | `#15181e` | `#ffffff` | Rail, top bar, panels, modal body |
| `--surface-2` | `#1c2028` | `#f0eee9` | Inputs, list rows on hover, table headers |
| `--surface-3` | `#252b35` | `#e6e3dc` | Selected rows, pressed states, chips |
| `--border` | `#2a303b` | `#e0dcd3` | Hairlines between regions, field outlines |
| `--border-strong` | `#3a4250` | `#c9c4b8` | Focused outlines when not in accent, dividers that must show |
| `--text` | `#e8eaef` | `#1c1e23` | Body text |
| `--text-muted` | `#9aa2b1` | `#5c6370` | Labels, secondary text |
| `--text-faint` | `#69717f` | `#8c919b` | Placeholders, disabled, counts |
| `--scrim` | `rgb(8 10 14 / 55%)` | `rgb(40 36 28 / 30%)` | Modal backdrop (together with the blur) |

### Accent
One accent, a **gold** that nods to rare and mythic symbols without being yellow.
| Token | Dark | Light |
| --- | --- | --- |
| `--accent` | `#d9ad55` | `#9a6d14` |
| `--accent-hover` | `#e6bf6e` | `#82590b` |
| `--accent-soft` | `rgb(217 173 85 / 14%)` | `rgb(154 109 20 / 10%)` |
| `--on-accent` | `#1a1408` | `#ffffff` |

Use the accent for the primary button, the selected rail item's indicator, focus rings,
links and the active segment of a segmented control. Nothing else gets it.

### Semantic
| Token | Dark | Light | Use |
| --- | --- | --- | --- |
| `--success` | `#46b97f` | `#1f8a55` | Saved, healthy, complete |
| `--warning` | `#e8a33d` | `#b06d00` | Health warnings, short of a target |
| `--danger` | `#e5574f` | `#c4352c` | Delete, errors, render failures |
| `--info` | `#5aa3e8` | `#2a6fb8` | Neutral notices, "info" warnings |

Each one has a `-soft` variant (14% dark, 10% light) for badge and banner backgrounds.

### Mana (color data)
These are for **data about colors**: pips, group headers, tile borders and chart series.
They are never used for UI states.
| Token | Value | Notes |
| --- | --- | --- |
| `--mana-w` | `#efe6c4` | Gets a `--border-strong` outline on light surfaces |
| `--mana-u` | `#4b8fd6` | |
| `--mana-b` | `#8a7f93` | Lifted so it shows on dark surfaces |
| `--mana-r` | `#df5b3b` | |
| `--mana-g` | `#3f9a5d` | |
| `--mana-m` | `#d4af37` | Multicolor |
| `--mana-c` | `#a8aeb6` | Colorless |
| `--mana-l` | `#a5835b` | Lands |

They replace `COLOR_PIPS` / `COLOR_BORDERS` in `widgets.py`.

### Rarity
`--rarity-common` (`--text-muted`), `--rarity-uncommon` `#a9bacb`, `--rarity-rare` `#d9b35b`,
`--rarity-mythic` `#e8702a`, `--rarity-special` `#a66ad9`. They're used on the rarity
letter and the set-symbol preview.

### Card status
`--status-idea` (`--text-faint`), `--status-draft` `#e3c547`, `--status-playtested`
`#5aa3e8`, `--status-final` (`--success`).

## Type
| Token | Value |
| --- | --- |
| `--font-ui` | `"Inter", system-ui, sans-serif` |
| `--font-display` | `"Marcellus", "Cinzel", serif`, decided at mockup review. Titles only: set name, modal titles, empty-state titles |
| `--font-mono` | `"JetBrains Mono", ui-monospace, monospace` for templates and `{slot}` text |

| Step | Size / line height | Weight | Use |
| --- | --- | --- | --- |
| `--text-xs` | 11 / 16 | 500 | Counts, badges, captions |
| `--text-sm` | 13 / 18 | 400 | Default UI text, fields, rows |
| `--text-md` | 14 / 20 | 500 | Section titles, buttons |
| `--text-lg` | 17 / 24 | 600 | Panel titles |
| `--text-xl` | 22 / 28 | display | Modal titles, the set name in the top bar |
| `--text-2xl` | 30 / 36 | display | Start page title |

The UI is dense: 13px is the base, not 16. Numbers in tables and counts use
`font-variant-numeric: tabular-nums`.

**Mana symbols** in the UI come from the bundled **Mana** font (`ms ms-w ms-cost`).
`{W}` renders as a symbol, never as the letter in a colored box.

## Spacing
A 4px grid: `--space-1` 4, `-2` 8, `-3` 12, `-4` 16, `-5` 20, `-6` 24, `-8` 32, `-10` 40.
- Inside controls: 8 to 12.
- Between fields: 12.
- Between sections: 24.
- Panel padding: 16 (20 in modals).

## Radii
`--radius-sm` 4 (chips, badges), `--radius-md` 6 (buttons, fields), `--radius-lg` 10
(panels, tiles), `--radius-xl` 14 (modals). Card tiles use 4.5% of their width, like a
real card.

## Elevation
| Token | Use |
| --- | --- |
| `--shadow-1` | Hovered tile, menus |
| `--shadow-2` | Popovers, the filter panel |
| `--shadow-3` | Modals |

In the dark theme, elevation is mostly shown by a lighter surface plus a 1px `--border`.
Shadows stay subtle.

## Blur and motion
- `--blur-backdrop: 8px`: modal backdrops blur the workspace (`backdrop-filter`).
- `--ease: cubic-bezier(.2,.7,.2,1)`.
- `--dur-fast` 120ms is for hover and press. `--dur-med` 200ms is for modals, popovers
  and the rail.
- Respect `prefers-reduced-motion`: no scale-in, only fades.
