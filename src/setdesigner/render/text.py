"""The text engine: lay out and draw a TextLayer (tagged text in a box).

Follows MSE's text viewer (src/render/text/*.cpp in MagicSetEditor2):
  1. tags -> styled pieces: <b…> bold, <i…> italic, <sym…> symbols, <soft>/<sep-soft>
     (laid out but not drawn), <line>/<soft-line> around "\\n" choose the break kind,
     <size:N>/<color:C>/<font:F> override; other tags are ignored;
  2. greedy word wrap at a font scale; each line advances by its height times the
     line height for how it ended (soft = wrapped, hard = "\\n", line = <line>);
  3. if the text does not fit, binary-search the scale down to the fonts'
     `scale down to` (single-line fields with shrink-overflow squeeze horizontally);
  4. vertical alignment (gaps may stretch up to the *_max line heights), then
     horizontal alignment per line;
  5. draw: shadow, stroke and fill for text; symbol images inline.
Font sizes are points drawn at 96/72 pixels per point, like MSE on Windows. Text is
drawn at 4x and averaged down, and every run hangs from its line's top (MSE draws
each run at the top left of its line, not on a shared baseline).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np
from PIL import Image, ImageDraw

from ..mse.script.tokens import ESCAPED_LANGLE
from .fonts import TEXT_SCALING, LoadedFont, advance, downsample, load_font, scaled_px
from .layout import Box, TextLayer

SOFT, HARD, LINE = "soft", "hard", "line"


# ------------------------------------------------------------------ pieces

@dataclass(frozen=True)
class Style:
    bold: bool = False
    italic: bool = False
    symbol: bool = False
    soft: bool = False                  # laid out, not drawn (editor-only text)
    size: float | None = None           # points, overrides the font size
    color: tuple | None = None
    font: str | None = None


@dataclass
class Piece:
    kind: str                           # "text", "space", "break", "symbol"
    text: str = ""
    style: Style = field(default_factory=Style)
    brk: str = HARD                     # for breaks
    symbol: object = None               # provider piece, for symbols


def _parse_color(text: str) -> tuple | None:
    from ..mse.script.values import ScriptError, to_color
    try:
        c = to_color(text)
        return (c.r, c.g, c.b, c.a)
    except ScriptError:
        return None


def parse_tagged(text: str, symbols=None, always_symbol: bool = False) -> list[Piece]:
    """Tagged text -> pieces (words are split into text pieces at spaces)."""
    pieces: list[Piece] = []
    bold = italic = sym = soft = 0
    line = soft_line = 0
    sizes: list[float] = []
    colors: list[tuple] = []
    fonts: list[str] = []
    buf: list[str] = []

    def style() -> Style:
        return Style(bold > 0, italic > 0, sym > 0, soft > 0, sizes[-1] if sizes else None,
                     colors[-1] if colors else None, fonts[-1] if fonts else None)

    def flush() -> None:
        if not buf:
            return
        run, st = "".join(buf).replace(ESCAPED_LANGLE, "<"), style()
        buf.clear()
        if st.symbol and symbols is not None:
            for p in symbols.split(run):
                pieces.append(Piece("symbol", p.text, st, symbol=p))
            return
        if always_symbol and symbols is not None:
            st = replace(st, symbol=True)
            for p in symbols.split(run):
                pieces.append(Piece("symbol", p.text, st, symbol=p))
            return
        word = []
        for ch in run:
            if ch == " ":
                if word:
                    pieces.append(Piece("text", "".join(word), st))
                    word = []
                pieces.append(Piece("space", " ", st))
            else:
                word.append(ch)
        if word:
            pieces.append(Piece("text", "".join(word), st))

    i = 0
    while i < len(text):
        c = text[i]
        if c == "<":
            end = text.find(">", i)
            end = len(text) - 1 if end < 0 else end
            flush()
            tag = text[i + 1:end]
            closing = tag.startswith("/")
            name = tag[1:] if closing else tag
            base = name.split(":", 1)[0]
            delta = -1 if closing else 1
            if base == "b" or base.startswith("b-"):
                bold += delta
            elif base == "i" or base.startswith("i-"):
                italic += delta
            elif base == "sym" or base.startswith("sym-"):
                sym += delta
            elif base in ("soft", "sep-soft"):
                soft += delta
            elif base == "soft-line":
                soft_line += delta
            elif base == "line":
                line += delta
            elif base == "size":
                if closing:
                    sizes and sizes.pop()
                else:
                    try:
                        sizes.append(float(name.split(":", 1)[1]))
                    except (IndexError, ValueError):
                        pass
            elif base == "color":
                if closing:
                    colors and colors.pop()
                else:
                    parsed = _parse_color(name.split(":", 1)[1]) if ":" in name else None
                    if parsed:
                        colors.append(parsed)
            elif base == "font":
                if closing:
                    fonts and fonts.pop()
                elif ":" in name:
                    fonts.append(name.split(":", 1)[1])
            i = end + 1
            continue
        if c == "\n":
            flush()
            kind = LINE if line > 0 else SOFT if soft_line > 0 else HARD
            pieces.append(Piece("break", "\n", style(), brk=kind))
            i += 1
            continue
        buf.append(c)
        i += 1
    flush()
    return pieces


# ------------------------------------------------------------------ measuring

@dataclass
class Measured:
    piece: Piece
    width: float
    height: float                       # the line height this piece asks for
    font: LoadedFont | None = None
    image: Image.Image | None = None    # symbols


class Measurer:
    """Fonts and symbol images for one layer at one scale. Like MSE, text is measured
    at TEXT_SCALING times the size (Windows line metrics, no kerning) and divided back."""

    def __init__(self, layer: TextLayer, scale: float):
        self.layer = layer
        self.scale = scale
        self._fonts: dict[tuple, LoadedFont] = {}

    def points(self, st: Style) -> float:
        return (st.size if st.size is not None else self.layer.font.size) * self.scale

    def font(self, st: Style) -> LoadedFont:
        spec = self.layer.font
        italic = st.italic or spec.italic
        name = st.font or (spec.italic_name if italic and spec.italic_name else spec.name)
        use_italic = italic and not (spec.italic_name and not st.font)
        key = (name, scaled_px(self.points(st)), st.bold or spec.bold, use_italic)
        if key not in self._fonts:
            self._fonts[key] = load_font(*key)
        return self._fonts[key]

    def measure(self, piece: Piece) -> Measured:
        if piece.kind == "symbol":
            sf = self.layer.symbol_font
            # MSE sizes symbols by the font size itself (no points -> pixels conversion)
            px = sf.size * self.scale if sf else 0
            img = sf.provider.image(piece.symbol, px) if sf else None
            if img is None:
                return Measured(piece, 0, 0)
            w, h = sf.provider.size(piece.symbol, px)
            return Measured(piece, w + sf.spacing, h + sf.vertical_spacing, image=img)
        lf = self.font(piece.style)
        height = (lf.ascent + lf.descent) / TEXT_SCALING
        if piece.kind == "break":
            return Measured(piece, 0, height, lf)
        return Measured(piece, advance(lf, piece.text) / TEXT_SCALING, height, lf)


# ------------------------------------------------------------------- layout

@dataclass
class Line:
    items: list[Measured]
    top: float
    brk: str                            # how the line ended ("" for the last line)
    height: float = 0.0
    left: float = 0.0                   # x of the line's start (after alignment)
    xs: list[float] = field(default_factory=list)

    @property
    def bottom(self) -> float:
        return self.top + self.height

    @property
    def width(self) -> float:
        items = self.items
        while items and items[-1].piece.kind in ("space", "break"):
            items = items[:-1]
        return sum(m.width for m in items)


@dataclass
class TextResult:
    lines: list[Line]
    scale: float
    stretch: float                      # horizontal squeeze (single-line overflow)
    fits: bool

    @property
    def content_width(self) -> float:
        return max((l.width for l in self.lines), default=0.0)

    @property
    def content_height(self) -> float:
        return (self.lines[-1].bottom - self.lines[0].top) if self.lines else 0.0


def _row_edges(layer: TextLayer, top: float, height: float) -> tuple[float, float]:
    """Usable [left, right] for a line from top to top+height (mask rows + padding)."""
    pl, _, pr, _ = layer.padding
    w = layer.box.width
    if layer.mask is None:
        return pl, w - pr
    mask = np.asarray(layer.mask)
    y0 = max(0, int(top))
    y1 = min(mask.shape[0], max(y0 + 1, int(math.ceil(top + height))))
    rows = mask[y0:y1] > 127
    if rows.size == 0 or not rows.any():
        return pl, w - pr
    cols = np.where(rows.all(axis=0))[0]
    if cols.size == 0:
        cols = np.where(rows.any(axis=0))[0]
    return cols[0] + pl, cols[-1] + 1 - pr


def _multiplier(layer: TextLayer, brk: str) -> float:
    return {SOFT: layer.line_height_soft, HARD: layer.line_height_hard,
            LINE: layer.line_height_line}.get(brk, 1.0)


def _line_height(items: list[Measured]) -> float:
    # MSE doesn't count <line> breaks, so a line holding only one takes no room
    return max((x.height for x in items if not (x.piece.kind == "break" and x.piece.brk == LINE)),
               default=0.0)


def layout_at(layer: TextLayer, pieces: list[Piece], scale: float) -> TextResult:
    m = Measurer(layer, scale)
    measured = [m.measure(p) for p in pieces]
    _, pt, _, pb = layer.padding
    lines: list[Line] = []
    top = pt
    current: list[Measured] = []
    carried = 0.0           # MSE: an empty line is as high as the one above (0 after <line>)

    def end_line(brk: str) -> None:
        nonlocal top, current, carried
        height = _line_height(current)
        if height < 0.01 and lines:
            height = carried
        lines.append(Line(current, top, brk, height))
        top += height * _multiplier(layer, brk)
        carried = 0.0 if brk == LINE else height
        current = []

    # words: consecutive text/symbol pieces form one unbreakable unit
    i = 0
    while i < len(measured):
        item = measured[i]
        kind = item.piece.kind
        if kind == "break":
            current.append(item)
            end_line(item.piece.brk)
            i += 1
            continue
        if kind == "space":
            current.append(item)
            i += 1
            # MSE counts a word's trailing space too: if that overflows, the line ends
            # after the word (so a later break starts a line of its own)
            if layer.multi_line and any(x.piece.kind != "space" for x in current):
                left, right = _row_edges(layer, top, _line_height(current))
                if sum(x.width for x in current) > right - left:
                    while current[-1].piece.kind == "space":
                        current.pop()
                    end_line(SOFT)
            continue
        j = i
        while j < len(measured) and measured[j].piece.kind in ("text", "symbol"):
            j += 1
        word = measured[i:j]
        word_w = sum(w.width for w in word)
        if layer.multi_line and current:
            line_w = sum(x.width for x in current)
            left, right = _row_edges(layer, top, _line_height(current + word))
            if line_w + word_w > right - left and any(x.piece.kind != "space" for x in current):
                while current and current[-1].piece.kind == "space":
                    current.pop()
                end_line(SOFT)
        current.extend(word)
        i = j
    end_line("")
    # a trailing empty line only exists if the text ended with a break
    if len(lines) > 1 and not any(x.piece.kind in ("text", "symbol") for x in lines[-1].items) \
            and lines[-2].brk == HARD and not (pieces and pieces[-1].kind == "break"):
        lines.pop()
        lines[-1].brk = ""

    # MSE (TextStyle::getStretch): "stretch" / "shrink" alignments fit the text's width
    # to the box, with "overflow" only when it is too wide; other text just overflows
    stretch = 1.0
    content_w = max((l.width for l in lines if l.height > 0), default=0.0)
    avail_w = layer.box.width - layer.padding[0] - layer.padding[2]
    if content_w > 0 and (layer.alignment.horizontal == "stretch" or layer.alignment.shrink_overflow):
        factor = avail_w / content_w
        if not layer.alignment.shrink_overflow or factor < 1.0:
            stretch = max(0.01, factor)
    fits = (lines[-1].bottom <= layer.box.height - pb + 1e-6) if lines else True
    return TextResult(lines, scale, stretch, fits)


def scale_limits(layer: TextLayer, pieces: list[Piece]) -> tuple[float, float]:
    """MSE's smallest scale and scale step: per font, `scale down to` / size and a
    quarter point; the symbol font counts when the text has symbols."""
    sizes = [(layer.font.size, layer.font.scale_down_to)]
    sf = layer.symbol_font
    if sf is not None and any(p.kind == "symbol" for p in pieces):
        sizes.append((sf.size, sf.scale_down_to))
    lowest = max(min(size, down) / max(0.01, size) for size, down in sizes)
    step = min(1.0 / max(size * 4, 1.0) for size, _ in sizes)
    return lowest, max(0.01, step)


def layout_text(layer: TextLayer) -> TextResult:
    """Lay out with MSE's scale search (TextViewer::prepareLinesTryScales, from scale 1):
    a binary search, narrowed by how far each attempt over- or underflows."""
    pieces = parse_tagged(layer.text, layer.symbol_font.provider if layer.symbol_font else None,
                          layer.always_symbol)
    lowest, step = scale_limits(layer, pieces)
    result = layout_at(layer, pieces, 1.0)
    if lowest < 1.0 and not result.fits:
        _, _, _, pb = layer.padding
        box_h = layer.box.height

        def bound_max(r: TextResult) -> float:      # it fits at r.scale
            height = min(box_h + 1, r.lines[-1].bottom + pb)
            return r.scale * (box_h + 1) / height if height >= 1 else 1.0

        def bound_min(r: TextResult) -> float:      # it doesn't fit at r.scale
            height = r.lines[-1].bottom + pb
            return r.scale * box_h / height if height >= 1 else 0.0

        lo = max(lowest, bound_min(result))
        result = layout_at(layer, pieces, lo)
        hi = min(1.0, bound_max(result))
        best = lo
        while lo + step < hi:
            attempt = layout_at(layer, pieces, (lo + hi) / 2)
            if attempt.fits:
                lo = best = attempt.scale
                hi = min(hi, bound_max(attempt))
                result = attempt
            else:
                hi = attempt.scale
                lo = max(lo, bound_min(attempt))
        if best != lo:
            result = layout_at(layer, pieces, lo)
    lines = result.lines
    if len(lines) == 1 and lines[0].width < 0.0001 and not layer.always_symbol:
        lf = Measurer(layer, result.scale).font(Style())     # no text: one line of the font
        lines[0].height = (lf.ascent + lf.descent) / TEXT_SCALING
    return _finish(layer, result)


def _finish(layer: TextLayer, result: TextResult) -> TextResult:
    """Vertical then horizontal alignment (TextViewer::alignParagraph)."""
    lines = result.lines
    if not lines:
        return result
    pl, pt, pr, pb = layer.padding
    avail_h = layer.box.height - pt - pb
    # the text's height; trailing lines without height don't count
    height = 0.0
    for line in reversed(lines):
        height = line.bottom
        if line.height:
            break
    height -= lines[0].top
    # stretch the gaps between lines up to the *_max line heights: every kind that can
    # still grow gets the same extra, one stop at a time
    if height < avail_h:
        room = {SOFT: max(0.0, layer.line_height_soft_max - layer.line_height_soft),
                HARD: max(0.0, layer.line_height_hard_max - layer.line_height_hard),
                LINE: max(0.0, layer.line_height_line_max - layer.line_height_line)}
        stops = [0.0] + sorted(room.values())
        for n in range(1, 4):
            if height >= avail_h:
                break
            stop = stops[n] - stops[n - 1]
            if stop <= 0:
                continue
            kinds = {k for k, r in room.items() if r >= stop}
            total = sum(l.height for l in lines if l.brk in kinds)
            if total == 0:
                break
            to_add = min(stop, (avail_h - height) / total)
            add = 0.0
            for line in lines:
                line.top += add
                if line.brk in kinds:
                    add += to_add * line.height
            height += add
    dy = {"middle": (avail_h - height) / 2, "bottom": avail_h - height}.get(layer.alignment.vertical, 0)
    for line in lines:
        line.top += dy
        left, right = _row_edges(layer, line.top, line.height)
        width = line.width * result.stretch
        line.left = {"center": left + (right - left - width) / 2,
                     "right": right - width}.get(layer.alignment.horizontal, left)
        x, line.xs = line.left, []
        for item in line.items:
            line.xs.append(x)
            x += item.width * result.stretch
    return result


# ------------------------------------------------------------------- drawing

def _rgba(c: tuple) -> tuple:
    return tuple(int(v) for v in c) if len(c) == 4 else (*[int(v) for v in c], 255)


def _blur(alpha: np.ndarray) -> np.ndarray:
    """MSE's blur_image_alpha: the centre twice plus the four neighbours, over six."""
    p = np.pad(alpha.astype(np.int32), 1, mode="edge")
    return ((2 * p[1:-1, 1:-1] + p[1:-1, :-2] + p[:-2, 1:-1] + p[1:-1, 2:] + p[2:, 1:-1]) // 6
            ).astype(np.uint8)


