"""Bringing image files into a set: card art and the set symbol.

Files are copied into the set folder (so the set stays self-contained) and stored
there by a path relative to it:

    assets/art/<card id>.<ext>          (a back face: <card id>-2.<ext>)
    assets/symbol.svg / assets/symbol.png

PNG, JPEG and WebP art is kept as it is; other images are converted to PNG.
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from ..model import Card

KEEP_FORMATS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}


class AssetError(Exception):
    """The file can't be used (not an image, unreadable, ...)."""


def _open_image(data: bytes, filename: str) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        return image
    except (UnidentifiedImageError, OSError, ValueError):
        raise AssetError(f"“{filename}” is not an image this app can read "
                         "(use PNG, JPEG, WebP, GIF, BMP or TIFF)") from None


def _image_bytes(data: bytes, filename: str) -> tuple[bytes, str]:
    """The file as stored: original bytes for PNG/JPEG/WebP, else converted to PNG."""
    image = _open_image(data, filename)
    if image.format in KEEP_FORMATS:
        return data, KEEP_FORMATS[image.format]
    out = io.BytesIO()
    image.convert("RGBA").save(out, "PNG")
    return out.getvalue(), ".png"


def _replace(folder: Path, stem: str, data: bytes, ext: str) -> Path:
    """Write <stem><ext>, removing the same stem with other extensions."""
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{stem}.*"):
        old.unlink(missing_ok=True)
    path = folder / f"{stem}{ext}"
    path.write_bytes(data)
    return path


def art_stem(card: Card, face: int) -> str:
    return card.id if face == 0 else f"{card.id}-{face + 1}"


def import_art(session, card: Card, data: bytes, filename: str, face: int = 0) -> str:
    """Copy art into the set for one face of a card (replacing its earlier art) and
    reset the crop. Returns the stored relative path."""
    content, ext = _image_bytes(data, filename)
    path = _replace(session.folder / "assets" / "art", art_stem(card, face), content, ext)
    relative = path.relative_to(session.folder).as_posix()
    session.update(card, "art_path", relative, face)
    session.update(card, "art_crop", None, face)
    session.art_version += 1
    return relative


def remove_art(session, card: Card, face: int = 0) -> None:
    path = session.project.resolve(card.faces[face].art_path)
    if path is not None and path.is_file() and session.folder in path.parents:
        path.unlink()
    session.update(card, "art_path", None, face)
    session.update(card, "art_crop", None, face)
    session.art_version += 1


def import_symbol(session, data: bytes, filename: str) -> str:
    """Copy a set symbol (SVG or an image) into the set. Returns its relative path."""
    head = data[:2048].lstrip().lower()
    if filename.lower().endswith(".svg") or head.startswith(b"<svg") or b"<svg" in head:
        if b"<svg" not in data[:65536].lower():
            raise AssetError(f"“{filename}” is not an SVG file")
        content, ext = data, ".svg"
    else:
        content, ext = _image_bytes(data, filename)
    path = _replace(session.folder / "assets", "symbol", content, ext)
    relative = path.relative_to(session.folder).as_posix()
    session.update_info(symbol_path=relative)
    return relative
