"""Fitting art into the art box: crop maths."""
from PIL import Image

from setdesigner.app.art import crop_art, crop_box, nudge, zoomed
from setdesigner.model import ArtCrop


def test_auto_fill_is_centred_and_fills_the_box() -> None:
    # wide image, squarer box: full height, centred horizontally
    assert crop_box((1200, 800), 1.0) == (200, 0, 1000, 800)
    # tall image, wide box: full width, centred vertically
    assert crop_box((600, 1200), 2.0) == (0, 450, 600, 750)


def test_zoom_and_position_stay_inside_the_image() -> None:
    left, top, right, bottom = crop_box((1200, 800), 1.0, ArtCrop(x=0.5, y=0.5, zoom=2))
    assert (right - left, bottom - top) == (400, 400)
    # asking for a crop past the edge clamps it to the edge
    assert crop_box((1200, 800), 1.0, ArtCrop(x=0.0, y=1.0, zoom=2)) == (0, 400, 400, 800)
    # zoom below 1 can't show more than the image
    assert crop_box((1200, 800), 1.0, ArtCrop(zoom=0.2)) == (200, 0, 1000, 800)


def test_nudge_moves_and_clamps() -> None:
    moved = nudge(None, 100, 0, (1200, 800), 1.0)
    assert crop_box((1200, 800), 1.0, moved) == (300, 0, 1100, 800)
    far = nudge(moved, 5000, 5000, (1200, 800), 1.0)
    assert crop_box((1200, 800), 1.0, far) == (400, 0, 1200, 800)
    closer = zoomed(far, 4, (1200, 800), 1.0)              # zooming keeps the visible centre
    assert closer.zoom == 4 and crop_box((1200, 800), 1.0, closer) == (700, 300, 900, 500)


def test_crop_art_size_and_content() -> None:
    image = Image.new("RGB", (1200, 800), "blue")
    image.paste((255, 0, 0), (0, 0, 600, 800))           # left half red
    out = crop_art(image, (316, 231), ArtCrop(x=0.0, y=0.5, zoom=2))
    assert out.size == (316, 231)
    assert out.getpixel((150, 100)) == (255, 0, 0)        # we're looking at the left side
