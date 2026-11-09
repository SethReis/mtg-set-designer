# Visual review

## Tooling
- `python tools/ui_sweep.py <set folder> <out>` screenshots every view and state at 900,
  1100, 1400 and 1920 px in both themes. It needs an app started with `SETDESIGNER_DEV=1`.
- `SETDESIGNER_VISUAL=1 pytest tests/ui_visual` runs `ui/theme/overlap_check.js` on every
  view and state at 900, 1100, 1280, 1400, 1600 and 1920 px. Edge is driven over its
  DevTools protocol, in real time.
  - **What it reports:**
    - text overlapping other text;
    - text spilling out of its box;
    - text cut off without an ellipsis;
    - a click that found nothing.
  - **What it looks at:** whole pages, including below the fold, once the page has stopped
    changing. `?dev_click=A|B` clicks through to dialogs, tabs and modes.
- `?part_outlines=1` (dev) outlines every editor hotspot on the card.

## Fixed
- **Field labels:** Quasar's floating labels collided with values and placeholders. Labels
  now stay above every field (`stack-label`).
- **Editor hotspots:** they were shorter than the name, cost and type bars. They now pad
  out to the bars (`PART_PADDING`).
- **Modal titles:** descenders were clipped.
- **List rows:** long two-faced names ran over the rarity letter. They're now cut with an
  ellipsis.
- **Data tables** (Health and others): headings overlapped the next column ("Mana value"
  / "Power / tough."). Each column is now at least as wide as its heading, and a table
  scrolls sideways when the window is narrower than that.
- **The first checker:** it missed most of this. It only looked at the first screen,
  measured before views finished loading, and clipped spilling text back into its own
  box.
