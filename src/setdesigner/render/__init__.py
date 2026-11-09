"""Card rendering.

    renderer = CardRenderer(project)        # once per open project
    image = renderer.render(card, face=0)   # PIL image, 375 x 523 for M15
    renderer.card_changed(card)             # after editing a card, before re-rendering

Real Magic Set Editor draws the cards (mse_service.py), with our own set symbol on
top. If MSE is missing or fails, our own renderer (an exact copy of MSE's layout,
with slightly different text rasterizing) is used instead and `last_backend` says so.

layout.py   our own card description (the seam)
draw.py     our drawing engine (+ text.py, fonts.py, symbol.py)
mse_layout.py, stylesheet.py, symbol_font.py   MSE stylesheet -> layout
mse_service.py   real MSE as the renderer
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..model import Card, SetProject
from ..mse.environment import ScriptEnvironment
from .draw import draw
from .layout import CardLayout
from .mse_layout import MSELayoutBuilder, mse_layout
from ..mse.mapping import face_uid
from .mse_service import MSEBlocked, MSEError, MSERenderer, find_mse, render_keys


# the editor's parts -> the stylesheet entries that draw them (the first one a frame has)
PART_ENTRIES: dict[str, tuple[str, ...]] = {
    "name": ("name",),
    "cost": ("casting cost",),
    "type": ("type", "super type"),
    "text": ("text", "rule text"),
    "pt": ("pt", "power"),
    "loyalty": ("loyalty",),
    "art": ("image",),
    "indicator": ("indicator",),
}


def card_layout(env: ScriptEnvironment, card: Card, face: int = 0) -> CardLayout:
    return mse_layout(env, env.card_object(card, face))


def render_card(env: ScriptEnvironment, card: Card, face: int = 0) -> Image.Image:
    """Our own renderer (no MSE needed)."""
    return draw(card_layout(env, card, face))


class CardRenderer:
    """Renders a project's cards: real MSE when available, else our own renderer."""

    def __init__(self, project: SetProject, use_mse: bool = True, mse_exe: Path | None = None):
        self.project = project
        self.env = ScriptEnvironment(project)
        self.mse: MSERenderer | None = None
        self.last_backend = ""
        self.warnings: list[str] = []
        self.blocked = ""                # Windows won't run MSE: why (then MSE isn't tried again)
        self.use_mse = use_mse
        if use_mse:
            try:
                self.mse = MSERenderer(project, self.env, mse_exe)
            except MSEError as e:
                self.warnings.append(f"Using the built-in renderer: {e}")

    def card_changed(self, card: Card) -> None:
        """Call after editing a card (its text, rarity, frame, ...)."""
        self.env.refresh_card(card)

    @property
    def _use_mse(self) -> bool:
        return self.mse is not None and not self.blocked

    def _failed(self, e: MSEError, what: str) -> None:
        if isinstance(e, MSEBlocked):
            self.blocked = str(e)
            self.warnings.append(str(e))
        else:
            self.warnings.append(f"MSE could not render {what}: {e}; used the built-in renderer")

    def mse_status(self) -> tuple[str, str]:
        """Whether MSE draws the cards: ("ok" | "off" | "missing" | "blocked" | "failed", why).
        "off": this renderer doesn't use MSE on purpose (tests). Starts MSE if it isn't
        running, so call it off the UI thread."""
        if not self.use_mse:
            return "off", ""
        if self.mse is None:
            return "missing", "Magic Set Editor wasn't found, so the built-in renderer draws the cards"
        if not self.blocked and not self.mse.process.alive:
            try:
                self.mse.process.start()
            except MSEBlocked as e:
                self.blocked = str(e)
            except MSEError as e:
                return "failed", f"Magic Set Editor could not start ({e}), so the built-in renderer draws the cards"
        return ("blocked", self.blocked) if self.blocked else ("ok", "")

    def mse_problem(self) -> str:
        """Why MSE can't draw the cards ("" when it can or isn't meant to)."""
        return self.mse_status()[1]

    def retry_mse(self) -> tuple[str, str]:
        """Forget that Windows blocked MSE and try it again (after the user renewed
        Windows' trust in it, see app/mse_trust.py)."""
        self.blocked = ""
        return self.mse_status()

    def gui_exe(self) -> Path | None:
        """MSE's windowed program, next to the command-line one we run."""
        if self.mse is None:
            return None
        exe = self.mse.process.exe.with_suffix(".exe")
        return exe if exe.is_file() else None

    def render(self, card: Card, face: int = 0) -> Image.Image:
        if self._use_mse:
            try:
                image = self.mse.render(card, face)
                self.last_backend = "mse"
                return image
            except MSEError as e:
                self._failed(e, card.id)
        self.last_backend = "builtin"
        return render_card(self.env, card, face)

    def render_keys(self, cards: list[Card]) -> dict[str, str]:
        """A key per card that changes whenever its picture would (for caching renders).
        Includes which renderer draws, so built-in pictures are redone once MSE works."""
        for card in cards:
            if face_uid(card, 0) not in self.env.set.by_uid:    # new since the env was made
                self.env.refresh_card(card)
        backend = "mse" if self.mse is not None else "builtin"
        return {cid: f"{backend}-{key}" for cid, key in render_keys(self.project, self.env, cards).items()}

    def art_box(self, card: Card, face: int = 0) -> tuple[float, float] | None:
        """(width, height) of the face's art box in its frame (None if it has none)."""
        builder = MSELayoutBuilder(self.env, self.env.card_object(card, face))
        entry = builder.entry("image")
        box = builder.box(entry) if entry is not None else None
        return (box.width, box.height) if box is not None and box.width > 0 and box.height > 0 else None

    def field_boxes(self, card: Card, face: int = 0) -> dict[str, tuple[float, float, float, float]]:
        """Where each editable part is on the face, for the editor's hotspots:
        {part: (left, top, width, height)} as fractions of the card's size, for the parts
        the frame shows (see PART_ENTRIES)."""
        builder = MSELayoutBuilder(self.env, self.env.card_object(card, face))
        width, height = builder.ss.card_width, builder.ss.card_height
        out = {}
        for part, names in PART_ENTRIES.items():
            for name in names:
                entry = builder.entry(name)
                if entry is None:
                    continue
                box = builder.box(entry) if builder.visible(entry) else None
                if box is not None and box.width > 0 and box.height > 0:
                    left, top = max(0.0, box.left / width), max(0.0, box.top / height)
                    out[part] = (left, top, min(box.width / width, 1 - left), min(box.height / height, 1 - top))
                break
        return out

    def render_many(self, cards: list[Card]) -> dict[tuple[str, int], Image.Image]:
        """Every face of several cards: {(card id, face index): image}."""
        if self._use_mse:
            try:
                images = self.mse.render_many(cards)
                self.last_backend = "mse"
                return images
            except MSEError as e:
                self._failed(e, "a batch")
        self.last_backend = "builtin"
        return {(card.id, face): render_card(self.env, card, face)
                for card in cards for face in range(len(card.faces))}

    def render_set(self, out_dir: Path) -> list[Path]:
        """Every face to PNG files (for printing)."""
        if self._use_mse:
            try:
                return self.mse.render_set(out_dir)
            except MSEError as e:
                self._failed(e, "the set")
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for card in self.project.cards:
            for face in range(len(card.faces)):
                path = out_dir / f"{card.id}{'' if len(card.faces) == 1 else f'-{face + 1}'}.png"
                render_card(self.env, card, face).save(path)
                written.append(path)
        return written

    def close(self) -> None:
        if self.mse is not None:
            self.mse.close()

    def __enter__(self) -> "CardRenderer":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


__all__ = ["CardRenderer", "render_card", "card_layout", "draw", "CardLayout", "find_mse"]
