# Navigation

## Places
| Place | Kind | How you get there |
| --- | --- | --- |
| Start (sets) | Page `/` | App start, "← Sets" in the rail |
| Cards | The workspace, `/set` | Rail: **Cards** |
| Card editor | Workspace modal | Click a tile, **New card**, search result, any card chip |
| Mechanics | Workspace modal | Rail: **Mechanics** |
| Cycles | Workspace modal | Rail: **Cycles**, the cycle link in the editor |
| Archetypes | `lg` modal | Rail: **Archetypes** |
| Health | Workspace modal | Rail: **Health** (with a warnings badge) |
| Set settings | `md` modal | Rail: **Set** (bottom) |

Rail order, from top to bottom: Cards · Mechanics · Cycles · Archetypes · Health. A divider
follows, then Set and ← Sets. New sections go above the divider in the order a designer
uses them. The rail scales to about 10 items before it needs groups.

## Modals over the workspace
- **One level deep.** Opening a card from Health or Mechanics *replaces* that modal with
  the card editor. Closing the editor returns to the modal it came from. There is a
  one-step "return to" and no stack of nested dialogs.
- **Confirmations** (`sm`) may sit on top of any modal. They're the only exception to
  "one level".
- The workspace behind a modal stays live. Edits made in the modal show on the tiles when
  it closes.

## URLs and deep links
The state lives in the query string of `/set`, so reloading or pasting a link reopens the
same view:
- `/set?card=<id>`
- `/set?open=mechanics&id=<mechanic id>`
- `/set?open=cycles&id=<cycle id>`
- `/set?open=health`, `/set?open=archetypes`, `/set?open=settings`

The old routes (`/set/card/<id>`, `/set/mechanics`, `/set/cycles?cycle=`, `/set/health`)
redirect to these.

## Keys
| Key | Does |
| --- | --- |
| Esc | Closes the top modal (flushing unsaved edits first) |
| Ctrl+K / Ctrl+F | Focuses card search (top bar; in the editor, its card list) |
| Ctrl+N | New card (opens it in the editor) |
| Ctrl+D | Duplicate the card (editor) |
| Alt+← / Alt+→ | Previous / next card in the editor, in workspace order |
| Ctrl+B | Toggles the rail |

Shortcuts are shown in the tooltips of their buttons ("New card · Ctrl+N").
