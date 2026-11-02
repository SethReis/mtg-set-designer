# Design language

How the Set Designer looks and behaves. Every screen follows these documents. When a new
screen needs something they don't cover, add it here first and then build it.

## Principles
1. **The cards are the hero.** The chrome is quiet and neutral, so card art, frames and
   mana colors carry the color. Accent color is reserved for the one thing to do next.
2. **Never lose the set.** The card workspace is home. Editing a card, a mechanic, a cycle,
   the set's settings or its health happens in a modal over the blurred set, never on a
   separate page. Esc always brings you back.
3. **Fill the window.** Work areas stretch to the window. Use fluid grid tracks
   (`minmax(…, 1fr)`) instead of fixed pixel widths. Only prose gets a capped line length.
4. **One primary action per view.** Each view has one filled accent button at most. The
   rest are secondary or ghost buttons.
5. **Flavor in small doses.** Real mana symbols, the set symbol in the chrome, mana-color
   accents on color data, and a display font for titles. No textures, no parchment, no
   fantasy fonts in body text.
6. **Calm feedback.** Saving is automatic and shown quietly. Warnings are amber and
   errors red, and the two are never mixed. Confirm only what is destructive or touches
   many cards.
7. **Keyboard-friendly.** Every modal closes with Esc. Common actions have shortcuts, and
   the shortcuts are shown in tooltips.

## Documents
| File | What it settles |
| --- | --- |
| [tokens.md](tokens.md) | Color (both themes, mana, rarity, semantic), type, spacing, radii, elevation, motion |
| [layout.md](layout.md) | The app shell, fluid layout rules, scroll regions, breakpoints |
| [navigation.md](navigation.md) | Sidebar, workspace vs modal, deep links, Esc/Back |
| [components.md](components.md) | Buttons, fields, chips, pips, lists, tables, panels, modals, empty states |
| [patterns.md](patterns.md) | List+detail, autosave, destructive actions, "update N cards", warnings, loading |
| [voice.md](voice.md) | Labels, helper text, empty states, numbers |
| [mockup.html](mockup.html) | A static page that uses the real tokens: the reference picture |

The tokens are implemented in `src/setdesigner/ui/theme/tokens.css`. The shared components
are in `src/setdesigner/ui/components.py`. A screen uses those two, and never hex values or
ad-hoc Tailwind colors.

## Future surfaces
- **Print mode:** playtest sheets with no art or frame, symbols as plain characters
  (`{2}{W}` becomes `2W`) and thin borders. It's built from `components.compact_tile`
  (HANDOFF.md). Printing always uses the light theme and plain black on white.
- **Click-to-edit on the card preview:** see HANDOFF.md, where the editor's form is
  described as not final.
