"""What a print holds: which faces, how many copies, in what order (no rendering).

    options = PrintOptions.from_dict(settings.print_options)
    faces = print_faces(cards, options)     # flat, in the order they go on the sheets

Every face is cut out as its own card (printing is single-sided), so a print is just a
list of faces. Cards are sorted first, then each is repeated by its copies (copies stay
together), then each copy expands into its faces, front then back.

Copies: *one of each* (a cube) prints every card once. *By rarity* prints each card
`copies[rarity]` times, unless the card says otherwise (Card.print_copies).
"""
from __future__ import annotations

import locale
from dataclasses import asdict, dataclass, field, fields
from typing import Callable

from ..app.overview import color_key, number_key
from ..model import Card, Rarity

DEFAULT_COPIES = {Rarity.COMMON.value: 4, Rarity.UNCOMMON.value: 2, Rarity.RARE.value: 1,
                  Rarity.MYTHIC.value: 1, Rarity.SPECIAL.value: 1}
COLOR_ORDER = "WUBRGMCL"                # color_key values
RARITY_ORDER = [r.value for r in Rarity]

SORTS: dict[str, tuple[str, Callable[[Card], tuple]]] = {
    "number": ("Collector number", number_key),
    "color": ("Color", lambda c: (COLOR_ORDER.index(color_key(c)), number_key(c))),
    "rarity": ("Rarity", lambda c: (RARITY_ORDER.index(c.rarity.value), number_key(c))),
}
DISTRIBUTIONS = {"cube": "One of each", "rarity": "By rarity"}
STYLES = {"rendered": "Rendered", "friendly": "Printer-friendly"}
BLEEDS = (0.0, 1.0, 3.0)                # millimetres


def default_paper() -> str:
    """Letter where it is the usual paper (the US and Canada), else A4."""
    try:
        name = " ".join(filter(None, locale.getlocale())) or ""
    except ValueError:
        name = ""
    return "letter" if any(p in name for p in ("United States", "Canada", "en_US", "en_CA")) else "a4"


@dataclass
class PrintOptions:
    scope: str = "set"                  # "set", or "filter": the overview's filtered cards
    distribution: str = "cube"          # see DISTRIBUTIONS
    copies: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_COPIES))  # rarity -> copies
    sort: str = "number"                # see SORTS
    style: str = "rendered"             # see STYLES
    paper: str = field(default_factory=default_paper)    # export.sheet.PAPERS
    bleed_mm: float = 0.0
    spacing_mm: float = 0.0             # extra space between cards
    crop_marks: bool = True
    labels: bool = False                # small "CODE 012 · front" under each card

    @classmethod
    def from_dict(cls, data: dict | None) -> "PrintOptions":
        """From saved settings; unknown keys and bad values fall back to the defaults."""
        options = cls()
        names = {f.name for f in fields(cls)}
        for key, value in (data or {}).items():
            if key not in names:
                continue
            default = getattr(options, key)
            try:
                if key == "copies":
                    value = {**default, **{str(k): max(0, int(v)) for k, v in dict(value).items()}}
                elif isinstance(default, bool):
                    value = bool(value)
                elif isinstance(default, float):
                    value = max(0.0, float(value))
                else:
                    value = str(value)
            except (TypeError, ValueError):
                continue
            setattr(options, key, value)
        if options.distribution not in DISTRIBUTIONS:
            options.distribution = "cube"
        if options.sort not in SORTS:
            options.sort = "number"
        if options.style not in STYLES:
            options.style = "rendered"
        return options

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PrintFace:
    card: Card
    face: int                           # index into card.faces
    copy: int                           # 0 for the first copy

    @property
    def key(self) -> tuple[str, int]:
        """Which picture this is (copies share it)."""
        return self.card.id, self.face


def copies(card: Card, options: PrintOptions) -> int:
    if options.distribution == "cube":
        return 1
    if card.print_copies is not None:
        return max(0, card.print_copies)
    return max(0, options.copies.get(card.rarity.value, 1))


def print_faces(cards: list[Card], options: PrintOptions) -> list[PrintFace]:
    out = []
    for card in sorted(cards, key=SORTS[options.sort][1]):
        for copy in range(copies(card, options)):
            out.extend(PrintFace(card, face, copy) for face in range(len(card.faces)))
    return out
