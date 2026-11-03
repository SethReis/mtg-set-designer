"""The print as a PDF, with reportlab.

    write_pdf(path, pages(faces, grid), grid, draw=image_drawer(pictures), title="My Set")

Each distinct face is drawn once into a PDF form (an XObject) and placed on the page as
often as it is printed, so copies don't make the file bigger. A face's form covers its
bleed box: the 63 x 88 mm card plus `grid.bleed` on every side.

Rendered pictures (`image_drawer`) have rounded, transparent corners, which are filled
with the card's border color; bleed repeats the outermost pixels outward (renders have
no real bleed area). Pictures go in as high-quality JPEG to keep the file small.
"""
from __future__ import annotations

import io
from dataclasses import replace
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from .selection import PrintFace
from .sheet import Grid, Slot

MARK = 4.0                              # crop mark length, mm
MARK_GAP = 1.0                          # between the bleed edge and a mark
JPEG_QUALITY = 92

# draw(canvas, face, width, height, bleed): draw one face with its bleed box at (0, 0), in
# points; the card itself is at (bleed, bleed) and is width x height
Drawer = Callable[[Canvas, PrintFace, float, float, float], None]


def border_color(image: Image.Image) -> tuple[int, int, int]:
    """The color along the card's edges, away from the rounded corners."""
    rgb = np.asarray(image.convert("RGB"))
    alpha = np.asarray(image.getchannel("A")) if "A" in image.getbands() else None
    h, w = rgb.shape[:2]
    edges = [rgb[h // 5:4 * h // 5, 1], rgb[h // 5:4 * h // 5, w - 2],
             rgb[1, w // 5:4 * w // 5], rgb[h - 2, w // 5:4 * w // 5]]
    if alpha is not None:
        masks = [alpha[h // 5:4 * h // 5, 1], alpha[h // 5:4 * h // 5, w - 2],
                 alpha[1, w // 5:4 * w // 5], alpha[h - 2, w // 5:4 * w // 5]]
        edges = [e[m > 128] for e, m in zip(edges, masks)]
    pixels = np.concatenate([e for e in edges if len(e)]) if any(len(e) for e in edges) else None
    if pixels is None:
        return 0, 0, 0
    return tuple(int(v) for v in np.median(pixels, axis=0))


def print_picture(image: Image.Image, bleed_px: int) -> Image.Image:
    """An RGB picture ready to print: corners filled, `bleed_px` of edge added all round."""
    image = image.convert("RGBA")
    filled = Image.new("RGBA", image.size, border_color(image) + (255,))
    filled.alpha_composite(image)
    rgb = np.asarray(filled.convert("RGB"))
    if bleed_px > 0:
        rgb = np.pad(rgb, ((bleed_px, bleed_px), (bleed_px, bleed_px), (0, 0)), mode="edge")
    return Image.fromarray(rgb)


def image_drawer(pictures: dict[tuple[str, int], Path | Image.Image]) -> Drawer:
    """Draws rendered pictures: {(card id, face): picture file or image}."""
    def draw(canvas: Canvas, face: PrintFace, width: float, height: float, bleed: float) -> None:
        source = pictures[face.key]
        image = Image.open(source) if isinstance(source, (str, Path)) else source
        try:
            bleed_px = round(bleed / width * image.width) if bleed else 0
            picture = print_picture(image, bleed_px)
        finally:
            if image is not source:
                image.close()
        data = io.BytesIO()
        picture.save(data, "JPEG", quality=JPEG_QUALITY, subsampling=0)
        data.seek(0)
        canvas.drawImage(ImageReader(data), 0, 0, width + 2 * bleed, height + 2 * bleed)
    return draw


def label_text(face: PrintFace, code: str) -> str:
    card = face.card
    side = "" if len(card.faces) == 1 else (" · front" if face.face == 0 else " · back")
    return f"{code} {card.collector_number or '—'}{side}".strip()


def write_pdf(target: Path | io.BytesIO, sheets: list[list[Slot]], grid: Grid, draw: Drawer, *,
              crop_marks: bool = True, label: Callable[[PrintFace], str] | None = None,
              title: str = "", author: str = "",
              progress: Callable[[int, int], None] | None = None) -> int:
    """Write the sheets (slots holding PrintFaces); returns the number of pages."""
    page_w, page_h = grid.page
    canvas = Canvas(target if isinstance(target, io.BytesIO) else str(target),
                    pagesize=(page_w * mm, page_h * mm), pageCompression=1)
    canvas.setTitle(title)
    canvas.setAuthor(author)
    canvas.setCreator("Set Designer")
    w, h = grid.card[0] * mm, grid.card[1] * mm
    bleed = grid.bleed * mm
    forms: dict[tuple[str, int], str] = {}
    for number, sheet in enumerate(sheets, start=1):
        for slot in sheet:
            face: PrintFace = slot.item
            name = forms.get(face.key)
            if name is None:
                name = forms[face.key] = f"face{len(forms)}"
                canvas.beginForm(name, 0, 0, w + 2 * bleed, h + 2 * bleed)
                draw(canvas, face, w, h, bleed)
                canvas.endForm()
            x = slot.x * mm - bleed
            y = (page_h - slot.y) * mm - h - bleed        # PDF y runs up from the bottom
            canvas.saveState()
            canvas.translate(x, y)
            canvas.doForm(name)
            canvas.restoreState()
            if label is not None:
                canvas.setFont("Helvetica", 6)
                canvas.setFillGray(0.35)
                canvas.drawCentredString(x + bleed + w / 2, y - 2.4 * mm, label(face))
        if crop_marks and sheet:
            draw_crop_marks(canvas, grid, len(sheet))
        if progress is not None:
            progress(number, len(sheets))
        canvas.showPage()
    canvas.save()
    return len(sheets)


def draw_crop_marks(canvas: Canvas, grid: Grid, used: int) -> None:
    """Short lines in the margins, in line with every card edge (never over a card)."""
    page_w, page_h = grid.page
    rows = -(-used // grid.columns)
    xs, ys = replace(grid, columns=grid.columns if rows > 1 else used, rows=rows).trim_lines()
    top = grid.top - grid.bleed - MARK_GAP
    bottom = ys[-1] + grid.bleed + MARK_GAP
    left = grid.left - grid.bleed - MARK_GAP
    right = max(xs) + grid.bleed + MARK_GAP
    canvas.setStrokeGray(0)
    canvas.setLineWidth(0.25)

    def line(x1: float, y1: float, x2: float, y2: float) -> None:
        canvas.line(x1 * mm, (page_h - y1) * mm, x2 * mm, (page_h - y2) * mm)

    for x in xs:
        line(x, max(0.0, top - MARK), x, top)
        line(x, bottom, x, min(page_h, bottom + MARK))
    for y in ys:
        line(max(0.0, left - MARK), y, left, y)
        line(right, y, min(page_w, right + MARK), y)
