"""Print export: the faces to print, their pictures (cached), then the PDF.

    result = export_pdf(session, cards, options, "My Set-print.pdf", progress)

Rendered prints use full-size pictures from the renderer, made in batches like the
overview's (one MSE set load per batch, the renderer lock taken per batch, so the
editor's preview never waits long). They are cached under the set's picture cache in
print/<card id>@<face>-<key>.png, so exporting an unchanged set again renders nothing.

Printer-friendly prints draw text only (export/playtest.py), so they need no renderer.
Runs in a background thread; `cancel` (a threading.Event) stops it between batches.
"""
from __future__ import annotations

import hashlib
import io
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image

from ..export.pdf import image_drawer, label_text, write_pdf
from ..export.selection import PrintOptions, print_faces
from ..export.sheet import fit, pages
from ..model import Card
from .thumbnails import BATCH, CACHE_VERSION

Progress = Callable[[str, float], None]          # (what is happening, 0-1)


class Cancelled(Exception):
    pass


class PrintCache:
    """Full-size pictures by (card id, face, key). Card ids never contain "@"."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def path(self, card_id: str, face: int, key: str) -> Path:
        short = hashlib.sha1(f"{CACHE_VERSION}:{key}".encode("utf-8")).hexdigest()[:16]
        return self.folder / f"{card_id}@{face}-{short}.png"

    def get(self, card_id: str, face: int, key: str) -> Path | None:
        path = self.path(card_id, face, key)
        return path if path.is_file() else None

    def put(self, card_id: str, key: str, images: dict[int, Image.Image]) -> dict[int, Path]:
        """Store a card's faces and delete its older pictures."""
        self.folder.mkdir(parents=True, exist_ok=True)
        paths = {face: self.path(card_id, face, key) for face in images}
        for face, image in images.items():
            image.save(paths[face], "PNG")
        for old in self.folder.glob(f"{card_id}@*.png"):
            if old not in paths.values():
                old.unlink(missing_ok=True)
        return paths


@dataclass
class ExportResult:
    path: Path | None                     # None when written to a stream
    pages: int
    faces: int
    rendered: int = 0                     # cards drawn now (the rest came from the cache)
    overflow: list[str] = field(default_factory=list)   # printer-friendly: text cut short
    builtin: bool = False                 # drawn by our own renderer, not MSE
    renderer_note: str = ""               # why, when it's known (e.g. Windows blocked MSE)


def print_cache(session) -> PrintCache:
    return PrintCache(session.cache_folder / "print")


def summary(cards: list[Card], options: PrintOptions) -> tuple[int, int, tuple[int, int]]:
    """(faces, pages, (columns, rows)) the print would have."""
    faces = print_faces(cards, options)
    grid = fit(options.paper, options.bleed_mm, options.spacing_mm, options.labels)
    return len(faces), -(-len(faces) // grid.per_page), (grid.columns, grid.rows)


def pictures(session, cards: list[Card], progress: Progress | None = None,
             cancel: threading.Event | None = None) -> tuple[dict[tuple[str, int], Path], int, bool]:
    """Full-size pictures of every face: ({(card id, face): file}, cards rendered now,
    whether any came from our own renderer rather than MSE)."""
    cache = print_cache(session)
    keys = session.using_renderer(lambda r: (session.refresh_edited(r), r.render_keys(cards))[1])
    found: dict[tuple[str, int], Path] = {}
    builtin = any(key.startswith("builtin") for key in keys.values())
    missing = []
    for card in cards:
        paths = [cache.get(card.id, face, keys[card.id]) for face in range(len(card.faces))]
        if all(paths):
            found.update({(card.id, face): p for face, p in enumerate(paths)})
        else:
            missing.append(card)
    for start in range(0, len(missing), BATCH):
        if cancel is not None and cancel.is_set():
            raise Cancelled
        if progress is not None:
            progress(f"Rendering cards {start + 1}–{min(start + BATCH, len(missing))} of {len(missing)}",
                     start / len(missing))
        batch = missing[start:start + BATCH]
        images, backend = session.using_renderer(lambda r: (r.render_many(batch), r.last_backend))
        for card in batch:
            key = keys[card.id]
            if backend == "builtin" and not key.startswith("builtin"):
                key = f"builtin-{key}"             # MSE failed: don't pass these off as its pictures
            builtin = builtin or backend == "builtin"
            stored = cache.put(card.id, key, {face: images[card.id, face] for face in range(len(card.faces))})
            found.update({(card.id, face): p for face, p in stored.items()})
    return found, len(missing), builtin


def export_pdf(session, cards: list[Card], options: PrintOptions, target: Path | io.BytesIO,
               progress: Progress | None = None, cancel: threading.Event | None = None) -> ExportResult:
    faces = print_faces(cards, options)
    grid = fit(options.paper, options.bleed_mm, options.spacing_mm, options.labels)
    sheets = pages(faces, grid)
    unique = list({f.card.id: f.card for f in faces}.values())
    overflow: list[str] = []
    rendered, builtin, note = 0, False, ""
    if options.style == "friendly":
        from ..export.playtest import playtest_drawer
        draw = playtest_drawer(session.project, overflow)
    else:
        found, rendered, builtin = pictures(session, unique, progress, cancel)
        draw = image_drawer(found)
        note = session.mse_problem() if builtin else ""
    if cancel is not None and cancel.is_set():
        raise Cancelled

    def page_done(number: int, total: int) -> None:
        if cancel is not None and cancel.is_set():
            raise Cancelled
        if progress is not None:
            progress(f"Writing page {number} of {total}", number / total)

    info = session.project.info
    label = (lambda f: label_text(f, info.code)) if options.labels else None
    count = write_pdf(target, sheets, grid, draw, crop_marks=options.crop_marks, label=label,
                      title=info.name, author=info.copyright or "", progress=page_done)
    return ExportResult(target if isinstance(target, Path) else None, count, len(faces),
                        rendered, sorted(set(overflow)), builtin, note)

