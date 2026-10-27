"""Real Magic Set Editor as the card renderer.

MSE's own rendering is the reference for its templates, so we use it: one MSE
process runs in the background (`magicseteditor.com --cli`), and cards are drawn by
its `write_image_file`. Users never see MSE; it is only the drawing engine.

Preview (one card, after an edit): a tiny set holding just that card's faces is
written and loaded (~50 ms) and rendered (~150 ms). Set-wide values are baked in, so
the result equals a render from the whole set: collector numbers come from our
ScriptEnvironment (which computes them exactly like MSE), reminder-text policies are
already in the card text.

Whole set (print): the full set is loaded once, then every card rendered.

Set symbol: MSE only draws its own vector .mse-symbol files, so it is given an empty
symbol and our rarity symbol (setdesigner/render/symbol.py) is drawn over its render.

If MSE crashes or hangs, the process is restarted and the render retried once.
"""
from __future__ import annotations

import hashlib
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from PIL import Image

from ..model import Card, SetProject
from ..mse.environment import ScriptEnvironment
from ..mse.export_set import set_file_parts, set_file_text, write_mse_set
from ..mse.mapping import face_uid

REPO = Path(__file__).resolve().parents[3]
MSE_CANDIDATES = (REPO / "Full-Magic-Pack-main" / "magicseteditor.com",
                  REPO / "resources" / "mse" / "magicseteditor.com")


class MSEError(Exception):
    """MSE reported an error, crashed, or did not answer in time."""


def find_mse() -> Path | None:
    """The MSE command-line program: $SETDESIGNER_MSE, else a bundled copy."""
    configured = os.environ.get("SETDESIGNER_MSE")
    if configured:
        return Path(configured) if Path(configured).is_file() else None
    return next((p for p in MSE_CANDIDATES if p.is_file()), None)


FONTS = REPO / "resources" / "fonts"
_registered_fonts: list[str] = []


def register_fonts(folder: Path = FONTS) -> int:
    """Make the templates' fonts (Matrix, MPlantin, Beleren, ...) available to MSE, which
    only uses fonts Windows knows. They are added for this Windows session only (nothing
    is installed or written to the registry) and removed again when Python exits.
    Returns how many font files were added."""
    if os.name != "nt" or _registered_fonts or not folder.is_dir():
        return 0
    import atexit
    import ctypes
    gdi32 = ctypes.windll.gdi32
    for path in sorted(folder.rglob("*")):
        if path.suffix.lower() in (".ttf", ".otf") and gdi32.AddFontResourceW(str(path)):
            _registered_fonts.append(str(path))
    atexit.register(lambda: [gdi32.RemoveFontResourceW(p) for p in _registered_fonts])
    return len(_registered_fonts)


class MSEProcess:
    """One running `magicseteditor.com --cli --raw`, answering one command at a time.
    (Raw mode: each answer is a status line, a line count, then that many lines.)"""

    def __init__(self, exe: Path, timeout: float = 60.0):
        self.exe = Path(exe)
        self.timeout = timeout
        self.proc: subprocess.Popen | None = None
        self.lines: queue.Queue[str | None] = queue.Queue()

    def start(self) -> None:
        self.close()
        self.lines = queue.Queue()
        register_fonts()
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self.proc = subprocess.Popen([str(self.exe), "--cli", "--quiet", "--raw"],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                         bufsize=1, creationflags=flags)
        except OSError as e:
            raise MSEError(f"could not start Magic Set Editor: {e}") from None
        threading.Thread(target=self._read, args=(self.proc, self.lines), daemon=True).start()

    @staticmethod
    def _read(proc: subprocess.Popen, lines: queue.Queue) -> None:
        for line in proc.stdout:
            lines.put(line.rstrip("\n"))
        lines.put(None)                         # end of output: the process is gone

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _line(self, deadline: float) -> str:
        try:
            line = self.lines.get(timeout=max(0.01, deadline - time.monotonic()))
        except queue.Empty:
            self.close()
            raise MSEError("MSE did not answer in time") from None
        if line is None:
            self.close()
            raise MSEError("MSE stopped unexpectedly")
        return line

    def command(self, line: str, timeout: float | None = None) -> list[str]:
        """Send one command; returns its output lines. Raises MSEError on errors."""
        if not self.alive:
            self.start()
        deadline = time.monotonic() + (timeout or self.timeout)
        try:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
        except OSError:
            self.close()
            raise MSEError("MSE stopped unexpectedly") from None
        status = self._line(deadline).strip()
        count = int(self._line(deadline))
        output = [self._line(deadline) for _ in range(count)]
        if status == "2":
            raise MSEError("\n".join(output) or "MSE reported an error")
        return output

    def close(self) -> None:
        if self.proc is not None:
            try:
                if self.proc.poll() is None:
                    self.proc.kill()
                self.proc.wait(timeout=5)
            except OSError:
                pass
        self.proc = None


