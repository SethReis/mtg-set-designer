"""MSE symbol fonts (.mse-symbol-font packages): how "2WU" becomes mana symbol images.

A symbol font lists symbols, each with a `code` (literal text, or a regex), an
`image` (often a script) and whether it is `enabled` (a script too). Splitting
tries the symbols in file order at each position and takes the first that
matches; unmatched characters are dropped (as in MSE). Images are drawn at
`size / image font size` of their natural size, plus `horizontal space`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable

import regex
from PIL import Image

from ..mse.reader import MSEReadError, Node, read_file
from ..mse.script import ast as A
from ..mse.script import images as I
from ..mse.script.parser import parse_template

# evaluate(script) -> value, in the card's script context
Evaluate = Callable[[A.Node], object]


@dataclass
class TextOverlay:
    """Text drawn on a symbol (e.g. the number on a generic mana circle). Sizes and
    margins are fractions of the symbol size."""
    font_name: str
    size: float = 1.0
    color: tuple = (0, 0, 0, 255)
    max_stretch: float = 1.0
    alignment: str = "middle center"
    margins: tuple[float, float, float, float] = (0, 0, 0, 0)     # left, top, right, bottom


@dataclass
class SymbolDef:
    code: str
    is_regex: bool
    image: A.Node | None
    enabled: A.Node | None
    image_font_size: float
    draw_text: int = -1
    compiled: regex.Pattern | None = None
    overlay: TextOverlay | None = None


@dataclass
class SymbolFont:
    package: str                        # "magic-mana-small"
    folder: Path
    image_font_size: float = 12.0
    horizontal_space: float = 1.0
    vertical_space: float = 1.0
    symbols: list[SymbolDef] = field(default_factory=list)


def _value(nodes: list[Node], key: str, default: str = "") -> str:
    return next((n.value for n in nodes if n.key == key), default)


def _template(nodes: list[Node], key: str) -> A.Node | None:
    node = next((n for n in nodes if n.key == key), None)
    if node is None:
        return None
    return parse_template(node.text())


def _overlay(children: list[Node]) -> TextOverlay | None:
    node = next((n for n in children if n.key == "text font"), None)
    if node is None or not node.block:
        return None
    try:
        font = node.children()
    except MSEReadError:
        return None
    from ..mse.script.values import ScriptError, to_color
    try:
        c = to_color(_value(font, "color", "black") or "black")
        color = (c.r, c.g, c.b, c.a)
    except ScriptError:
        color = (0, 0, 0, 255)
    margin = lambda side: float(_value(children, f"text margin {side}", "0") or 0)
    return TextOverlay(font_name=_value(font, "name", ""), size=float(_value(font, "size", "1") or 1),
                       color=color, max_stretch=float(_value(font, "max stretch", "1") or 1),
                       alignment=_value(children, "text alignment", "middle center") or "middle center",
                       margins=(margin("left"), margin("top"), margin("right"), margin("bottom")))


@lru_cache(maxsize=None)
def load_symbol_font(root: Path, name: str) -> SymbolFont:
    package = name[:-len(".mse-symbol-font")] if name.endswith(".mse-symbol-font") else name
    folder = root / f"{package}.mse-symbol-font"
    nodes, _ = read_file(folder / "symbol-font", root)
    font = SymbolFont(package, folder,
                      image_font_size=float(_value(nodes, "image font size", "12") or 12),
                      horizontal_space=float(_value(nodes, "horizontal space", "1") or 1),
                      vertical_space=float(_value(nodes, "vertical space", "1") or 1))
    for node in nodes:
        if node.key != "symbol":
            continue
        try:
            children = node.children()
        except MSEReadError:
            continue
        code = _value(children, "code")
        if not code:
            continue
        is_regex = _value(children, "regex") in ("true", "yes")
        sym = SymbolDef(code=code, is_regex=is_regex, image=_template(children, "image"),
                        enabled=_template(children, "enabled"),
                        image_font_size=float(_value(children, "image font size", "")
                                              or font.image_font_size),
                        draw_text=int(_value(children, "draw text", "-1") or -1),
                        overlay=_overlay(children))
        if is_regex:
            try:
                sym.compiled = regex.compile(code)
            except regex.error:
                continue
        font.symbols.append(sym)
    return font


@dataclass
class PlacedSymbol:
    symbol: SymbolDef
    text: str                           # the code text it stands for
    label: str = ""                     # text drawn on the symbol (regex group), if any


class SymbolRenderer:
    """A symbol font used for one card: knows how to evaluate its scripts.
    Implements layout.SymbolProvider."""

    def __init__(self, font: SymbolFont, evaluate: Evaluate, root: Path):
        self.font = font
        self.evaluate = evaluate
        self.root = root
        self._enabled: dict[int, bool] = {}
        self._images: dict[int, I.Raster | None] = {}
        self._sized: dict[tuple[int, int], Image.Image | None] = {}

    def enabled(self, sym: SymbolDef) -> bool:
        key = id(sym)
        if key not in self._enabled:
            ok = True
            if sym.enabled is not None:
                try:
                    from ..mse.script.values import to_bool
                    ok = to_bool(self.evaluate(sym.enabled))
                except Exception:
                    ok = False
            self._enabled[key] = ok
        return self._enabled[key]

    def split(self, text: str) -> list[PlacedSymbol]:
        out, pos = [], 0
        while pos < len(text):
            for sym in self.font.symbols:
                if not self.enabled(sym):
                    continue
                if sym.is_regex:
                    m = sym.compiled.match(text, pos)
                    if m and m.end() > pos:
                        label = ""
                        if 0 <= sym.draw_text <= len(m.groups()):
                            label = m.group(sym.draw_text) or ""
                        out.append(PlacedSymbol(sym, m.group(0), label))
                        pos = m.end()
                        break
                elif text.startswith(sym.code, pos):
                    out.append(PlacedSymbol(sym, sym.code, sym.code if sym.draw_text >= 0 else ""))
                    pos += len(sym.code)
                    break
            else:
                pos += 1                        # no symbol: the character is dropped
        return out

    def natural_image(self, sym: SymbolDef) -> I.Raster | None:
        key = id(sym)
        if key not in self._images:
            raster = None
            if sym.image is not None:
                try:
                    value = self.evaluate(sym.image)
                    opts = I.ImageOptions(root=self.root, package=self.font.folder)
                    raster = I.as_image(value).generate(opts)
                except Exception:
                    raster = None
            self._images[key] = raster
        return self._images[key]

    def image(self, piece: PlacedSymbol, px: float) -> Image.Image | None:
        """The symbol at font size `px` (MSE: natural size * int(size) // int(image font size);
        the size is the symbol font's size as given, not converted to pixels)."""
        sym = piece.symbol
        key = (id(sym), int(px), piece.label)
        if key not in self._sized:
            raster = self.natural_image(sym)
            if raster is None:
                self._sized[key] = None
            else:
                size, authored = max(1, int(px)), max(1, int(sym.image_font_size))
                w = max(1, raster.width * size // authored)     # integer maths, as in MSE
                h = max(1, raster.height * size // authored)
                image = raster.resized(w, h).to_pil().convert("RGBA")
                if piece.label and sym.overlay is not None:
                    draw_overlay(image, piece.label, sym.overlay, px)
                self._sized[key] = image
        return self._sized[key]


def draw_overlay(image: Image.Image, label: str, overlay: TextOverlay, px: float) -> None:
    """Draw a symbol's text (e.g. "12" on a generic mana circle), shrinking it until it
    fits the margins, and squeezing it horizontally down to `max stretch`."""
    from PIL import ImageDraw
    from .fonts import load_font
    ml, mt, mr, mb = (m * px for m in overlay.margins)
    box_w, box_h = image.width - ml - mr, image.height - mt - mb
    size = overlay.size * px
    while size >= 1:
        font = load_font(overlay.font_name, max(1, round(size))).font
        left, top, right, bottom = font.getbbox(label)
        tw, th = right - left, bottom - top
        if th <= box_h and tw * overlay.max_stretch <= box_w:
            break
        size -= 1
    else:
        return
    stretch = min(1.0, box_w / tw) if tw > 0 else 1.0
    layer = Image.new("RGBA", (max(1, int(tw + 2)), max(1, int(th + 2))), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((1 - left, 1 - top), label, font=font, fill=overlay.color)
    if stretch < 1:
        layer = layer.resize((max(1, round(layer.width * stretch)), layer.height),
                             Image.Resampling.LANCZOS)
    x = ml + (box_w - layer.width) / 2
    y = mt + (box_h - layer.height) / 2
    image.alpha_composite(layer, (round(x), round(y)))
