"""Fitting card art into a frame's art box: the crop maths (no UI, no files).

The art box has a fixed shape (its aspect ratio, which differs per frame). The crop is
the part of the image shown in it: by default the largest rectangle of the box's shape
that fits the image, centred. `ArtCrop.zoom` shrinks that rectangle (zooming in) and
`ArtCrop.x`/`y` move its centre; both are kept so the crop never leaves the image.
"""
from __future__ import annotations

from PIL import Image

from ..model import ArtCrop

MAX_ZOOM = 8.0


def _base_size(image_size: tuple[int, int], box_aspect: float) -> tuple[float, float]:
    """The largest rectangle with the box's shape (width / height) inside the image."""
    w, h = image_size
    if w / h > box_aspect:                       # image wider than the box: full height
        return h * box_aspect, float(h)
    return float(w), w / box_aspect


def _clamped(crop: ArtCrop, image_size: tuple[int, int], box_aspect: float) -> ArtCrop:
    w, h = image_size
    zoom = min(max(crop.zoom, 1.0), MAX_ZOOM)
    cw, ch = (s / zoom for s in _base_size(image_size, box_aspect))
    x = min(max(crop.x * w, cw / 2), w - cw / 2) / w
    y = min(max(crop.y * h, ch / 2), h - ch / 2) / h
    return ArtCrop(x=x, y=y, zoom=zoom)


def crop_box(image_size: tuple[int, int], box_aspect: float,
             crop: ArtCrop | None = None) -> tuple[int, int, int, int]:
    """The crop as (left, top, right, bottom) pixels of the image."""
    w, h = image_size
    crop = _clamped(crop or ArtCrop(), image_size, box_aspect)
    cw, ch = (s / crop.zoom for s in _base_size(image_size, box_aspect))
    left, top = crop.x * w - cw / 2, crop.y * h - ch / 2
    return (round(left), round(top), round(left + cw), round(top + ch))


def crop_art(image: Image.Image, box_size: tuple[int, int], crop: ArtCrop | None = None) -> Image.Image:
    """The art as it shows in a box of box_size (width, height) pixels."""
    box = crop_box(image.size, box_size[0] / box_size[1], crop)
    return image.crop(box).resize(box_size, Image.Resampling.LANCZOS)


def nudge(crop: ArtCrop | None, dx: float, dy: float, image_size: tuple[int, int],
          box_aspect: float) -> ArtCrop:
    """Move the crop by (dx, dy) image pixels (dragging), staying inside the image."""
    crop = _clamped(crop or ArtCrop(), image_size, box_aspect)
    w, h = image_size
    return _clamped(ArtCrop(x=crop.x + dx / w, y=crop.y + dy / h, zoom=crop.zoom), image_size, box_aspect)


def zoomed(crop: ArtCrop | None, zoom: float, image_size: tuple[int, int], box_aspect: float) -> ArtCrop:
    """The same centre at another zoom (kept inside the image)."""
    crop = crop or ArtCrop()
    return _clamped(ArtCrop(x=crop.x, y=crop.y, zoom=zoom), image_size, box_aspect)
