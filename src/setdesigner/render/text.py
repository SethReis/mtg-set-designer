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
Font sizes are points drawn at 96/72 pixels per point, like MSE on Windows.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..mse.script.tokens import ESCAPED_LANGLE
from .fonts import LoadedFont, load_font
from .layout import FontSpec, TextLayer

PX_PER_PT = 96 / 72
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
    ascent: float
    descent: float
    font: LoadedFont | None = None
    image: Image.Image | None = None


class Measurer:
    """Fonts and symbol images for one layer at one scale."""

    def __init__(self, layer: TextLayer, scale: float):
        self.layer = layer
        self.scale = scale
        self._fonts: dict[tuple, LoadedFont] = {}

    def font_px(self, st: Style) -> float:
        size = st.size if st.size is not None else self.layer.font.size
        return size * self.scale * PX_PER_PT

    def font(self, st: Style) -> LoadedFont:
        spec = self.layer.font
        italic = st.italic or spec.italic
        name = st.font or (spec.italic_name if italic and spec.italic_name else spec.name)
        use_italic = italic and not (spec.italic_name and not st.font)
        key = (name, round(self.font_px(st), 2), st.bold or spec.bold, use_italic)
        if key not in self._fonts:
            self._fonts[key] = load_font(name, max(1, round(self.font_px(st))),
                                         st.bold or spec.bold, use_italic)
        return self._fonts[key]

    def measure(self, piece: Piece) -> Measured:
        if piece.kind == "symbol":
            sf = self.layer.symbol_font
            # MSE sizes symbols by the font size itself (no points -> pixels conversion)
            px = sf.size * self.scale if sf else self.font_px(piece.style)
            img = sf.provider.image(piece.symbol, px) if sf else None
            if img is None:
                return Measured(piece, 0, 0, 0)
            # symbols sit on the baseline region of the text around them
            ascent = img.height * 0.8
            return Measured(piece, img.width + (sf.spacing if sf else 0), ascent,
                            img.height - ascent, image=img)
        lf = self.font(piece.style)
        ascent, descent = lf.font.getmetrics()
        if piece.kind == "break":
            return Measured(piece, 0, ascent, descent, lf)
        return Measured(piece, lf.font.getlength(piece.text), ascent, descent, lf)


# ------------------------------------------------------------------- layout

@dataclass
class Line:
    items: list[Measured]
    top: float
    brk: str                            # how the line ended
    left: float = 0.0                   # x of the line's start (after alignment)
    xs: list[float] = field(default_factory=list)

    @property
    def ascent(self) -> float:
        return max((m.ascent for m in self.items), default=0.0)

    @property
    def descent(self) -> float:
        return max((m.descent for m in self.items), default=0.0)

    @property
    def height(self) -> float:
        return self.ascent + self.descent

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
            LINE: layer.line_height_line}[brk]


def layout_at(layer: TextLayer, pieces: list[Piece], scale: float) -> TextResult:
    m = Measurer(layer, scale)
    measured = [m.measure(p) for p in pieces]
    _, pt, _, pb = layer.padding
    lines: list[Line] = []
    top = pt
    current: list[Measured] = []
    prev_height = None

    def default_height() -> tuple[float, float]:
        lf = m.font(Style())
        a, d = lf.font.getmetrics()
        return a, d

    def end_line(brk: str) -> None:
        nonlocal top, current, prev_height
        line = Line(current, top, brk)
        if not current or line.height == 0:
            a, d = default_height()
            line.items = current + [Measured(Piece("break"), 0, a, d)]
        lines.append(line)
        prev_height = line.height
        top = line.top + line.height * _multiplier(layer, brk)
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
            continue
        j = i
        while j < len(measured) and measured[j].piece.kind in ("text", "symbol"):
            j += 1
        word = measured[i:j]
        word_w = sum(w.width for w in word)
        if layer.multi_line and current:
            line_w = sum(x.width for x in current)
            h = max([x.ascent + x.descent for x in current + word] or [0])
            left, right = _row_edges(layer, top, h)
            if line_w + word_w > right - left and any(x.piece.kind != "space" for x in current):
                while current and current[-1].piece.kind == "space":
                    current.pop()
                end_line(SOFT)
        current.extend(word)
        i = j
    end_line(HARD)
    # a trailing empty line only exists if the text ended with a break
    if len(lines) > 1 and not any(x.piece.kind in ("text", "symbol") for x in lines[-1].items) \
            and lines[-2].brk == HARD and not (pieces and pieces[-1].kind == "break"):
        lines.pop()

    avail_w = layer.box.width - layer.padding[0] - layer.padding[2]
    stretch = 1.0
    if not layer.multi_line and lines and lines[0].width > avail_w > 0:
        stretch = max(0.01, avail_w / lines[0].width)
    fits = (lines[-1].bottom <= layer.box.height - pb + 0.5) if lines else True
    if not layer.multi_line:
        fits = fits and stretch >= 1.0
    return TextResult(lines, scale, stretch, fits)


def min_scale(layer: TextLayer) -> float:
    font = layer.font
    smallest = 1.0
    if font.scale_down_to < font.size:
        smallest = font.scale_down_to / font.size
    sf = layer.symbol_font
    if sf is not None and sf.scale_down_to < sf.size:
        smallest = max(smallest, sf.scale_down_to / sf.size) if smallest < 1 else smallest
    return smallest


