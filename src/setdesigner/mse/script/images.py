"""Image values: MSE's "generated images".

An image in a script is not pixels but a recipe (a GeneratedImage), e.g.
    masked_blend(light: "a.png", dark: "b.png", mask: "m.png")
It is turned into pixels later, when the renderer asks for it at a size:
    image.generate_conform(ImageOptions(width=375, height=523, package=...))

Pixels are a Raster: RGB plus an optional alpha channel, like MSE's wxImage
(whether an image *has* alpha matters to some formulas). The formulas are MSE's
own integer arithmetic (src/gfx/*.cpp in MagicSetEditor2), written with numpy.

File names: "x.png" is in the current stylesheet package, "/pkg.mse-include/x.png"
in another package. `import_image` takes a filesystem path; "<mse>/data/pkg/x.png"
(from get_mse_path()) means a package file too.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from .values import Color, ScriptError

DEFAULT_ROOT = Path(__file__).resolve().parents[4] / "resources" / "mse_packages"
MSE_PATH = "<mse>"          # what get_mse_path() returns; "<mse>/data/x" = package root / x


# ------------------------------------------------------------------ rasters

@dataclass
class Raster:
    rgb: np.ndarray                     # (h, w, 3) uint8
    alpha: np.ndarray | None = None     # (h, w) uint8, or None = no alpha (opaque)

    @property
    def width(self) -> int:
        return self.rgb.shape[1]

    @property
    def height(self) -> int:
        return self.rgb.shape[0]

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height

    def copy(self) -> "Raster":
        return Raster(self.rgb.copy(), None if self.alpha is None else self.alpha.copy())

    def alpha_or_opaque(self) -> np.ndarray:
        return self.alpha if self.alpha is not None else np.full(self.rgb.shape[:2], 255, np.uint8)

    def to_pil(self) -> Image.Image:
        if self.alpha is None:
            return Image.fromarray(self.rgb, "RGB")
        return Image.fromarray(np.dstack([self.rgb, self.alpha]), "RGBA")

    @classmethod
    def from_pil(cls, img: Image.Image) -> "Raster":
        if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
            data = np.asarray(img.convert("RGBA"))
            return cls(data[..., :3].copy(), data[..., 3].copy())
        return cls(np.asarray(img.convert("RGB")).copy())

    @classmethod
    def blank(cls, width: int, height: int) -> "Raster":
        w, h = max(1, width), max(1, height)
        return cls(np.zeros((h, w, 3), np.uint8), np.zeros((h, w), np.uint8))

    def resized(self, width: int, height: int) -> "Raster":
        # MSE has its own resampler; Pillow's Hamming filter came closest in the
        # oracle comparisons (tests/script/test_image_oracle.py).
        if (width, height) == self.size:
            return self
        return Raster.from_pil(self.to_pil().resize((max(1, width), max(1, height)),
                                                    Image.Resampling.HAMMING))


# ------------------------------------------------------------------- options

@dataclass(frozen=True)
class ImageOptions:
    width: int = 0                      # 0 = natural size (or keep aspect if the other is set)
    height: int = 0
    preserve_aspect: str = "stretch"    # "stretch", "fit" or "border"
    root: Path = DEFAULT_ROOT           # folder with all packages
    package: Path | None = None         # current package folder (the stylesheet)
    local_dir: Path | None = None       # the set's own files (art, symbol)

    def sized(self, width: int, height: int) -> "ImageOptions":
        return replace(self, width=width, height=height)


def resolve_file(name: str, opts: ImageOptions) -> Path:
    """A package file name as MSE resolves it."""
    if name.startswith(MSE_PATH + "/data/"):
        return opts.root / name[len(MSE_PATH + "/data/"):]
    if name.startswith("/"):
        return opts.root / name.lstrip("/")
    if opts.package is None:
        raise ScriptError(f"File not found: '{name}' (no package)")
    return opts.package / name


def file_exists(name: str, opts: ImageOptions) -> bool:
    try:
        return resolve_file(name, opts).is_file()
    except ScriptError:
        return False


@lru_cache(maxsize=256)
def _load(path: str, mtime: float) -> Raster:
    with Image.open(path) as img:
        return Raster.from_pil(img)


def load_raster(path: Path) -> Raster:
    if not path.is_file():
        raise ScriptError(f"File not found: '{path}'")
    return _load(str(path), path.stat().st_mtime).copy()


def conform(img: Raster, opts: ImageOptions) -> Raster:
    """Fit an image to the requested size, like MSE's conform_image."""
    w, h = opts.width, opts.height
    iw, ih = img.size
    if (w, h) == (iw, ih) or (w <= 0 and h <= 0):
        return img
    if h <= 0:
        h = max(1, w * ih // iw)
    elif w <= 0:
        w = max(1, h * iw // ih)
    if opts.preserve_aspect == "fit":
        scale = min(w / iw, h / ih)
        return img.resized(max(1, int(iw * scale)), max(1, int(ih * scale)))
    return img.resized(w, h)


# ----------------------------------------------------------------- generators

@dataclass
class GeneratedImage:
    """Base class. `combine` is how the image is drawn over what is below it."""
    type_label = "image"

    def generate(self, opts: ImageOptions) -> Raster:
        raise NotImplementedError

    def generate_conform(self, opts: ImageOptions) -> Raster:
        return conform(self.generate(opts), opts)

    @property
    def combine(self) -> str | None:
        return None


@dataclass
class BlankImage(GeneratedImage):
    def generate(self, opts: ImageOptions) -> Raster:
        w = opts.width if opts.width > 0 else opts.height
        h = opts.height if opts.height > 0 else opts.width
        return Raster.blank(w, h)


@dataclass
class PackagedImage(GeneratedImage):
    """A file in a package (a string used as an image)."""
    name: str

    def generate(self, opts: ImageOptions) -> Raster:
        return load_raster(resolve_file(self.name, opts))


@dataclass
class ImportedImage(GeneratedImage):
    """import_image(path): a file anywhere on disk (or "<mse>/data/..." = a package file)."""
    path: str

    def generate(self, opts: ImageOptions) -> Raster:
        if self.path.startswith(MSE_PATH + "/"):
            return load_raster(resolve_file(self.path, opts))
        return load_raster(Path(self.path))


def _same_size(img: Raster, other: Raster) -> Raster:
    # MSE requires equal sizes here and fails otherwise; we resample instead.
    return other.resized(*img.size)


@dataclass
class LinearBlend(GeneratedImage):
    image1: GeneratedImage
    image2: GeneratedImage
    x1: float
    y1: float
    x2: float
    y2: float

    def generate(self, opts: ImageOptions) -> Raster:
        img = self.image1.generate(opts)
        other = _same_size(img, self.image2.generate(opts))
        w, h = img.size
        dx, dy = (self.x2 - self.x1) * w, (self.y2 - self.y1) * h
        length2 = dx * dx + dy * dy
        if length2 == 0:
            raise ScriptError("linear_blend: the two points are the same")
        xs = np.arange(w)[None, :] - self.x1 * w
        ys = np.arange(h)[:, None] - self.y1 * h
        t = np.clip((xs * dx + ys * dy) / length2, 0, 1)[..., None]
        a, b = img.rgb.astype(np.int32), other.rgb.astype(np.int32)
        return Raster((a + t * (b - a)).astype(np.uint8), img.alpha)


@dataclass
class MaskedBlend(GeneratedImage):
    """White in the mask shows `light`, black shows `dark` (per channel)."""
    light: GeneratedImage
    dark: GeneratedImage
    mask: GeneratedImage

    def generate(self, opts: ImageOptions) -> Raster:
        img = self.light.generate(opts)
        dark = _same_size(img, self.dark.generate(opts)).rgb.astype(np.int32)
        mask = _same_size(img, self.mask.generate(opts)).rgb.astype(np.int32)
        light = img.rgb.astype(np.int32)
        return Raster(((light * mask + dark * (255 - mask)) // 255).astype(np.uint8), img.alpha)


def _overlay(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.where(a < 128, (a * b) >> 7, 255 - (((255 - a) * (255 - b)) >> 7))


def _safe_div(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    return num // np.where(den == 0, 1, den)


COMBINE_MODES = {
    "normal": lambda a, b: b,
    "add": lambda a, b: a + b,
    "subtract": lambda a, b: a - b,
    "stamp": lambda a, b: a - 2 * b + 256,
    "difference": lambda a, b: np.abs(a - b),
    "negation": lambda a, b: 255 - np.abs(255 - a - b),
    "multiply": lambda a, b: (a * b) // 255,
    "darken": np.minimum,
    "lighten": np.maximum,
    "color dodge": lambda a, b: np.where(b == 255, 255, _safe_div(a * 255, 255 - b)),
    "color burn": lambda a, b: np.where(b == 0, 0, 255 - _safe_div((255 - a) * 255, b)),
    "screen": lambda a, b: 255 - ((255 - a) * (255 - b)) // 255,
    "overlay": _overlay,
    "hard light": lambda a, b: _overlay(b, a),
    "soft light": lambda a, b: b,               # sic: MSE's soft light is just b
    "reflect": lambda a, b: np.where(b == 255, 255, _safe_div(a * a, 255 - b)),
    "glow": lambda a, b: np.where(a == 255, 255, _safe_div(b * b, 255 - a)),
    "freeze": lambda a, b: np.where(b == 0, 0, 255 - _safe_div((255 - a) * (255 - a), b)),
    "heat": lambda a, b: np.where(a == 0, 0, 255 - _safe_div((255 - b) * (255 - b), a)),
    "and": lambda a, b: a & b,
    "or": lambda a, b: a | b,
    "xor": lambda a, b: a ^ b,
    "shadow": lambda a, b: (b * a * a) // (255 * 255),
    "symmetric overlay": lambda a, b: (_overlay(a, b) + _overlay(b, a)) // 2,
    # MSE 2.6 (transform symbols): b is a light map around grey 128 (formula found
    # by matching real MSE output exactly, see tools/oracle_cases/images.txt)
    "lightmap relative": lambda a, b: np.where(b < 128, a * b // 128, a + (255 - a) * (b - 128) // 128),
}


def combine_rgb(a: np.ndarray, b: np.ndarray, mode: str) -> np.ndarray:
    if mode not in COMBINE_MODES:
        raise ScriptError(f"Unknown combine mode '{mode}'")
    out = COMBINE_MODES[mode](a.astype(np.int32), b.astype(np.int32))
    return np.clip(out, 0, 255).astype(np.uint8)


@dataclass
class CombineBlend(GeneratedImage):
    image1: GeneratedImage
    image2: GeneratedImage
    mode: str

    def generate(self, opts: ImageOptions) -> Raster:
        img = self.image1.generate(opts)
        other = _same_size(img, self.image2.generate(opts))
        alpha = other.alpha if other.alpha is not None else img.alpha
        return Raster(combine_rgb(img.rgb, other.rgb, self.mode), alpha)


def multiply_alpha(img: Raster, alpha: np.ndarray) -> Raster:
    """MSE's set_alpha: multiply the existing alpha (or set it if there is none)."""
    if img.alpha is None:
        return Raster(img.rgb, alpha.astype(np.uint8))
    return Raster(img.rgb, (img.alpha.astype(np.int32) * alpha // 255).astype(np.uint8))


@dataclass
class SetMask(GeneratedImage):
    image: GeneratedImage
    mask: GeneratedImage

    def generate(self, opts: ImageOptions) -> Raster:
        img = self.image.generate(opts)
        mask = self.mask.generate(opts).resized(*img.size)
        return multiply_alpha(img, mask.rgb[..., 0].astype(np.int32))

    @property
    def combine(self) -> str | None:
        return self.image.combine


@dataclass
class SetAlpha(GeneratedImage):
    input: GeneratedImage
    alpha: float

    def generate(self, opts: ImageOptions) -> Raster:
        img = self.input.generate(opts)
        value = np.full(img.rgb.shape[:2], int(self.alpha * 255), np.int32)
        return multiply_alpha(img, value)

    @property
    def combine(self) -> str | None:
        return self.input.combine


@dataclass
class SetCombine(GeneratedImage):
    """Only changes how the image is drawn onto the card (e.g. "shadow")."""
    input: GeneratedImage
    mode: str

    def generate(self, opts: ImageOptions) -> Raster:
        return self.input.generate(opts)

    @property
    def combine(self) -> str | None:
        return self.mode


@dataclass
class Saturate(GeneratedImage):
    input: GeneratedImage
    amount: float

    def generate(self, opts: ImageOptions) -> Raster:
        img = self.input.generate(opts)
        factor = int(256 * self.amount)
        if factor == 0:
            return img
        c = img.rgb.astype(np.int32)
        r, g, b = c[..., 0], c[..., 1], c[..., 2]
        if factor == 256:
            out = np.stack([np.where(r + r > g + b, 255, 0), np.where(g + g > b + r, 255, 0),
                            np.where(b + b > r + g, 255, 0)], -1)
        elif factor > 0:
            avg = (factor * (r + g + b))[..., None]
            out = np.clip((768 * c - avg) // (768 - 3 * factor), 0, 255)
        else:
            f1 = -factor
            avg = (f1 * (r + g + b))[..., None]
            out = ((768 - 3 * f1) * c + avg) // 768
        return Raster(out.astype(np.uint8), img.alpha)


@dataclass
class Invert(GeneratedImage):
    input: GeneratedImage

    def generate(self, opts: ImageOptions) -> Raster:
        img = self.input.generate(opts)
        return Raster(255 - img.rgb, img.alpha)


def grayscale(c: Color) -> int:
    return (6969 * c.r + 23434 * c.g + 2365 * c.b) // 32768


def recolor_rgb(rgb: np.ndarray, red: Color, green: Color, blue: Color, white: Color) -> np.ndarray:
    """Each pixel = its red, green, blue and white parts mixed from four colors."""
    c = rgb.astype(np.int32)
    lo = c.min(axis=-1)
    nr, ng, nb, nw = c[..., 0] - lo, c[..., 1] - lo, c[..., 2] - lo, lo
    total = np.maximum(255, nr + ng + nb + nw)
    out = [(nr * red.rgb[i] + ng * green.rgb[i] + nb * blue.rgb[i] + nw * white.rgb[i]) // total
           for i in range(3)]
    return np.stack(out, -1).astype(np.uint8)


@dataclass
class Recolor(GeneratedImage):
    """recolor_image(color): red parts become `color`; green/blue become black or
    white depending on whether the color is dark."""
    input: GeneratedImage
    color: Color

    def generate(self, opts: ImageOptions) -> Raster:
        img = self.input.generate(opts)
        black, white = Color(0, 0, 0), Color(255, 255, 255)
        dark = grayscale(self.color) < 100
        return Raster(recolor_rgb(img.rgb, self.color, black if dark else white,
                                  white if dark else black, white), img.alpha)


@dataclass
class Recolor4(GeneratedImage):
    input: GeneratedImage
    red: Color
    green: Color
    blue: Color
    white: Color = field(default_factory=lambda: Color(255, 255, 255))

    def generate(self, opts: ImageOptions) -> Raster:
        img = self.input.generate(opts)
        return Raster(recolor_rgb(img.rgb, self.red, self.green, self.blue, self.white), img.alpha)


@dataclass
class Flip(GeneratedImage):
    input: GeneratedImage
    horizontal: bool

    def generate(self, opts: ImageOptions) -> Raster:
        img = self.input.generate(opts)
        axis = 1 if self.horizontal else 0
        return Raster(np.flip(img.rgb, axis).copy(),
                      None if img.alpha is None else np.flip(img.alpha, axis).copy())


@dataclass
class Rotate(GeneratedImage):
    input: GeneratedImage
    degrees: float

    def generate(self, opts: ImageOptions) -> Raster:
        img = self.input.generate(opts)
        turns = (self.degrees / 90) % 4
        if turns == int(turns):
            k = int(turns)
            return Raster(np.rot90(img.rgb, k).copy(),
                          None if img.alpha is None else np.rot90(img.alpha, k).copy())
        rotated = img.to_pil().convert("RGBA").rotate(self.degrees, Image.Resampling.BILINEAR, expand=True)
        return Raster.from_pil(rotated)


@dataclass
class Enlarge(GeneratedImage):
    """A transparent border of `border_size` (a fraction of the size) on each side."""
    input: GeneratedImage
    border_size: float

    def generate(self, opts: ImageOptions) -> Raster:
        b = self.border_size
        inner_opts = opts.sized(int(opts.width * (1 - 2 * b)) if b < 0.5 else 0,
                                int(opts.height * (1 - 2 * b)) if b < 0.5 else 0)
        img = self.input.generate_conform(inner_opts) if opts.width or opts.height \
            else self.input.generate(inner_opts)
        w, h = img.size
        dw, dh = int(w * b), int(h * b)
        out = Raster.blank(w + 2 * dw, h + 2 * dh)
        out.rgb[dh:dh + h, dw:dw + w] = img.rgb
        out.alpha[dh:dh + h, dw:dw + w] = img.alpha_or_opaque()
        return out


def place(img: Raster, width: int, height: int, x: int, y: int,
          background: Color | None = None) -> Raster:
    """A width x height canvas with img's top-left corner at (x, y); the rest is
    transparent (or `background`)."""
    out = Raster.blank(width, height)
    if background is not None:
        out.rgb[...] = background.rgb
        out.alpha[...] = background.a
    sx0, sy0 = max(0, -x), max(0, -y)
    dx0, dy0 = max(0, x), max(0, y)
    w = min(img.width - sx0, out.width - dx0)
    h = min(img.height - sy0, out.height - dy0)
    if w > 0 and h > 0:
        out.rgb[dy0:dy0 + h, dx0:dx0 + w] = img.rgb[sy0:sy0 + h, sx0:sx0 + w]
        out.alpha[dy0:dy0 + h, dx0:dx0 + w] = img.alpha_or_opaque()[sy0:sy0 + h, sx0:sx0 + w]
    if img.alpha is None and background is None and (w, h) == out.size:
        out.alpha = None
    return out


@dataclass
class Crop(GeneratedImage):
    """crop: width x height pixels starting at (offset_x, offset_y)."""
    input: GeneratedImage
    width: int
    height: int
    offset_x: float
    offset_y: float
    background: Color | None = None

    def generate(self, opts: ImageOptions) -> Raster:
        img = self.input.generate(opts)
        return place(img, self.width, self.height, -int(self.offset_x), -int(self.offset_y),
                     self.background)


def _blur_axis(values: np.ndarray, sigma: float, axis: int) -> np.ndarray:
    """Gaussian blur along one axis (zero outside the image)."""
    if sigma <= 0:
        return values
    radius = max(1, int(math.ceil(3 * sigma)))
    xs = np.arange(-radius, radius + 1)
    kernel = np.exp(-(xs * xs) / (2 * sigma * sigma))
    kernel /= kernel.sum()
    return np.apply_along_axis(lambda row: np.convolve(row, kernel, mode="same"), axis, values)


def _shadow(img: Raster, offset_x: float, offset_y: float, alpha: float, blur_radius: float,
            color: Color) -> Raster:
    """MSE's drop shadow: the image's alpha, blurred, offset and colored, behind it."""
    if img.alpha is None:
        return img
    w, h = img.size
    dw, dh = int(w * offset_x), int(h * offset_y)
    shadow = img.alpha.astype(np.float64)
    if blur_radius > 0:     # sigma is a fraction of the width / height respectively
        shadow = _blur_axis(_blur_axis(shadow, blur_radius * w, 1), blur_radius * h, 0)
    shadow = np.clip(np.rint(shadow), 0, 255).astype(np.uint8)
    shifted = place(Raster(np.zeros((h, w, 3), np.uint8), shadow), w, h, dw, dh)
    shad = shifted.alpha.astype(np.int32) * int(alpha * 255) // 255
    a = img.alpha.astype(np.int32)
    out_alpha = a + shad * (255 - a) // 255
    # colour where the image is (partly) transparent comes from the shadow color
    weight = np.where(out_alpha == 0, 0, a * 255 // np.maximum(out_alpha, 1))[..., None]
    rgb = (img.rgb.astype(np.int32) * weight + np.array(color.rgb) * (255 - weight)) // 255
    return Raster(rgb.astype(np.uint8), out_alpha.astype(np.uint8))


@dataclass
class DropShadow(GeneratedImage):
    input: GeneratedImage
    offset_x: float = 0.0
    offset_y: float = 0.0
    alpha: float = 1.0
    blur_radius: float = 0.0
    color: Color = field(default_factory=lambda: Color(0, 0, 0))

    def generate(self, opts: ImageOptions) -> Raster:
        return _shadow(self.input.generate(opts), self.offset_x, self.offset_y, self.alpha,
                       self.blur_radius, self.color)


# ------------------------------------------------- MSE 2.6 additions

@dataclass
class Resize(GeneratedImage):
    input: GeneratedImage
    width: int
    height: int

    def generate(self, opts: ImageOptions) -> Raster:
        return self.input.generate(opts).resized(self.width, self.height)


@dataclass
class Insert(GeneratedImage):
    """insert_image: draw `inserted_image` over `base_image` at (offset_x, offset_y)
    pixels; the canvas grows to fit it (as MSE does)."""
    base_image: GeneratedImage
    inserted_image: GeneratedImage
    offset_x: float = 0.0
    offset_y: float = 0.0

    def generate(self, opts: ImageOptions) -> Raster:
        base = self.base_image.generate(opts)
        inserted = self.inserted_image.generate(opts)
        x, y = int(self.offset_x), int(self.offset_y)
        width = max(base.width, x + inserted.width)
        height = max(base.height, y + inserted.height)
        canvas = place(base, width, height, 0, 0)
        return alpha_composite(canvas, place(inserted, width, height, x, y))


def alpha_composite(base: Raster, top: Raster) -> Raster:
    """`top` drawn over `base` (same size), standard "over" compositing."""
    ta = top.alpha_or_opaque().astype(np.int32)[..., None]
    ba = base.alpha_or_opaque().astype(np.int32)[..., None]
    out_a = ta + ba * (255 - ta) // 255
    num = top.rgb.astype(np.int32) * ta + base.rgb.astype(np.int32) * ba * (255 - ta) // 255
    rgb = np.where(out_a == 0, 0, num // np.maximum(out_a, 1))
    alpha = None if base.alpha is None and top.alpha is None else out_a[..., 0].astype(np.uint8)
    return Raster(rgb.astype(np.uint8), alpha)


@dataclass
class Fill(GeneratedImage):
    """fill_image: every pixel becomes `color`, keeping the alpha (the image's shape)."""
    input: GeneratedImage
    color: Color

    def generate(self, opts: ImageOptions) -> Raster:
        img = self.input.generate(opts)
        rgb = np.empty_like(img.rgb)
        rgb[...] = self.color.rgb
        return Raster(rgb, img.alpha)


@dataclass
class NineSlice(GeneratedImage):
    """nine_slice_image: stretch to width x height keeping the borders (pixels) unscaled."""
    input: GeneratedImage
    width: int
    height: int
    top: int = 0
    bottom: int = 0
    left: int = 0
    right: int = 0

    def generate(self, opts: ImageOptions) -> Raster:
        img = self.input.generate(opts)
        out = Raster.blank(self.width, self.height)
        if img.alpha is None:
            out.alpha = None
        xs = self._cuts(img.width, self.width, self.left, self.right)
        ys = self._cuts(img.height, self.height, self.top, self.bottom)
        for (sy0, sy1, dy0, dy1) in ys:
            for (sx0, sx1, dx0, dx1) in xs:
                if sx1 <= sx0 or sy1 <= sy0 or dx1 <= dx0 or dy1 <= dy0:
                    continue
                part = Raster(img.rgb[sy0:sy1, sx0:sx1],
                              None if img.alpha is None else img.alpha[sy0:sy1, sx0:sx1])
                part = part.resized(dx1 - dx0, dy1 - dy0)
                out.rgb[dy0:dy1, dx0:dx1] = part.rgb
                if out.alpha is not None:
                    out.alpha[dy0:dy1, dx0:dx1] = part.alpha_or_opaque()
        return out

    @staticmethod
    def _cuts(src: int, dst: int, start: int, end: int) -> list[tuple[int, int, int, int]]:
        start, end = int(start), int(end)
        return [(0, start, 0, start), (start, src - end, start, dst - end),
                (src - end, src, dst - end, dst)]


# ------------------------------------------------------------- conversion

def as_image(value: object) -> GeneratedImage:
    """A script value used as an image: images as is, text = a package file name."""
    from .values import ErrorValue, check, type_name
    check(value)
    if isinstance(value, GeneratedImage):
        return value
    if isinstance(value, str):
        return PackagedImage(value)
    if value is None:
        return BlankImage()
    if hasattr(value, "to_image"):                  # e.g. image field values
        return value.to_image()
    raise ScriptError(f"Can't convert from {type_name(value)} to image")
