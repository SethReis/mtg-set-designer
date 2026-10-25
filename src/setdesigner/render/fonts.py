"""Find font files by the names stylesheets use ("Beleren Bold", "MPlantin",
"MPlantin-Italic", "Relay-Medium", ...) and load them at a pixel size.

Every .ttf/.otf under the fonts folder is indexed by its family name, family +
subfamily ("MPlantin Italic"), full name and PostScript name, case-insensitively.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import ImageFont

DEFAULT_FONTS = Path(__file__).resolve().parents[3] / "resources" / "fonts"
FALLBACK_NAMES = ("Times New Roman", "Arial")


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
        return LoadedFont(ImageFont.load_default(px), False, False, True)
    font = ImageFont.truetype(str(found.path), px)
    return LoadedFont(font, bold and not found.bold, italic and not found.italic, missing)