def layout_text(layer: TextLayer) -> TextResult:
    """Lay out with MSE's scale search: the largest scale (step ~1 point) that fits."""
    pieces = parse_tagged(layer.text, layer.symbol_font.provider if layer.symbol_font else None,
                          layer.always_symbol)
    lowest = min_scale(layer)
    first = layout_at(layer, pieces, 1.0)
    if first.fits or lowest >= 1.0:
        return _finish(layer, first)
    step = max(0.01, 1.0 / max(layer.font.size, 1.0))
    lo, hi = lowest, 1.0
    best = layout_at(layer, pieces, lo)
    if not best.fits:
        return _finish(layer, best)
    while lo + step < hi:
        mid = (lo + hi) / 2
        attempt = layout_at(layer, pieces, mid)
        if attempt.fits:
            lo, best = mid, attempt
        else:
            hi = mid
    return _finish(layer, best)


def _finish(layer: TextLayer, result: TextResult) -> TextResult:
    """Vertical then horizontal alignment."""
    lines = result.lines
    if not lines:
        return result
    pl, pt, pr, pb = layer.padding

    def empty(line: Line) -> bool:
        return not any(m.piece.kind in ("text", "symbol") and not m.piece.style.soft
                       for m in line.items)

    # MSE: an empty first line before a <line> break (no rules text, only flavor) takes
    # no room; trailing empty lines don't count when aligning vertically
    if len(lines) > 1 and empty(lines[0]) and lines[0].brk == LINE:
        shift = lines[1].top - lines[0].top
        lines.pop(0)
        for line in lines:
            line.top -= shift
    visible = lines
    while len(visible) > 1 and empty(visible[-1]):
        visible = visible[:-1]
    avail_h = layer.box.height - pt - pb
    height = visible[-1].bottom - visible[0].top
    # stretch gaps after hard/line breaks up to their *_max line heights
    extra = avail_h - height
    if extra > 0:
        gaps = []
        for n, line in enumerate(visible[:-1]):
            base = _multiplier(layer, line.brk)
            top_max = {SOFT: layer.line_height_soft_max, HARD: layer.line_height_hard_max,
                       LINE: layer.line_height_line_max}[line.brk]
            if top_max > base:
                gaps.append((n, (top_max - base) * line.height))
        total = sum(g for _, g in gaps)
        if total > 0:
            factor = min(1.0, extra / total)
            shift = 0.0
            for n, line in enumerate(lines):
                line.top += shift
                for gn, g in gaps:
                    if gn == n:
                        shift += g * factor
            height = visible[-1].bottom - visible[0].top
    dy = {"middle": (avail_h - height) / 2, "bottom": avail_h - height}.get(layer.alignment.vertical, 0)
    if layer.alignment.vertical != "top":
        dy = max(dy, 0) if result.fits else dy
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


def draw_text(layer: TextLayer, result: TextResult | None = None) -> Image.Image:
    """The layer drawn on a transparent image of the box's size."""
    result = result or layout_text(layer)
    w, h = max(1, math.ceil(layer.box.width)), max(1, math.ceil(layer.box.height))
    font = layer.font
    shadow = font.shadow_color[3] > 0 and (font.shadow_dx or font.shadow_dy)
    pad = 4                                     # room for shadow/stroke at the edges
    canvas_w = math.ceil(w / min(1.0, result.stretch)) + 2 * pad
    fill = Image.new("RGBA", (canvas_w, h + 2 * pad), (0, 0, 0, 0))
    shade = Image.new("RGBA", fill.size, (0, 0, 0, 0)) if shadow else None
    df, ds = ImageDraw.Draw(fill), ImageDraw.Draw(shade) if shadow else None
    inv = 1.0 / min(1.0, result.stretch)

    for line in result.lines:
        baseline = line.top + line.ascent + pad
        for item, x in zip(line.items, line.xs):
            x = x * inv + pad                   # unsqueezed canvas; squeezed below
            piece = item.piece
            if piece.style.soft or piece.kind in ("space", "break"):
                continue
            if piece.kind == "symbol":
                if item.image is not None:
                    y = round(baseline - item.ascent)
                    fill.alpha_composite(item.image, (round(x), y))
                continue
            color = _rgba(piece.style.color or font.color)
            stroke = round(font.stroke_radius * result.scale) if font.stroke_radius else 0
            # no bold file: overstrike 1 px to the right, as Windows does
            offsets = (0, 1) if item.font and item.font.fake_bold else (0,)
            kwargs = dict(font=item.font.font, anchor="ls")
            for dx in offsets:
                if shadow:
                    ds.text((x + dx + font.shadow_dx, baseline + font.shadow_dy), piece.text,
                            fill=_rgba(font.shadow_color), **kwargs)
                if stroke:
                    df.text((x + dx, baseline), piece.text, fill=color, stroke_width=stroke,
                            stroke_fill=_rgba(font.stroke_color), **kwargs)
                else:
                    df.text((x + dx, baseline), piece.text, fill=color, **kwargs)
    if shade is not None:
        if font.shadow_blur:
            shade = shade.filter(ImageFilter.GaussianBlur(font.shadow_blur))
        shade.alpha_composite(fill)
        fill = shade
    left_pad = pad
    if result.stretch < 1:                      # squeeze horizontally to fit
        fill = fill.resize((max(1, round(fill.width * result.stretch)), fill.height),
                           Image.Resampling.LANCZOS)
        left_pad = round(pad * result.stretch)
    return fill.crop((left_pad, pad, left_pad + w, pad + h))