class Ink:
    """Text drawn as MSE does: masks at TEXT_SCALING times the size, one per (color,
    blur), averaged down and painted in the order they were first used."""

    def __init__(self, width: int, height: int):
        self.size = (width * TEXT_SCALING, height * TEXT_SCALING)
        self.masks: dict[tuple, tuple[Image.Image, ImageDraw.ImageDraw]] = {}

    def text(self, x: float, y: float, text: str, lf: LoadedFont, color: tuple, blur: int = 0,
             stroke: int = 0) -> None:
        """`text` with its cell's top left at (x, y) in pixels, snapped to the fine grid."""
        key = (color, blur)
        if key not in self.masks:
            mask = Image.new("L", self.size, 0)
            self.masks[key] = (mask, ImageDraw.Draw(mask))
        draw = self.masks[key][1]
        n = TEXT_SCALING
        x4, baseline = math.floor(x * n), math.floor(y * n) + lf.ascent
        if not lf.fake_bold:
            draw.text((x4, baseline), text, font=lf.font, anchor="ls", fill=255, stroke_width=stroke * n)
            return
        # no bold file: Windows overstrikes each glyph one pixel to the right and makes
        # its advance a pixel wider (at the 4x size)
        for ch in text:
            for dx in (0, 1):
                draw.text((x4 + dx, baseline), ch, font=lf.font, anchor="ls", fill=255,
                          stroke_width=stroke * n)
            x4 += advance(lf, ch)

    def paint(self, out: Image.Image, width: int | None = None) -> None:
        """Onto `out` (1x); `width` squeezes the masks horizontally to that many pixels."""
        for (color, blur), (mask, _) in self.masks.items():
            alpha = downsample(mask, width)
            for _ in range(blur):
                alpha = _blur(alpha)
            alpha = (alpha.astype(np.int32) * color[3] // 255).astype(np.uint8)
            layer = Image.new("RGBA", (alpha.shape[1], alpha.shape[0]), color)
            layer.putalpha(Image.fromarray(alpha, "L"))
            out.alpha_composite(layer.crop((0, 0, out.width, out.height)))


def draw_text(layer: TextLayer, result: TextResult | None = None) -> Image.Image:
    """The layer drawn on a transparent image of the box's size, which goes at the box's
    rounded corner; text keeps the box's fractional position, as in MSE. Text too wide
    for its box runs on to the right (wider image), as in MSE."""
    result = result or layout_text(layer)
    w, h = max(1, math.ceil(layer.box.width)), max(1, math.ceil(layer.box.height))
    w = max([w] + [math.ceil(l.left + l.width * result.stretch) + 2 for l in result.lines])
    font = layer.font
    shadow = font.shadow_color[3] > 0 and (font.shadow_dx or font.shadow_dy)
    pad = 4                                     # room for shadow/stroke at the edges
    squeeze = result.stretch
    inv = 1.0 / squeeze
    canvas_w = math.ceil(w * inv) + 2 * pad
    ink = Ink(canvas_w, h + 2 * pad)
    ox = layer.box.left - round(layer.box.left) + pad
    oy = layer.box.top - round(layer.box.top) + pad
    stroke = round(font.stroke_radius * result.scale) if font.stroke_radius else 0
    symbols = []

    for line in result.lines:
        for item, x in zip(line.items, line.xs):
            piece = item.piece
            if piece.style.soft or piece.kind in ("space", "break"):
                continue
            if piece.kind == "symbol":
                # centred (by the symbol font's alignment) in its slot: as wide as the
                # symbol plus spacing, as high as the line
                if item.image is not None:
                    slot = Box(x + ox - pad * (1 - squeeze), line.top + oy,
                               item.width * result.stretch, line.height)
                    sx, sy = layer.symbol_font.alignment.place(item.image.size, slot)
                    symbols.append((item.image, round(sx), round(sy)))
                continue
            x = x * inv + ox                    # unsqueezed canvas; squeezed below
            y = line.top + oy
            if shadow:
                ink.text(x + font.shadow_dx, y + font.shadow_dy, piece.text, item.font,
                         _rgba(font.shadow_color), int(font.shadow_blur))
            if stroke:
                ink.text(x, y, piece.text, item.font, _rgba(font.stroke_color), stroke=stroke)
            ink.text(x, y, piece.text, item.font, _rgba(piece.style.color or font.color))

    out = Image.new("RGBA", (max(1, round(canvas_w * squeeze)), h + 2 * pad), (0, 0, 0, 0))
    ink.paint(out, out.width if squeeze != 1 else None)
    for image, x, y in symbols:
        out.paste(image, (x, y), image) if x < 0 or y < 0 else out.alpha_composite(image, (x, y))
    left_pad = round(pad * squeeze)
    return out.crop((left_pad, pad, left_pad + w, pad + h))
