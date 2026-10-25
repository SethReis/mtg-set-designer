"""Color and image built-ins. They build image *recipes* (see script/images.py);
pixels are only made when an image is generated at a size.

`rgb(...)` / `rgba(...)` are special forms in the evaluator (positional arguments).
"""
from __future__ import annotations

from pathlib import Path

from .. import images as I
from ..values import Color, ErrorValue, ScriptError, to_bool, to_color, to_double, to_int, to_str
from .registry import builtin


def _color(value) -> Color:
    return to_color(value)


def _opt_color(value, default: Color) -> Color:
    return default if value is None else to_color(value)


def script_options(script) -> I.ImageOptions:
    """Image options for scripts that need pixels now (dimensions_of, exists_in_package):
    the current stylesheet's package folder."""
    style = script.var("stylesheet")
    root = getattr(style, "root", None) or I.DEFAULT_ROOT
    package = getattr(style, "package", None)
    return I.ImageOptions(root=Path(root),
                          package=Path(root) / f"{package}.mse-style" if package else None)


# ------------------------------------------------------------------ colors

@builtin("to_color")
def to_color_(input):
    try:
        return to_color(input)
    except ScriptError as e:
        return ErrorValue(str(e))


# ------------------------------------------------------------------ images

@builtin("to_image")
def to_image(input):
    return I.as_image(input)


@builtin("linear_blend")
def linear_blend(image1, image2, x1, y1, x2, y2):
    return I.LinearBlend(I.as_image(image1), I.as_image(image2), to_double(x1), to_double(y1),
                         to_double(x2), to_double(y2))


@builtin("masked_blend")
def masked_blend(light, dark, mask):
    return I.MaskedBlend(I.as_image(light), I.as_image(dark), I.as_image(mask))


@builtin("combine_blend")
def combine_blend(combine, image1, image2):
    mode = to_str(combine)
    if mode not in I.COMBINE_MODES:
        raise ScriptError(f"Unknown combine mode '{mode}'")
    return I.CombineBlend(I.as_image(image1), I.as_image(image2), mode)


@builtin("set_mask")
def set_mask(image, mask):
    return I.SetMask(I.as_image(image), I.as_image(mask))


@builtin("set_alpha")
def set_alpha(input, alpha):
    return I.SetAlpha(I.as_image(input), to_double(alpha))


@builtin("set_combine")
def set_combine(combine, input):
    mode = to_str(combine)
    if mode not in I.COMBINE_MODES:
        raise ScriptError(f"Unknown combine mode '{mode}'")
    return I.SetCombine(I.as_image(input), mode)


@builtin("saturate")
def saturate(input, amount):
    return I.Saturate(I.as_image(input), to_double(amount))


@builtin("invert_image")
def invert_image(input):
    return I.Invert(I.as_image(input))


@builtin("recolor_image")
def recolor_image(input, color=None, red=None, green=None, blue=None, white=None):
    """recolor_image(color: c), or the four-color form (red:, green:, blue:, white:)."""
    if red is not None:
        return I.Recolor4(I.as_image(input), _color(red), _color(green), _color(blue),
                          _opt_color(white, Color(255, 255, 255)))
    return I.Recolor(I.as_image(input), _color(color))


@builtin("enlarge")
def enlarge(input, border_size):
    return I.Enlarge(I.as_image(input), to_double(border_size))


@builtin("crop")
def crop(input, width, height, offset_x, offset_y):
    return I.Crop(I.as_image(input), to_int(width), to_int(height), to_double(offset_x),
                  to_double(offset_y))


@builtin("crop_image")
def crop_image(input, width, height, offset_x=0, offset_y=0, background_color=None):
    return I.Crop(I.as_image(input), to_int(width), to_int(height), to_double(offset_x),
                  to_double(offset_y), None if background_color is None else _color(background_color))


@builtin("flip_horizontal")
def flip_horizontal(input):
    return I.Flip(I.as_image(input), True)


@builtin("flip_vertical")
def flip_vertical(input):
    return I.Flip(I.as_image(input), False)


@builtin("flip_image")
def flip_image(input, horizontal=False):
    return I.Flip(I.as_image(input), to_bool(horizontal))


@builtin("rotate", "rotate_image")
def rotate(input, angle):
    return I.Rotate(I.as_image(input), to_double(angle))


def _shadow(input, offset_x, offset_y, alpha, blur_radius, color):
    # MSE's optional parameters default to 0 (and black), as in SCRIPT_OPTIONAL_PARAM
    return I.DropShadow(I.as_image(input), to_double(offset_x), to_double(offset_y),
                        to_double(alpha), to_double(blur_radius), _opt_color(color, Color(0, 0, 0)))


@builtin("drop_shadow")
def drop_shadow(input, offset_x=0, offset_y=0, alpha=0, blur_radius=0, color=None):
    return _shadow(input, offset_x, offset_y, alpha, blur_radius, color)


@builtin("add_drop_shadow")
def add_drop_shadow(input, offset_x=0, offset_y=0, alpha=0, blur_radius=0, color=None):
    return _shadow(input, offset_x, offset_y, alpha, blur_radius, color)


@builtin("insert_image")
def insert_image(base_image, inserted_image, offset_x=0, offset_y=0):
    return I.Insert(I.as_image(base_image), I.as_image(inserted_image), to_double(offset_x),
                    to_double(offset_y))


@builtin("resize_image")
def resize_image(input, width, height):
    return I.Resize(I.as_image(input), to_int(width), to_int(height))


@builtin("fill_image")
def fill_image(input, color):
    return I.Fill(I.as_image(input), _color(color))


@builtin("nine_slice_image")
def nine_slice_image(input, width, height, top=0, bottom=0, left=0, right=0):
    return I.NineSlice(I.as_image(input), to_int(width), to_int(height), to_int(top),
                       to_int(bottom), to_int(left), to_int(right))


# ---------------------------------------------------------------- symbols

@builtin("symbol_variation")
def symbol_variation(symbol=None, variation="common"):
    """The set symbol in a rarity's colors. MSE renders its own vector .mse-symbol
    files here; we use the user's SVG/PNG symbol (see setdesigner/render/symbol.py)."""
    from setdesigner.render.symbol import RaritySymbol
    path = to_str(symbol) if symbol not in (None, "") else None
    return RaritySymbol(path, to_str(variation))


# ---------------------------------------------------------------- files

@builtin("get_mse_path")
def get_mse_path():
    """MSE's install folder. Ours is a marker: "<mse>/data/x" means package file x."""
    return I.MSE_PATH


@builtin("import_image")
def import_image(input, script):
    """An image file from disk, or an error value if there is none."""
    path = to_str(input)
    opts = script_options(script)
    exists = I.file_exists(path, opts) if path.startswith(I.MSE_PATH + "/") else Path(path).is_file()
    if not exists:
        return ErrorValue(f"File not found: '{path}'")
    return I.ImportedImage(path)


@builtin("exists_in_package")
def exists_in_package(input, script):
    return I.file_exists(to_str(input), script_options(script))


def _natural_size(input, script) -> tuple[int, int]:
    return I.as_image(input).generate(script_options(script)).size


@builtin("dimensions_of")
def dimensions_of(input, script):
    return list(_natural_size(input, script))


@builtin("width_of")
def width_of(input, script):
    return _natural_size(input, script)[0]


@builtin("height_of")
def height_of(input, script):
    return _natural_size(input, script)[1]
