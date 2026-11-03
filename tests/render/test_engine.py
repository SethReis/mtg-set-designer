"""The drawing engine and its parts, on synthetic inputs (no MSE needed except where
marked)."""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from setdesigner.render.fonts import find_font
from setdesigner.render.layout import Alignment, Box, FontSpec, TextLayer
from setdesigner.render.symbol import symbol_image
from setdesigner.render.text import HARD, LINE, SOFT, draw_text, layout_text, parse_tagged

PACKAGES = Path(__file__).resolve().parents[2] / "resources" / "mse_packages"
FONTS = Path(__file__).resolve().parents[2] / "resources" / "fonts"
needs_fonts = pytest.mark.skipif(not FONTS.is_dir(), reason="resources/fonts not populated")


def layer(text, width=200, height=100, size=12, multi_line=True, **kw) -> TextLayer:
    return TextLayer(Box(0, 0, width, height), text, FontSpec("MPlantin", size, **kw.pop("font", {})),
                     multi_line=multi_line, **kw)


# ------------------------------------------------------------------ alignment

def test_alignment_parse_and_place() -> None:
    a = Alignment.parse("left bottom shrink-overflow")
    assert (a.horizontal, a.vertical, a.shrink_overflow) == ("left", "bottom", True)
    assert Alignment.parse("middle right").place((10, 10), Box(0, 0, 100, 50)) == (90, 20)
    assert Alignment.parse("stretch").horizontal == "stretch"


# ----------------------------------------------------------------- tag parsing

def test_tags_become_styled_pieces() -> None:
    pieces = parse_tagged("A <i-auto>(b c)</i-auto><soft> x</soft>\n<line>\n</line>d")
    words = [(p.kind, p.text, p.style.italic, p.style.soft) for p in pieces if p.kind != "break"]
    assert ("text", "A", False, False) in words and ("text", "(b", True, False) in words
    assert ("text", "x", False, True) in words
    assert [p.brk for p in pieces if p.kind == "break"] == [HARD, LINE]
    assert [p.brk for p in parse_tagged("a<soft-line>\n</soft-line>b") if p.kind == "break"] == [SOFT]


def test_escaped_angle_bracket_is_text() -> None:
    assert parse_tagged("a\x01b")[0].text == "a<b"


# ---------------------------------------------------------------- text layout

@needs_fonts
def test_wraps_and_breaks() -> None:
    result = layout_text(layer("one two three four five six seven eight", width=80))
    assert len(result.lines) > 2
    assert all(l.width <= 80 for l in result.lines)
    assert len(layout_text(layer("a\nb\nc")).lines) == 3


@needs_fonts
def test_shrinks_to_fit_down_to_scale_down_to() -> None:
    long = " ".join(["word"] * 80)
    fits = layout_text(layer(long, width=150, height=60, font={"scale_down_to": 4}))
    assert fits.scale < 1 and fits.fits
    stuck = layout_text(layer(long, width=150, height=60))      # no scale_down_to: no shrinking
    assert stuck.scale == 1 and not stuck.fits


@needs_fonts
def test_single_line_squeezes_instead_of_wrapping() -> None:
    shrink = Alignment.parse("left shrink-overflow")
    result = layout_text(layer("A very long card name indeed", width=60, multi_line=False, alignment=shrink))
    assert len(result.lines) == 1 and result.stretch < 1
    assert layout_text(layer("Short", width=60, multi_line=False, alignment=shrink)).stretch == 1
    # as in MSE, only "shrink"/"stretch" alignments squeeze; other text runs past the box
    plain = layout_text(layer("A very long card name indeed", width=60, multi_line=False))
    assert plain.stretch == 1 and plain.fits
    assert draw_text(layer("A very long card name indeed", width=60, multi_line=False)).width > 60


