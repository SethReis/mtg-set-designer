"""The set symbol, drawn per rarity from the user's own SVG/PNG.

Only the symbol's *shape* (its alpha) is used: it is filled with the rarity's color
or gradient and given an outline, the way printed cards color expansion symbols.
    common      black, white outline
    uncommon    silver gradient
    rare        gold gradient
    mythic rare orange-red gradient
    special     purple gradient
    watermark   plain grey (used faded behind rules text)
Without a symbol file a rounded square is used. SVG files need the optional
`cairosvg` package; PNG works out of the box.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..mse.script import images as I
from ..mse.script.values import ScriptError

# variation -> (light color, dark color, outline color); a gradient runs light -> dark
VARIATIONS = {
    "common": ((20, 20, 20), (0, 0, 0), (255, 255, 255)),
    "invertedcommon": ((255, 255, 255), (230, 230, 230), (0, 0, 0)),
    "uncommon": ((225, 232, 240), (110, 125, 140), (0, 0, 0)),
    "rare": ((240, 215, 130), (150, 115, 40), (0, 0, 0)),
    "mythic rare": ((255, 180, 70), (200, 50, 25), (0, 0, 0)),
    "mythic": ((255, 180, 70), (200, 50, 25), (0, 0, 0)),
    "special": ((215, 160, 230), (110, 50, 140), (0, 0, 0)),
    "masterpiece": ((240, 190, 120), (150, 90, 40), (0, 0, 0)),
    "watermark": ((128, 128, 128), (128, 128, 128), None),
}
BASE_SIZE = 256                 # shapes are drawn at this size, then scaled


def ink(img: Image.Image) -> Image.Image:
    """Which pixels of an uploaded symbol are the symbol ("L", 255 = symbol).

    Symbols come as black art with white outlines or details (a ready-made common symbol),
    on a transparent, white or black background. The background is read from the
    image's border:
    - transparent: the dark opaque pixels are the symbol; white outlines and white inner
      details are gaps, drawn in each rarity's outline color (white lines of a common
      symbol become black on uncommon and up). An all-light symbol is taken as it is.
    - opaque and light: the dark pixels are the symbol (white is background);
    - opaque and dark: the light pixels are the symbol.
    Greys in between are soft edges (anti-aliasing); near-background noise (JPEG) drops out.
    """
    rgba = np.asarray(img.convert("RGBA"), np.float64) / 255
    alpha = rgba[..., 3]
    lum = (0.299 * rgba[..., 0] + 0.587 * rgba[..., 1] + 0.114 * rgba[..., 2])
    edge = np.concatenate([rgba[0], rgba[-1], rgba[:, 0], rgba[:, -1]])
    if np.median(edge[:, 3]) < 0.5:                           # transparent background
        dark = alpha * (1 - lum)
        # hardly any clearly dark pixels among the opaque ones: a light symbol, keep it all
        value = dark if (dark > 0.5).sum() > 0.05 * (alpha > 0.5).sum() else alpha
    else:
        edge_lum = 0.299 * edge[:, 0] + 0.587 * edge[:, 1] + 0.114 * edge[:, 2]
        value = (1 - lum) if np.median(edge_lum) >= 0.5 else lum
        value = value * alpha
    value = np.clip((value - 0.25) / 0.5, 0, 1)                 # firm up edges, drop noise
    return Image.fromarray((value * 255).astype(np.uint8), "L")


@lru_cache(maxsize=32)
def _shape(path: str, mtime: float) -> Image.Image:
    """The symbol's alpha shape ("L"), trimmed to its content, at BASE_SIZE."""
    p = Path(path)
    if p.suffix.lower() == ".svg":
        try:
            import cairosvg
        except ImportError:
            raise ScriptError("SVG set symbols need the 'cairosvg' package (or use a PNG)") from None
        import io
        png = cairosvg.svg2png(url=str(p), output_width=BASE_SIZE * 2)
        img = Image.open(io.BytesIO(png))
    else:
        img = Image.open(p)
    alpha = ink(img.convert("RGBA"))
    box = alpha.point(lambda v: 255 if v > 24 else 0).getbbox() or (0, 0, alpha.width, alpha.height)
    alpha = alpha.crop(box)
    scale = BASE_SIZE / max(alpha.size)
    return alpha.resize((max(1, round(alpha.width * scale)), max(1, round(alpha.height * scale))),
                        Image.Resampling.LANCZOS)


