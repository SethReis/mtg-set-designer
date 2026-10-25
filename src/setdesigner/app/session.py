"""One open set: the editor's behaviour, without any UI code.

    session = SetSession.create(folder, "My Set", "MYS", "m15")    # or SetSession.open(folder)
    card = session.new_card()
    session.update(card, "rules_text", "Flying")                    # saved ~0.5 s later
    image = session.render(card)                                    # PIL image (real MSE)
    session.close()                                                 # saves anything pending

Saving is automatic: an edit marks the card dirty, and `flush_due()` (called by the UI
a few times a second) writes cards whose last edit is older than AUTOSAVE_DELAY.
`flush()` writes everything now (on close, or when switching sets).
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Callable

from PIL import Image

from ..model import (Card, Face, Rarity, SetInfo, SetProject, Status, delete_card, load_project,
                     new_card_id, save_card, save_info, save_project)

AUTOSAVE_DELAY = 0.5                    # seconds after the last edit

FACE_FIELDS = {"name", "mana_cost", "type_line", "rules_text", "flavor_text", "power",
               "toughness", "loyalty", "artist"}
CARD_FIELDS = {"rarity", "collector_number", "frame", "status", "notes"}
OPTIONAL = {"power", "toughness", "loyalty"}            # "" means "not set"


class SessionError(Exception):
    pass


def _number_key(card: Card) -> tuple:
    digits = re.match(r"\d+", card.collector_number)
    return (int(digits.group()) if digits else float("inf"), card.collector_number, card.id)


class SetSession:
    def __init__(self, folder: Path, project: SetProject,
                 renderer_factory: Callable[[SetProject], object] | None = None):
        self.folder = Path(folder)
        self.project = project
        self._renderer_factory = renderer_factory
        self._renderer = None
        self._renderer_lock = threading.Lock()
        self._pending: dict[str, float] = {}     # card id -> time of last edit

    # ------------------------------------------------------------ opening

    @classmethod
    def create(cls, folder: Path, name: str, code: str, frame: str = "m15", **kw) -> "SetSession":
        folder = Path(folder)
        if (folder / "set.json").exists():
            raise SessionError(f"There is already a set in {folder}")
        if not name.strip() or not code.strip():
            raise SessionError("A set needs a name and a code")
        project = SetProject(info=SetInfo(name=name.strip(), code=code.strip().upper(),
                                          default_frame=frame))
        save_project(project, folder)
        return cls(folder, project, **kw)

    @classmethod
    def open(cls, folder: Path, **kw) -> "SetSession":
        folder = Path(folder)
        if not (folder / "set.json").is_file():
            raise SessionError(f"No set found in {folder} (it has no set.json)")
        return cls(folder, load_project(folder), **kw)

    # -------------------------------------------------------------- cards

    def cards(self) -> list[Card]:
        """All cards in collector-number order."""
        return sorted(self.project.cards, key=_number_key)

    def search(self, text: str) -> list[Card]:
        words = text.lower().split()
        if not words:
            return self.cards()

        def haystack(card: Card) -> str:
            return " ".join(f"{f.name} {f.type_line} {f.rules_text}" for f in card.faces).lower()

        return [c for c in self.cards() if all(w in haystack(c) for w in words)]

    def card(self, card_id: str) -> Card:
        return self.project.card(card_id)

    def next_collector_number(self) -> str:
        numbers = [int(m.group()) for c in self.project.cards
                   if (m := re.match(r"\d+", c.collector_number))]
        return str(max(numbers, default=0) + 1)

    def new_card(self, name: str = "New Card") -> Card:
        card = Card(id=new_card_id(self.project, name), faces=[Face(name=name)],
                    rarity=Rarity.COMMON, collector_number=self.next_collector_number())
        self.project.cards.append(card)
        save_card(self.folder, card)
        return card

    def duplicate(self, card: Card) -> Card:
        copy = card.model_copy(deep=True)
        copy.id = new_card_id(self.project, card.faces[0].name)
        copy.collector_number = self.next_collector_number()
        self.project.cards.append(copy)
        save_card(self.folder, copy)
        return copy

    def delete(self, card: Card) -> None:
        self.project.cards = [c for c in self.project.cards if c.id != card.id]
        self._pending.pop(card.id, None)
        delete_card(self.folder, card.id)
        if self._renderer is not None:
            with self._renderer_lock:
                self._renderer.env.remove_card(card.id)

    # ------------------------------------------------------------ editing

    def update(self, card: Card, field: str, value: object, face: int = 0) -> None:
        """Change one field and schedule saving. Face fields apply to `face`."""
        if field in FACE_FIELDS:
            if field in OPTIONAL:                          # "" or None = not set
                value = (str(value).strip() or None) if value is not None else None
            else:
                value = "" if value is None else str(value)
            setattr(card.faces[face], field, value)
        elif field in CARD_FIELDS:
            if field == "rarity":
                value = Rarity(value)
            elif field == "status":
                value = Status(value)
            elif field == "frame":
                value = value or None                       # "" = use the set's default
            setattr(card, field, value)
        else:
            raise SessionError(f"Unknown field {field!r}")
        self._pending[card.id] = time.monotonic()

    def update_info(self, **values: object) -> None:
        for key, value in values.items():
            setattr(self.project.info, key, value)
        save_info(self.folder, self.project.info)

    # ------------------------------------------------------------- saving

    @property
    def unsaved(self) -> bool:
        return bool(self._pending)

    def flush_due(self, now: float | None = None) -> list[str]:
        """Save cards whose last edit is at least AUTOSAVE_DELAY old. Returns their ids."""
        now = time.monotonic() if now is None else now
        due = [cid for cid, t in self._pending.items() if now - t >= AUTOSAVE_DELAY]
        for cid in due:
            self._save(cid)
        return due

    def flush(self) -> None:
        for cid in list(self._pending):
            self._save(cid)

    def _save(self, card_id: str) -> None:
        self._pending.pop(card_id, None)
        card = next((c for c in self.project.cards if c.id == card_id), None)
        if card is not None:
            save_card(self.folder, card)

    # ---------------------------------------------------------- rendering

    @property
    def renderer(self):
        """The card renderer, started on first use (real MSE takes a few seconds)."""
        with self._renderer_lock:
            if self._renderer is None:
                if self._renderer_factory is None:
                    from ..render import CardRenderer
                    self._renderer = CardRenderer(self.project)
                else:
                    self._renderer = self._renderer_factory(self.project)
            return self._renderer

    def render(self, card: Card, face: int = 0) -> Image.Image:
        """Render a card as it is now. Safe to call from a worker thread."""
        renderer = self.renderer
        with self._renderer_lock:
            renderer.card_changed(card)                    # cheap; keeps numbering current
            return renderer.render(card, face)

    @property
    def renderer_note(self) -> str:
        """Shown in the UI when cards are not drawn by MSE."""
        r = self._renderer
        if r is None:
            return ""
        return "built-in renderer" if r.last_backend == "builtin" else ""

    def close(self) -> None:
        self.flush()
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None