@needs_fonts
def test_text_is_measured_like_windows_gdi() -> None:
    from setdesigner.render.fonts import advance, load_font, scaled_px
    assert scaled_px(14) == 75                      # 14 pt at 4x: round(14 * 4 * 96 / 72)
    plantin = load_font("MPlantin", scaled_px(14))
    assert (plantin.ascent, plantin.descent) == (68, 20)      # OS/2 win metrics, not hhea
    one = layout_text(layer("x", size=14)).lines[0]
    assert one.height == 22                         # 88 / 4
    fake = load_font("Relay-Medium", 40, bold=True)             # no bold file
    assert fake.fake_bold and advance(fake, "ORC") == fake.font.getlength("ORC") + 3


@needs_fonts
def test_trailing_space_that_overflows_ends_the_line() -> None:
    # MSE counts a word's trailing space when checking the width: if only that space
    # doesn't fit, the line still ends there, and a following break gets a line of its own
    text = "aaa bbb"
    width = layout_text(layer(text, width=1000)).content_width
    fits = layout_text(layer(text + "\nc", width=width + 0.5))
    assert [len(fits.lines), fits.lines[0].brk] == [2, HARD]
    tight = layout_text(layer(text + " \nc", width=width + 0.5))
    assert [l.brk for l in tight.lines] == [SOFT, HARD, ""]


def test_downsample_averages_blocks() -> None:
    from setdesigner.render.fonts import downsample
    mask = Image.new("L", (8, 4), 0)
    mask.paste(255, (0, 0, 4, 2))                   # half of the first 4x4 block
    assert downsample(mask).tolist() == [[127, 0]]


@needs_fonts
def test_vertical_alignment() -> None:
    top = layout_text(layer("x", height=100))
    middle = layout_text(layer("x", height=100, alignment=Alignment("left", "middle")))
    assert middle.lines[0].top > top.lines[0].top + 30


@needs_fonts
def test_draws_ink_in_the_box() -> None:
    img = draw_text(layer("Hello", font={"color": (255, 0, 0, 255)}))
    alpha = np.asarray(img.getchannel("A"))
    assert img.size == (200, 100) and alpha.max() == 255
    ys, xs = np.nonzero(alpha)
    assert xs.min() < 10 and ys.max() < 30                          # top left


# ---------------------------------------------------------------------- fonts

@needs_fonts
def test_font_names_resolve_like_mse() -> None:
    assert find_font("Beleren Bold").path.name.startswith("beleren-bold")
    assert find_font("MPlantin-Italic").path.name == "mplantinit.ttf"      # a PostScript name
    assert find_font("No Such Font") is None


# ---------------------------------------------------------------- symbol font

@pytest.mark.skipif(not PACKAGES.is_dir(), reason="resources/mse_packages not populated")
def test_symbol_font_splitting_and_labels() -> None:
    from setdesigner.render.symbol_font import SymbolRenderer, load_symbol_font
    font = load_symbol_font(PACKAGES, "magic-mana-small.mse-symbol-font")
    renderer = SymbolRenderer(font, evaluate=lambda node: False, root=PACKAGES)  # scripts: "disabled"
    pieces = renderer.split("12WU")
    # with scripted symbols disabled, "12" is one generic (regex) symbol; W and U follow
    assert [p.text for p in pieces][:1] == ["12"] and pieces[0].symbol.is_regex
    assert len(pieces) >= 2


# --------------------------------------------------------------------- symbol

def test_rarity_symbol_colors() -> None:
    common = np.asarray(symbol_image(None, "common", 64).convert("RGBA"))
    center = common[common.shape[0] // 2, common.shape[1] // 2]
    edge = common[common.shape[0] // 2, 1]
    assert center[:3].max() < 40 and center[3] == 255              # black fill
    assert edge[:3].min() > 200                                     # white outline
    rare = np.asarray(symbol_image(None, "rare", 64).convert("RGB"))
    r, g, b = rare[32, 32]
    assert r > b + 40 and g > b                                     # gold


def test_symbol_from_png(tmp_path) -> None:
    shape = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    shape.paste((0, 0, 0, 255), (5, 5, 35, 15))
    path = tmp_path / "symbol.png"
    shape.save(path)
    img = symbol_image(str(path), "mythic rare", 60)
    assert img.width == 60 and img.height < 40                      # keeps its wide shape
