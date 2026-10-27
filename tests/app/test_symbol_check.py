"""The set symbol's small-size advice, on test shapes."""
from PIL import Image, ImageDraw

from setdesigner.app.symbol_check import FINE_DETAIL, THIN_LINES, TOO_SMALL, check_shape, check_symbol


def shape(draw) -> Image.Image:
    image = Image.new("L", (256, 256), 0)
    draw(ImageDraw.Draw(image))
    return image


def test_bold_shapes_pass() -> None:
    shield = shape(lambda d: d.polygon([(40, 20), (216, 20), (216, 140), (128, 240), (40, 140)], fill=255))
    star = shape(lambda d: d.polygon([(128, 10), (160, 100), (250, 100), (178, 155), (205, 245),
                                      (128, 190), (51, 245), (78, 155), (6, 100), (96, 100)], fill=255))
    assert check_shape(shield) == []
    assert check_shape(star) == []


def test_thin_ring_is_flagged() -> None:
    ring = shape(lambda d: d.ellipse([10, 10, 246, 246], outline=255, width=8))
    assert THIN_LINES in check_shape(ring)


def test_fine_hatching_is_flagged() -> None:
    hatch = shape(lambda d: [d.line([(x, 0), (x, 255)], fill=255, width=6) for x in range(0, 256, 18)])
    assert check_shape(hatch) == [THIN_LINES, FINE_DETAIL]


def test_a_speck_is_too_small() -> None:
    speck = shape(lambda d: d.ellipse([126, 126, 130, 130], fill=255))
    assert check_shape(speck) == [TOO_SMALL]


def test_no_file_no_advice(tmp_path) -> None:
    assert check_symbol(None) == []
    assert check_symbol(tmp_path / "missing.png") == []
