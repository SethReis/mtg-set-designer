# Printing

**Print** in the rail (`/set?open=print`) makes a PDF of paper proxies to cut out and sleeve
with bulk cards. Printing is single-sided (duplex off), so every face is its own card:
a transform card prints its front, then its back, next to each other.

## Options
Your choices are remembered between sessions (in your settings, not the set).

- **Cards:** the whole set, or the overview's current filter (offered while one is on).
- **Copies:**
  - *One of each* prints every card once (a cube).
  - *By rarity* prints each card as many times as its rarity says (4 commons, 2
    uncommons, 1 rare, 1 mythic by default), for drafting from a pool. A card's own
    **Print copies** (in the editor, under Stats and set data) wins; 0 leaves it out.
- **Style:**
  - *Rendered* prints the real card pictures.
  - *Printer-friendly* prints playtest-style text cards to save ink (see below).
- **Paper:** A4 or Letter. Cards are always 63 × 88 mm, 3 × 3 to a page; the summary line
  says how many fit.
- **Bleed:** none, 1 mm or 3 mm of extra picture around each card, so a slightly off cut
  doesn't show white. With 3 mm on Letter only two rows fit.
- **Order:** collector number, color or rarity. Copies of a card stay together.
- **Crop marks:** short lines in the margins in line with every card edge, for a ruler or a
  paper cutter. They never touch a card.
- **Labels under cards:** "EMW 12 · back" in small print, to sort a printout.

The preview shows each page with the overview's pictures. **Export PDF** opens the system's
Save As (in a browser, the PDF downloads). Rendering can take a while the first time, so
the footer shows progress and a **Cancel** button.

## Rendered prints
Cards are drawn by Magic Set Editor at full size (about 150 dpi for M15), in batches like
the overview's pictures, and cached under the overview's picture cache
(`%LOCALAPPDATA%/setdesigner/thumbnails/<set>/print/`), so exporting an unchanged set again
renders nothing. If MSE can't run, the built-in renderer draws them and the dialog says so
(when it opens, and after the export); those pictures aren't kept, so MSE redraws them once
it works again.

### When Windows blocks Magic Set Editor
Windows' **Smart App Control** trusts the unsigned `magicseteditor.com` for about a day
after it was opened through Windows' own launcher (a double-click, for example). It stores
that trust on the file itself, with an expiry. When it lapses, the app's background MSE is
blocked, and cards are drawn by the built-in renderer (the "stand-in"), which gets the
layout right but not every detail of the text and symbols.

The app says so wherever cards show:
- a banner under the top bar;
- a line under the editor's preview;
- the Print dialog, where Export becomes **Export with stand-in pictures** and asks first.

All three offer **Renew Magic Set Editor** (`app/mse_trust.py`). It runs MSE once through
Windows' launcher, hidden, with `--version` (which just prints and exits), so nothing opens:
first the `.com`, then the `.exe`. It ends anything it started, then tries the app's own MSE
again.

If Windows wants a real double-click instead, the banner opens MSE's folder and asks for
one. The app closes that MSE window itself once MSE works. Which route worked is logged.
Stand-in pictures are kept apart from MSE's in the caches, so they're redrawn by MSE once
it works.

This is a stopgap; the aim is a renderer that doesn't need the MSE program at all. For
trying the blocked path without Windows, set `SETDESIGNER_FAKE_MSE_BLOCK=1`: MSE then acts
blocked until **Renew** is pressed.

Each card's rounded corners are filled with its border color, so the cards print square
and cut cleanly. Bleed repeats the card's outermost pixels outward. Each distinct face is
stored once in the PDF however many copies print.

## Printer-friendly prints
No art and no frame: a thin border, then
- the name and cost;
- the type line;
- the rules text, with the set's reminder text where the renders show it (the mechanic's
  reminder policy, or the card's own choice), and parenthesized text in italics;
- the flavor text in italics, after a thin rule;
- P/T or loyalty;
- rarity, number and set code.

Symbols become plain characters: `{2}{W}` → `2W`, `{T}` → `T`, `{W/U}` → `(W/U)`.
CARDNAME becomes the card's name. Reminder text for the game's own keywords (Flying,
Trample) isn't added; only your set's mechanics have theirs. Text shrinks from 9 to 6
points to fit; if it still doesn't, it is cut off with "…" and the dialog names the card.

## Code
| Module | What it does |
| --- | --- |
| `export/selection.py` | `PrintOptions`, copies, sort order, `print_faces` (no UI) |
| `export/sheet.py` | paper sizes, `fit` (the grid), `pages` |
| `export/pdf.py` | `write_pdf` (reportlab), corners and bleed, crop marks, labels |
| `export/playtest.py` | printer-friendly cards, `plain_symbols` |
| `app/mechanics.py` | `with_reminders`: reminder text written into rules text |
| `app/printing.py` | `export_pdf`: pictures (cached), then the PDF, with progress and cancel |
| `ui/print_dialog.py` | the Print modal |

Tests: `tests/export/`, `tests/app/test_printing.py` and `tests/ui/test_print.py`.
