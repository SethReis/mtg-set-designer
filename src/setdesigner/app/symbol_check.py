"""Does a set symbol still read at the size it's printed? (Advice for the Set panel.)

On an M15 card the rarity symbol is about 20 pixels tall at 150 dpi (3-4 mm). Two checks
on the symbol's shape drawn at that size:

- thin lines: shrinking the small shape by one pixel removes most of it (strokes are
  about a pixel wide, so they print faint or vanish);
- fine detail: the small shape, scaled back up, differs a lot from the full-size one
  (holes, spikes and hatching merge into a blob).

Thresholds were tuned on test shapes (tests/app/test_symbol_check.py): a bold shield
passes, a thin ring and fine hatching are flagged. The result is advice, never a block.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

PRINT_SIZE = 20                 # pixels on the longest side, as on an M15 card at 150 dpi
THIN_KEEP = 0.30                # thin lines: less than this share survives a 1 px shrink
DETAIL_LOST = 0.30              # fine detail: more than this share of the shape changes

THIN_LINES = "Thin lines may disappear when printed this small; try thicker strokes."
FINE_DETAIL = "Fine detail is lost at card size; consider a bolder, simpler shape."
TOO_SMALL = "Almost nothing of the symbol is left at card size."


def _mask(image: Image.Image) -> np.ndarray:
    return np.asarray(image, np.uint8) > 127


def check_shape(shape: Image.Image, print_size: int = PRINT_SIZE) -> list[str]:
    """Warnings for a symbol shape (an "L" image, white = symbol). Empty list = fine."""
    scale = print_size / max(shape.size)
    small_size = (max(1, round(shape.width * scale)), max(1, round(shape.height * scale)))
    small = shape.resize(small_size, Image.Resampling.LANCZOS)
    area = _mask(small).sum()
    if area < 4:
        # nothing solid left: either the shape really is tiny, or it is fine lines that
        # blur into grey
        coverage = np.asarray(small, np.float64).mean() / 255
        return [TOO_SMALL] if coverage < 0.03 else [THIN_LINES, FINE_DETAIL]
    warnings = []
    kept = _mask(small.filter(ImageFilter.MinFilter(3))).sum() / area
    if kept < THIN_KEEP:
        warnings.append(THIN_LINES)
    full = _mask(shape)
    back = _mask(small.resize(shape.size, Image.Resampling.BILINEAR))
    lost = (full ^ back).sum() / max(1, full.sum())
    if lost > DETAIL_LOST:
        warnings.append(FINE_DETAIL)
    return warnings


def check_symbol(path: Path | None) -> list[str]:
    """Warnings for a symbol file (SVG or image); none without a file."""
    if path is None or not Path(path).is_file():
        return []
    from ..render.symbol import _shape
    return check_shape(_shape(str(path), Path(path).stat().st_mtime))