def preview_overrides(env: ScriptEnvironment, uids) -> tuple[dict, dict]:
    """Set-wide values baked into a set holding only some cards, so they render as they
    would in the whole set: the card numbers (worked out on the whole set)."""
    numbers = {uid: {"custom card number": str(env.set.by_uid[uid].fields.get("card number"))}
               for uid in uids}
    return {"automatic card numbers": "no"}, numbers


def render_keys(project: SetProject, env: ScriptEnvironment, cards: list[Card]) -> dict[str, str]:
    """A key per card that changes whenever its picture would: a hash of exactly what a
    preview set for it would contain (its fields, its number, the set info and keywords).
    Works out the set file once for all the cards. Cards must be known to `env`."""
    uids = {card.id: [face_uid(card, i) for i in range(len(card.faces))] for card in cards}
    set_values, card_values = preview_overrides(env, [u for us in uids.values() for u in us])
    header, blocks = set_file_parts(project, set_values, card_values)
    symbol = Path(project.info.symbol_path) if project.info.symbol_path else None
    stamp = f"{symbol.stat().st_mtime_ns}" if symbol is not None and symbol.is_file() else ""
    return {cid: hashlib.sha1((header + stamp + "".join(blocks[u] for u in us)).encode("utf-8")).hexdigest()
            for cid, us in uids.items()}


