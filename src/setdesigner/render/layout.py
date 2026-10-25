"""The renderer's own description of a card: a canvas and a stack of layers.

This is the seam between "what to draw" and "how to draw it". The drawing engine
(draw.py, text.py, ...) only knows these classes; producers turn a card into them
(mse_layout.py does so from MSE stylesheets; other producers can come later).
All coordinates are pixels on the card at scale 1 (M15: 375 x 523).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from PIL import Image


@dataclass(frozen=True)
class Box:
    left: float
    top: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    def scaled(self, s: float) -> "Box":
        return Box(self.left * s, self.top * s, self.width * s, self.height * s)


@dataclass(frozen=True)
class Alignment:
    """Where content sits in its box, plus flags.
    horizontal: left / center / right / justify / justify-all / stretch
    vertical:   top / middle / bottom
    shrink_overflow: shrink text rather than let it overflow (text boxes)."""
    horizontal: str = "left"
    vertical: str = "top"
    shrink_overflow: bool = False

    @classmethod
    def parse(cls, text: str, default: "Alignment | None" = None) -> "Alignment":
        """MSE-style words, e.g. "middle right", "left bottom shrink-overflow", "stretch"."""
        base = default or cls()
        words = text.lower().replace(",", " ").split()
        horizontal, vertical = base.horizontal, base.vertical
        for w in words:
            if w in ("left", "center", "right", "justify", "justify-all", "stretch"):
                horizontal = w
            elif w in ("top", "middle", "bottom"):
                vertical = w
        if "stretch" in words:
            horizontal = "stretch"
        return cls(horizontal, vertical, "shrink-overflow" in words)

    def place(self, size: tuple[float, float], box: Box) -> tuple[float, float]:
        """Top-left position of content of `size` inside `box`."""
        w, h = size
        x = {"center": box.left + (box.width - w) / 2,
             "right": box.right - w}.get(self.horizontal, box.left)
        y = {"middle": box.top + (box.height - h) / 2,
             "bottom": box.bottom - h}.get(self.vertical, box.top)
        return x, y


@dataclass
class ImageLayer:
    """A raster drawn into a box. `image` is already at the box's pixel size (or
    smaller, then aligned); `mask` (grey, same size as image) limits its alpha."""
    box: Box
    image: Image.Image                  # RGBA
    combine: str | None = None          # blend mode with what is below (None = normal)
    alignment: Alignment = field(default_factory=lambda: Alignment("stretch"))
    angle: float = 0.0


@dataclass(frozen=True)
class FontSpec:
    name: str
    size: float                          # points; pixels = size * 96 / 72 * scale
    color: tuple[int, int, int, int] = (0, 0, 0, 255)
    italic_name: str = ""
    bold: bool = False
    italic: bool = False
    scale_down_to: float = 100000.0      # smallest size (points) to shrink to
    max_stretch: float = 1.0
    shadow_color: tuple[int, int, int, int] = (0, 0, 0, 0)
    shadow_dx: float = 0.0
    shadow_dy: float = 0.0
    shadow_blur: float = 0.0
    stroke_radius: float = 0.0
    stroke_color: tuple[int, int, int, int] = (0, 0, 0, 255)
    stroke_blur: float = 0.0
    separator_color: tuple[int, int, int, int] = (0, 0, 0, 128)


class SymbolProvider(Protocol):
    """Turns symbol text ("2WU") into symbol pictures. Pieces are opaque; `.text` is
    the text a piece stands for."""

    def split(self, text: str) -> list: ...

    def image(self, piece, px: float) -> "Image.Image | None": ...


@dataclass
class SymbolFontSpec:
    provider: SymbolProvider
    size: float = 12.0                   # points
    scale_down_to: float = 1.0
    alignment: Alignment = field(default_factory=lambda: Alignment("center", "middle"))
    spacing: float = 1.0                 # extra pixels after each symbol


@dataclass
class TextLayer:
    """Tagged text (MSE tag syntax: <b>, <i…>, <sym>, <line>, …) laid out in a box."""
    box: Box
    text: str
    font: FontSpec
    symbol_font: SymbolFontSpec | None = None
    always_symbol: bool = False
    alignment: Alignment = field(default_factory=Alignment)
    padding: tuple[float, float, float, float] = (0, 0, 0, 0)       # left, top, right, bottom
    line_height_soft: float = 1.0
    line_height_hard: float = 1.0
    line_height_line: float = 1.0
    line_height_soft_max: float = 0.0
    line_height_hard_max: float = 0.0
    line_height_line_max: float = 0.0
    paragraph_height: float = -1.0
    multi_line: bool = True
    mask: Image.Image | None = None      # "L" image at box size: text rows stay inside it
    angle: float = 0.0


@dataclass
class CardLayout:
    width: int
    height: int
    layers: list[ImageLayer | TextLayer] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
