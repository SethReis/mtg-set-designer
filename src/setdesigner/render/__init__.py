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
from .mse_layout import mse_layout
from .mse_service import MSEError, MSERenderer, find_mse


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
        if use_mse:
            try:
                self.mse = MSERenderer(project, self.env, mse_exe)
            except MSEError as e:
                self.warnings.append(f"Using the built-in renderer: {e}")

    def card_changed(self, card: Card) -> None:
        """Call after editing a card (its text, rarity, frame, ...)."""
        self.env.refresh_card(card)

    def render(self, card: Card, face: int = 0) -> Image.Image:
        if self.mse is not None:
            try:
                image = self.mse.render(card, face)
                self.last_backend = "mse"
                return image
            except MSEError as e:
                self.warnings.append(f"MSE could not render {card.id}: {e}; used the built-in renderer")
        self.last_backend = "builtin"
        return render_card(self.env, card, face)

    def render_set(self, out_dir: Path) -> list[Path]:
        """Every face to PNG files (for printing)."""
        if self.mse is not None:
            try:
                return self.mse.render_set(out_dir)
            except MSEError as e:
                self.warnings.append(f"MSE could not render the set: {e}; used the built-in renderer")
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