@lru_cache(maxsize=1)
def _default_shape() -> Image.Image:
    shape = Image.new("L", (BASE_SIZE, BASE_SIZE), 0)
    ImageDraw.Draw(shape).rounded_rectangle((16, 16, BASE_SIZE - 16, BASE_SIZE - 16), radius=24, fill=255)
    return shape


def symbol_image(path: str | None, variation: str, size: int | None = None) -> Image.Image:
    """The symbol for a rarity variation, as RGBA, `size` pixels on its longest side."""
    try:
        mtime = Path(path).stat().st_mtime if path else 0.0
    except OSError:
        path, mtime = None, 0.0
    return _symbol_image(path, mtime, variation, size).copy()


def _dilate(shape: Image.Image, radius: int) -> Image.Image:
    """Grow a shape by `radius` pixels in every direction with a round brush, so the
    outline keeps corners and holes round (a square max filter squares them off)."""
    a = np.asarray(shape, np.uint8)
    padded = np.pad(a, radius)
    out = a.copy()
    h, w = a.shape
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                np.maximum(out, padded[radius + dy:radius + dy + h, radius + dx:radius + dx + w], out=out)
    return Image.fromarray(out, "L")


@lru_cache(maxsize=128)
def _symbol_image(path: str | None, mtime: float, variation: str, size: int | None) -> Image.Image:
    shape = _shape(path, mtime) if path else _default_shape()
    light, dark, outline = VARIATIONS.get(variation, VARIATIONS["common"])
    pad = BASE_SIZE // 12
    canvas_size = (shape.width + 2 * pad, shape.height + 2 * pad)
    alpha = Image.new("L", canvas_size, 0)
    alpha.paste(shape, (pad, pad))
    # fill: diagonal gradient from light (top left) to dark (bottom right)
    h, w = canvas_size[1], canvas_size[0]
    t = (np.add.outer(np.arange(h), np.arange(w)) / max(1, h + w - 2))[..., None]
    fill = (np.array(light) * (1 - t) + np.array(dark) * t).astype(np.uint8)
    out = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    if outline is not None:
        grown = _dilate(alpha, pad // 2)
        ring = Image.new("RGBA", canvas_size, (*outline, 255))
        ring.putalpha(grown)
        out.alpha_composite(ring)
    body = Image.fromarray(fill, "RGB").convert("RGBA")
    body.putalpha(alpha)
    out.alpha_composite(body)
    out = out.crop(out.getbbox() or (0, 0, w, h))
    if size:
        scale = size / max(out.size)
        out = out.resize((max(1, round(out.width * scale)), max(1, round(out.height * scale))),
                         Image.Resampling.LANCZOS)
    return out


@dataclass
class RaritySymbol(I.GeneratedImage):
    """symbol_variation(symbol: set.symbol, variation: "rare") as an image recipe."""
    path: str | None
    variation: str

    def generate(self, opts: I.ImageOptions) -> I.Raster:
        size = max(opts.width, opts.height) or 64
        if not self.path and opts.height:           # the placeholder is drawn smaller
            size = round(opts.height * 0.65)
        img = symbol_image(self.path, self.variation, size)
        if opts.width and opts.height:              # fit inside the requested box
            scale = min(opts.width / img.width, opts.height / img.height, 1.0)
            if scale < 1:
                img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                                 Image.Resampling.LANCZOS)
        return I.Raster.from_pil(img)
