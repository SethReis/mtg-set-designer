"""Reading an uploaded set symbol: which pixels are the symbol, whatever the background."""
import io

import numpy as np
from PIL import Image, ImageDraw

from setdesigner.render.symbol import ink, symbol_image


def common_style(background) -> Image.Image:
    """A ready-made common symbol: black body, white outline, a white inner line."""
    img = Image.new("RGBA", (200, 200), background)
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 180, 180], fill="white")          # outline
    d.rectangle([30, 30, 170, 170], fill="black")          # body
    d.rectangle([95, 40, 105, 160], fill="white")          # inner detail
    return img


def at(shape: Image.Image, xy) -> int:
    return shape.getpixel(xy)


def test_transparent_background_white_outline_and_details_are_gaps() -> None:
    shape = ink(common_style((0, 0, 0, 0)))
    assert at(shape, (50, 50)) == 255                      # black body
    assert at(shape, (100, 100)) == 0                      # white inner line: a gap
    assert at(shape, (24, 100)) == 0                       # white outline: not the symbol
    assert at(shape, (5, 5)) == 0                          # background


def test_white_background() -> None:
    shape = ink(common_style("white").convert("RGB"))
    assert (at(shape, (50, 50)), at(shape, (100, 100)), at(shape, (5, 5))) == (255, 0, 0)


def test_black_background_light_symbol() -> None:
    img = Image.new("RGB", (200, 200), "black")
    ImageDraw.Draw(img).ellipse([40, 40, 160, 160], fill="white")
    shape = ink(img)
    assert (at(shape, (100, 100)), at(shape, (5, 5))) == (255, 0)


def test_light_symbol_on_transparent_background_is_kept() -> None:
    img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([40, 40, 160, 160], fill=(240, 240, 240, 255))
    assert at(ink(img), (100, 100)) == 255


def test_jpeg_noise_drops_out() -> None:
    out = io.BytesIO()
    common_style("white").convert("RGB").save(out, "JPEG", quality=60)
    shape = np.asarray(ink(Image.open(io.BytesIO(out.getvalue()))))
    assert shape[:15, :15].max() == 0                      # background stays clean
    assert shape[45:60, 45:60].min() == 255


def test_common_symbol_becomes_the_other_rarities(tmp_path) -> None:
    path = tmp_path / "symbol.png"
    common_style((0, 0, 0, 0)).save(path)
    rare = np.asarray(symbol_image(str(path), "rare", 200).convert("RGB"), np.int32)
    h, w, _ = rare.shape
    body = rare[h // 2, w // 4]                            # gold body
    line = rare[h // 2, w // 2]                            # the white detail, now the outline color
    assert body[0] > 120 and body[0] > body[2]
    assert line.sum() < 150