class MSERenderer:
    """Renders our cards with real MSE (see the module docstring)."""

    def __init__(self, project: SetProject, env: ScriptEnvironment, exe: Path | None = None,
                 workdir: Path | None = None, timeout: float = 60.0):
        exe = exe or find_mse()
        if exe is None or not Path(exe).is_file():
            raise MSEError("Magic Set Editor (magicseteditor.com) was not found")
        self.project = project
        self.env = env
        self.process = MSEProcess(exe, timeout)
        self._own_workdir = workdir is None
        self.workdir = Path(workdir or tempfile.mkdtemp(prefix="setdesigner-mse-"))
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._loaded: tuple[str, str] | None = None     # (set file path, content hash)
        self._counter = 0

    # ---------------------------------------------------------------- loading

    def _load(self, path: Path, text_hash: str) -> None:
        if self._loaded == (str(path), text_hash) and self.process.alive:
            return
        self.process.command(f":load {path}")
        self.process.command(f":cd {self.workdir}")
        self._loaded = (str(path), text_hash)

    def _write_image(self, index: int) -> Image.Image:
        """Render card `index` of the loaded set and read the picture back."""
        self._counter += 1
        name = f"render-{self._counter}.png"           # unique: MSE skips repeated names
        self.process.command(f'write_image_file(file: "{name}", input: set.cards.{index})')
        path = self.workdir / name
        with Image.open(path) as img:
            image = img.convert("RGBA")
        path.unlink(missing_ok=True)
        return image

    # ---------------------------------------------------------------- preview

    def preview_values(self, card: Card) -> tuple[set[str], dict, dict]:
        """The card's MSE uids, plus the set-wide values baked into a preview set."""
        uids = {face_uid(card, i) for i in range(len(card.faces))}
        return (uids, *preview_overrides(self.env, uids))

    def render_many(self, cards: list[Card]) -> dict[tuple[str, int], Image.Image]:
        """Every face of several cards from one set load (faster than one by one: the
        load costs about as much as rendering ten faces). Like the preview, set-wide values
        are baked in, so each picture equals `render(card, face)`.
        Returns {(card id, face index): image}."""
        if not cards:
            return {}
        uids = {face_uid(card, i) for card in cards for i in range(len(card.faces))}
        set_values, card_values = preview_overrides(self.env, uids)
        options = dict(only_uids=uids, extra_set_values=set_values, extra_card_values=card_values)
        path = self.workdir / "batch.mse-set"
        for attempt in (1, 2):
            try:
                write_mse_set(self.project, path, blank_symbol=True, **options)
                self._loaded = None
                self._load(path, "batch")
                order = [uid for uid in set_file_parts(self.project)[1] if uid in uids]  # file order
                out = {}
                for card in cards:
                    for face in range(len(card.faces)):
                        image = self._write_image(order.index(face_uid(card, face)))
                        out[card.id, face] = self.add_symbol(image, card, face)
                self._loaded = None
                return out
            except MSEError:
                self._loaded = None
                if attempt == 2 or self.process.alive:
                    raise
                self.process.start()
        return {}

    def render(self, card: Card, face: int = 0) -> Image.Image:
        """One face, as MSE draws it, with our set symbol on top."""
        uids, set_values, card_values = self.preview_values(card)
        options = dict(only_uids=uids, extra_set_values=set_values, extra_card_values=card_values)
        digest = hashlib.sha1(set_file_text(self.project, **options).encode("utf-8")).hexdigest()
        path = self.workdir / "preview.mse-set"
        for attempt in (1, 2):
            try:
                if self._loaded != (str(path), digest):       # unchanged card: no reload
                    write_mse_set(self.project, path, blank_symbol=True, **options)
                self._load(path, digest)
                image = self._write_image(face)
                break
            except MSEError:
                self._loaded = None
                if attempt == 2 or self.process.alive:     # a real error, or a second failure
                    raise
                self.process.start()                         # crashed: restart and retry once
        return self.add_symbol(image, card, face)

    def add_symbol(self, image: Image.Image, card: Card, face: int) -> Image.Image:
        """Draw our rarity symbol where the frame puts it (MSE drew an empty one)."""
        from .draw import draw_layer
        from .mse_layout import MSELayoutBuilder
        builder = MSELayoutBuilder(self.env, self.env.card_object(card, face))
        entry = builder.entry("rarity")
        if entry is None or not builder.visible(entry):
            return image
        box = builder.box(entry)
        if box is None or box.width <= 0 or box.height <= 0:
            return image
        layer = builder.image_layer(entry, box)
        if layer is not None:
            draw_layer(image, layer)
        return image

    # ------------------------------------------------------------- whole set

    def render_set(self, out_dir: Path) -> list[Path]:
        """Every face of every card into out_dir (for print), from one full set load."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = self.workdir / "full.mse-set"
        write_mse_set(self.project, path, blank_symbol=True)
        self._loaded = None
        self._load(path, "full")
        written, index = [], 0
        for card in self.project.cards:
            for face in range(len(card.faces)):
                image = self.add_symbol(self._write_image(index), card, face)
                target = out_dir / f"{card.id}{'' if len(card.faces) == 1 else f'-{face + 1}'}.png"
                image.save(target)
                written.append(target)
                index += 1
        self._loaded = None
        return written

    def close(self) -> None:
        self.process.close()
        if self._own_workdir:
            shutil.rmtree(self.workdir, ignore_errors=True)

    def __enter__(self) -> "MSERenderer":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
