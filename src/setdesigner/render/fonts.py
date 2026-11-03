"""Find font files by the names stylesheets use ("Beleren Bold", "MPlantin",
"MPlantin-Italic", "Relay-Medium", ...) and load them at a pixel size.

Every .ttf/.otf under the fonts folder is indexed by its family name, family +
subfamily ("MPlantin Italic"), full name and PostScript name, case-insensitively.

Text is drawn the way MSE draws it (src/gfx/resample_text.cpp): glyphs at
TEXT_SCALING times the size, averaged down. Line heights use the fonts' Windows
metrics (OS/2 usWinAscent/usWinDescent), as Windows GDI does.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageFont

DEFAULT_FONTS = Path(__file__).resolve().parents[3] / "resources" / "fonts"
FALLBACK_NAMES = ("Times New Roman", "Arial")
TEXT_SCALING = 4                            # MSE draws text this much larger, then averages down


def scaled_px(points: float) -> int:
    """Em size in pixels at TEXT_SCALING of a font of `points` (MSE's toWxFont on Windows:
    -(int)(size * 96 / 72 + 0.5) pixels, with the size already times TEXT_SCALING)."""
    return max(1, int(points * TEXT_SCALING * 96 / 72 + 0.5))


@dataclass(frozen=True)
class FontFile:
    path: Path
    family: str
    subfamily: str

    @property
    def bold(self) -> bool:
        return "bold" in self.subfamily.lower()

    @property
    def italic(self) -> bool:
        sub = self.subfamily.lower()
        return "italic" in sub or "oblique" in sub


def _key(name: str) -> str:
    return "".join(name.lower().split()).replace("-", "").replace("_", "")


@lru_cache(maxsize=None)
def font_index(folder: Path = DEFAULT_FONTS) -> dict[str, list[FontFile]]:
    index: dict[str, list[FontFile]] = {}
    for path in sorted(folder.rglob("*")):
        if path.suffix.lower() not in (".ttf", ".otf"):
            continue
        try:
            font = TTFont(path, lazy=True, fontNumber=0)
            names = font["name"]
            get = lambda i: (names.getDebugName(i) or "").strip()
            family = get(16) or get(1)
            subfamily = get(17) or get(2) or "Regular"
            entry = FontFile(path, family, subfamily)
            for name in {get(1), family, f"{family} {subfamily}", f"{get(1)} {get(2)}", get(4), get(6)}:
                if name:
                    index.setdefault(_key(name), []).append(entry)
            font.close()
        except Exception:                       # unreadable font files are skipped
            continue
    return index


def find_font(name: str, bold: bool = False, italic: bool = False,
              folder: Path = DEFAULT_FONTS) -> FontFile | None:
    """The best file for a font name and style, or None."""
    index = font_index(folder)
    candidates = index.get(_key(name), [])
    if not candidates:
        return None

    def score(f: FontFile) -> tuple:
        return (f.bold == bold, f.italic == italic, f.subfamily.lower() in ("regular", "medium"))

    return max(candidates, key=score)


@dataclass(frozen=True)
class LoadedFont:
    font: ImageFont.FreeTypeFont
    fake_bold: bool                         # draw with a thin stroke (no bold file)
    fake_italic: bool                       # shear when drawing (no italic file)
    missing: bool                           # name not found; a fallback is used
    ascent: int = 0                         # pixels above / below the baseline at the loaded
    descent: int = 0                        # size, as Windows measures them


@lru_cache(maxsize=None)
def _win_metrics(path: Path) -> tuple[int, int, int] | None:
    """(usWinAscent, usWinDescent, units per em): what GDI's line height is made of."""
    try:
        font = TTFont(path, lazy=True, fontNumber=0)
        os2, upm = font["OS/2"], font["head"].unitsPerEm
        return os2.usWinAscent, os2.usWinDescent, upm
    except Exception:
        return None


@lru_cache(maxsize=512)
def load_font(name: str, px: int, bold: bool = False, italic: bool = False,
              folder: Path = DEFAULT_FONTS) -> LoadedFont:
    """A FreeType font at `px` pixels (em size), choosing bold/italic files when they exist."""
    px = max(1, px)
    found = find_font(name, bold, italic, folder)
    missing = found is None
    if found is None:
        for fallback in FALLBACK_NAMES:
            found = find_font(fallback, bold, italic, folder)
            if found:
                break
    if found is None:
        font = ImageFont.load_default(px)
        return LoadedFont(font, False, False, True, *font.getmetrics())
    font = ImageFont.truetype(str(found.path), px)
    win = _win_metrics(found.path)
    ascent, descent = font.getmetrics()
    if win is not None:
        ascent, descent = round(win[0] * px / win[2]), round(win[1] * px / win[2])
    return LoadedFont(font, bold and not found.bold, italic and not found.italic, missing,
                      ascent, descent)


def advance(font: LoadedFont, text: str) -> float:
    """Width of `text` in pixels at the loaded size, as Windows measures it: no kerning
    (no `kern` features are applied), and simulated bold widens every glyph by a pixel."""
    return font.font.getlength(text) + (len(text) if font.fake_bold else 0)


def downsample(mask: Image.Image, width: int | None = None) -> np.ndarray:
    """A grey mask drawn at TEXT_SCALING times the size, averaged down to 1x (MSE's
    downsample_to_alpha). With `width` (squeezed text) the columns are resampled to that
    width and made bolder to make up for it, as MSE does."""
    a = np.asarray(mask, dtype=np.int32)
    h4, w4 = a.shape
    n = TEXT_SCALING
    if width is None or width * n == w4:
        a = a[:, :w4 - w4 % n].reshape(h4, -1, n).sum(axis=2) // n
    else:
        squeezed = mask.resize((max(1, width), h4), Image.Resampling.BOX)
        mul = 128 + min(256, 128 * w4 // (n * max(1, width)))
        a = np.asarray(squeezed, dtype=np.int32) * mul >> 8
    a = a[:h4 - h4 % n].reshape(-1, n, a.shape[1]).sum(axis=1) // n
    return np.clip(a, 0, 255).astype(np.uint8)
