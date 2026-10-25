"""Image generators on tiny synthetic images; expected pixels follow MSE's formulas
(src/gfx/*.cpp in MagicSetEditor2). Real-MSE comparisons are in test_image_oracle.py."""
from dataclasses import dataclass

import numpy as np
import pytest

from setdesigner.mse.script import Context, run
from setdesigner.mse.script import images as I
from setdesigner.mse.script.builtins import builtin_variables
from setdesigner.mse.script.values import Color, to_code

OPTS = I.ImageOptions()


@dataclass
class Fixed(I.GeneratedImage):
    raster: I.Raster

    def generate(self, opts):
        return self.raster.copy()


def img(*pixels, alpha=None, width=None) -> Fixed:
    """A one-row image (or `width` columns) from (r, g, b) tuples."""
    rgb = np.array(pixels, np.uint8).reshape(-1, width or len(pixels), 3)
    a = None if alpha is None else np.array(alpha, np.uint8).reshape(rgb.shape[:2])
    return Fixed(I.Raster(rgb, a))


def px(gen: I.GeneratedImage) -> list:
    return gen.generate(OPTS).rgb.reshape(-1, 3).tolist()


# ----------------------------------------------------------------- blends

def test_masked_blend_white_shows_light() -> None:
    light, dark = img((200, 100, 0), (200, 100, 0)), img((0, 0, 0), (0, 0, 100))
    mask = img((255, 255, 255), (0, 128, 255))
    assert px(I.MaskedBlend(light, dark, mask)) == [[200, 100, 0], [0, 50, 0]]


def test_linear_blend_goes_from_image1_to_image2() -> None:
    a, b = img(*[(0, 0, 0)] * 5), img(*[(200, 200, 200)] * 5)
    row = [p[0] for p in px(I.LinearBlend(a, b, 0, 0, 1, 0))]
    assert row[0] == 0 and row == sorted(row) and row[-1] > 150


