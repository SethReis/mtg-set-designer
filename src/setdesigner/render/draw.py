"""The drawing engine: CardLayout -> picture. Knows nothing about MSE."""
from __future__ import annotations

import numpy as np
from PIL import Image

from ..mse.script.images import combine_rgb
from .layout import CardLayout, ImageLayer, TextLayer
from .text import draw_text


def _composite(canvas: Image.Image, image: Image.Image, x: int, y: int,
               combine: str | None = None) -> None:
    """Draw `image` onto `canvas` at (x, y), clipped to the canvas."""
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(canvas.width, x + image.width), min(canvas.height, y + image.height)
    if x1 <= x0 or y1 <= y0:
        return
    part = image.crop((x0 - x, y0 - y, x1 - x, y1 - y))
    if combine:
        under = np.asarray(canvas.crop((x0, y0, x1, y1)))
        top = np.asarray(part)
        rgb = combine_rgb(under[..., :3], top[..., :3], combine)
        part = Image.fromarray(np.dstack([rgb, top[..., 3]]), "RGBA")
    canvas.alpha_composite(part, (x0, y0))


def draw_layer(canvas: Image.Image, layer: ImageLayer | TextLayer, scale: float = 1.0) -> None:
    if isinstance(layer, TextLayer):
        image = draw_text(layer)
        if layer.angle:
            image = image.rotate(layer.angle, expand=True, resample=Image.Resampling.BICUBIC)
        _composite(canvas, image, round(layer.box.left), round(layer.box.top))
        return
    image = layer.image
    if layer.angle:
        image = image.rotate(layer.angle, expand=True, resample=Image.Resampling.BICUBIC)
    x, y = layer.alignment.place(image.size, layer.box)
    _composite(canvas, image, round(x), round(y), layer.combine)


def draw(layout: CardLayout, background: tuple = (0, 0, 0, 0)) -> Image.Image:
    canvas = Image.new("RGBA", (layout.width, layout.height), background)
    for layer in layout.layers:
        draw_layer(canvas, layer)
    return canvas
