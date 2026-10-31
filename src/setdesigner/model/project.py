"""A set project on disk: a folder of human-readable, git-friendly JSON.

    my_set/
      set.json           SetInfo
      mechanics.json     list of Mechanic
      archetypes.json    list of Archetype
      cycles.json        list of Cycle
      cards/<id>.json    one Card per file
      assets/            set symbol, custom frames, art (referenced by path)

Cards load in id (file name) order; a card's place in the set comes from its
collector number, not from file order.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from pydantic import BaseModel, Field

from .archetype import Archetype
from .card import Card, Face
from .cycle import Cycle
from .mechanic import Mechanic
from .set_info import SetInfo


class SetProject(BaseModel):
    info: SetInfo
    mechanics: list[Mechanic] = Field(default_factory=list)
    archetypes: list[Archetype] = Field(default_factory=list)
    cycles: list[Cycle] = Field(default_factory=list)
    # where the set lives (set by load_project / save_project; not saved): paths inside
    # the set, such as art and the symbol, are stored relative to it
    folder: Path | None = Field(default=None, exclude=True)
    cards: list[Card] = Field(default_factory=list)

    def card(self, card_id: str) -> Card:
        return next(c for c in self.cards if c.id == card_id)

    def iter_faces(self) -> Iterator[tuple[Card, int, Face]]:
        """Every face of every card, for analysis that counts faces separately."""
        for card in self.cards:
            for index, face in card.iter_faces():
                yield card, index, face

    def resolve(self, path: str | None) -> Path | None:
        """A path stored in the set (relative to its folder, e.g. "assets/art/bear.png")
        as a full path. Absolute paths are kept; None or "" give None."""
        if not path:
            return None
        p = Path(path)
        if p.is_absolute() or self.folder is None:
            return p
        return self.folder / p


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != text:    # keep mtimes stable
        path.write_text(text, encoding="utf-8")


def _dump(model: BaseModel) -> dict:
    return model.model_dump(mode="json")


def save_project(project: SetProject, folder: Path) -> None:
    folder = Path(folder)
    project.folder = folder
    _write_json(folder / "set.json", _dump(project.info))
    _write_json(folder / "mechanics.json", [_dump(m) for m in project.mechanics])
    _write_json(folder / "archetypes.json", [_dump(a) for a in project.archetypes])
    _write_json(folder / "cycles.json", [_dump(c) for c in project.cycles])
    cards_dir = folder / "cards"
    for card in project.cards:
        _write_json(cards_dir / f"{card.id}.json", _dump(card))
    # remove files of cards that were deleted from the project
    keep = {f"{card.id}.json" for card in project.cards}
    if cards_dir.is_dir():
        for path in cards_dir.glob("*.json"):
            if path.name not in keep:
                path.unlink()


def save_card(folder: Path, card: Card) -> None:
    """Write one card's file (autosave after an edit)."""
    _write_json(Path(folder) / "cards" / f"{card.id}.json", _dump(card))


def delete_card(folder: Path, card_id: str) -> None:
    (Path(folder) / "cards" / f"{card_id}.json").unlink(missing_ok=True)


def save_mechanics(folder: Path, mechanics: list[Mechanic]) -> None:
    _write_json(Path(folder) / "mechanics.json", [_dump(m) for m in mechanics])


def save_cycles(folder: Path, cycles: list[Cycle]) -> None:
    _write_json(Path(folder) / "cycles.json", [_dump(c) for c in cycles])


def save_archetypes(folder: Path, archetypes: list[Archetype]) -> None:
    _write_json(Path(folder) / "archetypes.json", [_dump(a) for a in archetypes])


def save_info(folder: Path, info: SetInfo) -> None:
    _write_json(Path(folder) / "set.json", _dump(info))


def slug(text: str) -> str:
    """"Grizzly Bears!" -> "grizzly-bears" (a file-name-safe id)."""
    import re
    out = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return out or "card"


def new_card_id(project: SetProject, name: str) -> str:
    """A unique id for a new card. Ids never change afterwards, even if the card is renamed."""
    base, taken = slug(name), {c.id for c in project.cards}
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def _read_json(path: Path, default: object) -> object:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def load_project(folder: Path) -> SetProject:
    folder = Path(folder)
    cards_dir = folder / "cards"
    cards = [Card.model_validate(_read_json(p, {})) for p in sorted(cards_dir.glob("*.json"))] \
        if cards_dir.is_dir() else []
    return SetProject(
        info=SetInfo.model_validate(_read_json(folder / "set.json", {})),
        mechanics=[Mechanic.model_validate(m) for m in _read_json(folder / "mechanics.json", [])],
        archetypes=[Archetype.model_validate(a) for a in _read_json(folder / "archetypes.json", [])],
        cycles=[Cycle.model_validate(c) for c in _read_json(folder / "cycles.json", [])],
        cards=cards,
        folder=folder,
    )
