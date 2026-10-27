"""Rendered card pictures for the set overview, cached on disk and made in the background.

    worker = session.thumbnails            # one per open set
    worker.request(cards)                  # what the overview shows, in display order
    worker.get(card)                       # picture file, or None until it's rendered
    worker.version                         # goes up whenever a picture becomes ready

A picture is stored under a key that changes whenever the card would look different
(`CardRenderer.render_keys`), so reopening a set shows unchanged cards at once and only
edited cards are drawn again. Pictures are kept outside the set folder (which may be
in git): %LOCALAPPDATA%/setdesigner/thumbnails/<set>/<card id>@<key>.webp.

Rendering happens in batches (one MSE set load each), taking the renderer lock per
batch only, so a live preview in the editor never waits long.
"""
from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path

from PIL import Image

from ..model import Card

CACHE_VERSION = "1"              # bump to redraw every cached picture (renderer changes)
BATCH = 20                       # cards per MSE load
WIDTH = 300                      # stored picture width in pixels (tiles are smaller)


def default_cache_dir(set_folder: Path) -> Path:
    """$SETDESIGNER_CACHE_DIR (tests use it), else %LOCALAPPDATA%/setdesigner."""
    base = os.environ.get("LOCALAPPDATA")
    root = Path(os.environ.get("SETDESIGNER_CACHE_DIR")
                or (Path(base) / "setdesigner" if base else Path.home() / ".setdesigner"))
    name = hashlib.sha1(str(Path(set_folder).resolve()).encode("utf-8")).hexdigest()[:12]
    return root / "thumbnails" / f"{Path(set_folder).name}-{name}"


class ThumbnailCache:
    """Picture files by (card id, key). Card ids never contain "@"."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def path(self, card_id: str, key: str) -> Path:
        short = hashlib.sha1(f"{CACHE_VERSION}:{key}".encode("utf-8")).hexdigest()[:16]
        return self.folder / f"{card_id}@{short}.webp"

    def get(self, card_id: str, key: str) -> Path | None:
        path = self.path(card_id, key)
        return path if path.is_file() else None

    def put(self, card_id: str, key: str, image: Image.Image) -> Path:
        """Store a picture (scaled to WIDTH) and delete the card's older ones."""
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.path(card_id, key)
        height = round(image.height * WIDTH / image.width)
        image.resize((WIDTH, height), Image.Resampling.LANCZOS).save(path, "WEBP", quality=90)
        self.remove(card_id, keep=path)
        return path

    def remove(self, card_id: str, keep: Path | None = None) -> None:
        if self.folder.is_dir():
            for old in self.folder.glob(f"{card_id}@*.webp"):
                if old != keep:
                    old.unlink(missing_ok=True)


class ThumbnailWorker:
    """Makes the pictures the overview asks for, in a background thread.

    `session` must offer `using_renderer(fn)` (runs fn(renderer) under the renderer
    lock) and `refresh_edited()`; see SetSession."""

    def __init__(self, session, cache: ThumbnailCache):
        self.session = session
        self.cache = cache
        self.version = 0                        # read by the UI to spot new pictures
        self.error = ""                         # last rendering problem, for the UI
        self._ready: dict[str, Path] = {}       # card id -> picture of its current version
        self._wanted: list[Card] = []
        self._generation = 0
        self._wake = threading.Event()
        self._stop = False
        self._thread: threading.Thread | None = None

    # ---------------------------------------------------------------- for the UI

    def request(self, cards: list[Card]) -> None:
        """Make pictures for these cards (replaces the previous request)."""
        self._wanted = list(cards)
        self._generation += 1
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="thumbnails", daemon=True)
            self._thread.start()
        self._wake.set()

    def get(self, card: Card) -> Path | None:
        return self._ready.get(card.id)

    def forget(self, card_id: str) -> None:
        """The card changed or was deleted: its picture is out of date."""
        self._ready.pop(card_id, None)

    def stop(self) -> None:
        self._stop = True
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=30)

    def wait_idle(self, timeout: float = 120.0) -> bool:
        """Block until every requested picture is ready (for tests)."""
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.error or all(c.id in self._ready for c in self._wanted):
                return not self.error
            time.sleep(0.05)
        return False

    # ---------------------------------------------------------------- background

    def _run(self) -> None:
        while not self._stop:
            self._wake.wait()
            self._wake.clear()
            if self._stop:
                return
            try:
                self._work(self._generation)
            except Exception as e:              # keep the thread alive; the UI shows it
                self.error = str(e)

    def _work(self, generation: int) -> None:
        cards = self._wanted
        keys = self.session.using_renderer(lambda r: (self.session.refresh_edited(r),
                                                      r.render_keys(cards))[1])
        missing = []
        for card in cards:
            path = self.cache.get(card.id, keys[card.id])
            if path is not None:
                self._ready[card.id] = path
            else:
                self._ready.pop(card.id, None)
                missing.append(card)
        if len(missing) < len(cards):
            self.version += 1
        for start in range(0, len(missing), BATCH):
            if self._stop or generation != self._generation:
                return                          # a newer request takes over
            batch = missing[start:start + BATCH]
            images = self.session.using_renderer(lambda r: r.render_many(batch))
            for card in batch:
                self._ready[card.id] = self.cache.put(card.id, keys[card.id], images[card.id, 0])
            self.version += 1
        self.error = ""