@pytest.mark.parametrize("mode, expected", [
    ("normal", 50), ("add", 250), ("subtract", 150), ("multiply", 200 * 50 // 255),
    ("screen", 255 - (55 * 205) // 255), ("darken", 50), ("lighten", 200),
    ("difference", 150), ("overlay", 255 - ((55 * 205) >> 7)),
    ("shadow", (50 * 200 * 200) // (255 * 255)), ("and", 200 & 50), ("xor", 200 ^ 50),
])
def test_combine_modes(mode, expected) -> None:
    out = px(I.CombineBlend(img((200, 200, 200)), img((50, 50, 50)), mode))
    assert out == [[expected] * 3]


def test_combine_takes_second_alpha_only_if_it_has_one() -> None:
    first = img((1, 1, 1), alpha=[100])
    assert I.CombineBlend(first, img((2, 2, 2)), "normal").generate(OPTS).alpha.tolist() == [[100]]
    assert I.CombineBlend(first, img((2, 2, 2), alpha=[7]), "normal").generate(OPTS).alpha.tolist() == [[7]]


# ------------------------------------------------------------------ alpha

def test_set_mask_multiplies_alpha_with_mask_red() -> None:
    out = I.SetMask(img((9, 9, 9), (9, 9, 9), alpha=[255, 128]),
                    img((255, 0, 0), (128, 255, 255))).generate(OPTS)
    assert out.alpha.tolist() == [[255, 128 * 128 // 255]]
    no_alpha = I.SetMask(img((9, 9, 9)), img((64, 0, 0))).generate(OPTS)
    assert no_alpha.alpha.tolist() == [[64]]


def test_set_alpha_constant() -> None:
    assert I.SetAlpha(img((1, 1, 1)), 0.5).generate(OPTS).alpha.tolist() == [[127]]


# ----------------------------------------------------------------- colors

def test_recolor_single_color() -> None:
    # pure red takes the color; white stays white; a light color recolors green to white
    color = Color(30, 60, 200)      # grey = (6969*30 + 23434*60 + 2365*200)/32768 = 63 -> dark
    out = px(I.Recolor(img((255, 0, 0), (255, 255, 255), (0, 255, 0)), color))
    assert out == [[30, 60, 200], [255, 255, 255], [0, 0, 0]]


def test_recolor_four_colors_mixes_parts() -> None:
    red, green, blue, white = Color(100, 0, 0), Color(0, 100, 0), Color(0, 0, 100), Color(255, 255, 255)
    # (200, 100, 100): lo=100 -> nr=100, nw=100, total=255
    out = px(I.Recolor4(img((200, 100, 100)), red, green, blue, white))
    assert out == [[(100 * 100 + 100 * 255) // 255, (100 * 255) // 255, (100 * 255) // 255]]


def test_invert_and_saturate() -> None:
    assert px(I.Invert(img((0, 100, 255)))) == [[255, 155, 0]]
    assert px(I.Saturate(img((200, 100, 50)), 1)) == [[255, 0, 0]]
    assert px(I.Saturate(img((200, 100, 50)), 0)) == [[200, 100, 50]]


# --------------------------------------------------------------- geometry

def test_flip_and_crop() -> None:
    row = img((1, 1, 1), (2, 2, 2), (3, 3, 3))
    assert px(I.Flip(row, True)) == [[3, 3, 3], [2, 2, 2], [1, 1, 1]]
    assert px(I.Crop(row, 2, 1, 1, 0)) == [[2, 2, 2], [3, 3, 3]]
    padded = I.Crop(row, 2, 1, 2, 0).generate(OPTS)
    assert padded.rgb.reshape(-1, 3).tolist()[0] == [3, 3, 3] and padded.alpha.tolist() == [[255, 0]]


def test_enlarge_adds_transparent_border() -> None:
    out = I.Enlarge(Fixed(I.Raster(np.full((10, 10, 3), 9, np.uint8))), 0.1).generate(OPTS)
    assert out.size == (12, 12)
    assert out.alpha[0, 0] == 0 and out.alpha[5, 5] == 255


def test_drop_shadow_is_behind_and_offset() -> None:
    a = np.zeros((10, 10), np.uint8)
    a[2:5, 2:5] = 255
    shape = Fixed(I.Raster(np.full((10, 10, 3), 255, np.uint8), a))
    out = I.DropShadow(shape, 0.3, 0.3, 1.0, 0, Color(0, 0, 0)).generate(OPTS)
    assert out.alpha[3, 3] == 255 and tuple(out.rgb[3, 3]) == (255, 255, 255)   # image on top
    assert out.alpha[6, 6] == 255 and tuple(out.rgb[6, 6]) == (0, 0, 0)         # shadow
    assert out.alpha[0, 0] == 0


def test_nine_slice_keeps_corners() -> None:
    src = np.zeros((3, 3, 3), np.uint8)
    src[0, 0] = (255, 0, 0)
    out = I.NineSlice(Fixed(I.Raster(src)), 9, 9, 1, 1, 1, 1).generate(OPTS)
    assert out.size == (9, 9) and tuple(out.rgb[0, 0]) == (255, 0, 0) and tuple(out.rgb[1, 1]) == (0, 0, 0)


def test_conform_sizes() -> None:
    gen = Fixed(I.Raster(np.zeros((20, 10, 3), np.uint8)))
    assert gen.generate_conform(I.ImageOptions(width=5)).size == (5, 10)
    assert gen.generate_conform(I.ImageOptions(width=30, height=30)).size == (30, 30)
    assert gen.generate_conform(I.ImageOptions(width=30, height=30, preserve_aspect="fit")).size == (15, 30)


# ----------------------------------------------------------------- scripts

def script(source):
    return run(source, ctx=Context(builtin_variables()))


def test_rgb_values() -> None:
    assert to_code(script("rgb(1, 2, 300)")) == "rgb(1,2,255)"
    assert to_code(script("rgba(1, 2, 3, 4)")) == "rgba(1,2,3,4)"
    assert script("rgb(1,2,3) == rgb(1,2,3)") is True
    assert to_code(script('to_color("#ff0000")')) == "rgb(255,0,0)"
    assert to_code(script('to_color("nonsense") or else "bad"')) == '"bad"'


def test_scripts_build_image_recipes() -> None:
    value = script('masked_blend(light: "a.png", dark: "b.png", mask: "m.png")')
    assert isinstance(value, I.MaskedBlend) and value.light == I.PackagedImage("a.png")
    assert script('set_combine(combine: "shadow", input: "x.png")').combine == "shadow"
    assert script('import_image("Z:/definitely/missing.png") or else "none"') == "none"
