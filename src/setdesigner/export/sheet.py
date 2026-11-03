"""Where cards go on the paper (pure geometry, in millimetres from the page's top left).

    grid = fit("a4", bleed=1, spacing=0)        # 3 x 3 cards, centred
    for page in pages(faces, grid):
        for slot in page: ...                    # slot.x, slot.y: the card's trim box

Each card is 63 x 88 mm (its trim box). Bleed is extra picture around it, so cards sit
2 x bleed (+ spacing) apart. Trim boxes stay inside the printable margin; the outer
bleed may run into it. Labels need a few millimetres under every row.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, TypeVar

CARD = (63.0, 88.0)                     # width, height of a card, mm
MARGIN = 4.0                            # most home printers can't print closer to the edge
LABEL = 3.0                             # room for a label under each row
PAPERS = {"a4": ("A4", 210.0, 297.0), "letter": ("Letter", 215.9, 279.4)}

T = TypeVar("T")


@dataclass
class Grid:
    page: tuple[float, float]           # width, height
    columns: int
    rows: int
    left: float                         # trim box of the top-left card
    top: float
    step_x: float                       # from one card's left edge to the next one's
    step_y: float
    bleed: float
    card: tuple[float, float] = CARD

    @property
    def per_page(self) -> int:
        return self.columns * self.rows

    def position(self, index: int) -> tuple[float, float]:
        """Trim box top-left of the index-th card on a page (row by row)."""
        row, column = divmod(index, self.columns)
        return self.left + column * self.step_x, self.top + row * self.step_y

    def trim_lines(self) -> tuple[list[float], list[float]]:
        """x positions of every card's left/right edge and y of every top/bottom edge."""
        w, h = self.card
        xs = sorted({x for c in range(self.columns) for x in (self.left + c * self.step_x,
                                                              self.left + c * self.step_x + w)})
        ys = sorted({y for r in range(self.rows) for y in (self.top + r * self.step_y,
                                                           self.top + r * self.step_y + h)})
        return xs, ys


@dataclass
class Slot:
    x: float
    y: float
    item: object


def fit(paper: str, bleed: float = 0.0, spacing: float = 0.0, labels: bool = False,
        card: tuple[float, float] = CARD, margin: float = MARGIN) -> Grid:
    """As many cards as fit, centred. At least one card, even if it doesn't fit."""
    _, page_w, page_h = PAPERS[paper]
    w, h = card
    gap_x = 2 * bleed + spacing
    gap_y = 2 * bleed + spacing + (LABEL if labels else 0.0)

    def count(space: float, size: float, gap: float) -> int:
        return max(1, int((space - size) // (size + gap)) + 1) if space >= size else 1

    columns = count(page_w - 2 * margin, w, gap_x)
    rows = count(page_h - 2 * margin, h, gap_y)
    used_w = columns * w + (columns - 1) * gap_x
    used_h = rows * h + (rows - 1) * gap_y + (LABEL if labels else 0.0)
    return Grid((page_w, page_h), columns, rows, (page_w - used_w) / 2, (page_h - used_h) / 2,
                w + gap_x, h + gap_y, bleed, card)


def pages(items: Sequence[T], grid: Grid) -> list[list[Slot]]:
    """The items laid out row by row, page by page."""
    out = []
    for start in range(0, len(items), grid.per_page):
        out.append([Slot(*grid.position(i), item)
                    for i, item in enumerate(items[start:start + grid.per_page])])
    return out
