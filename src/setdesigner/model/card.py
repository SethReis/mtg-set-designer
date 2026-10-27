"""Cards and their faces.

A card is one record holding all of its faces (front, and back for transform /
modal double-faced cards). Analysis that treats faces independently uses
`Card.iter_faces()` or `project.iter_faces()`.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Iterator

from pydantic import BaseModel, Field


class Rarity(str, Enum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    MYTHIC = "mythic"
    SPECIAL = "special"


class Status(str, Enum):
    IDEA = "idea"
    DRAFT = "draft"
    PLAYTESTED = "playtested"
    FINAL = "final"


class Layout(str, Enum):
    NORMAL = "normal"
    TRANSFORM = "transform"
    MDFC = "mdfc"
    # later: adventure, split, flip (two text sets on one face)


class FaceRole(str, Enum):
    FRONT = "front"
    BACK = "back"


COLORS = "WUBRG"
COLOR_NAMES = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


class ArtCrop(BaseModel):
    """Which part of the art shows in the frame's art box (see setdesigner.app.art).
    x, y: where the crop's centre sits in the image (0-1); zoom >= 1, relative to the
    largest crop of the box's shape that fits the image."""
    x: float = 0.5
    y: float = 0.5
    zoom: float = 1.0


class Face(BaseModel):
    name: str
    role: FaceRole = FaceRole.FRONT
    mana_cost: str = ""                 # "{2}{W}{W}"
    color_indicator: str = ""           # e.g. "R" or "red, green"; transform backs have no cost
    type_line: str = ""                 # "Legendary Creature — Elf Warrior"
    rules_text: str = ""                # keyword lines like "Cycling {2}" match mechanics.json
    flavor_text: str = ""
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    art_path: str | None = None         # relative to the set folder: "assets/art/<card>.png"
    art_crop: ArtCrop | None = None     # None: centred, filling the art box
    artist: str = ""
    frame: str | None = None            # overrides the card's frame for this face

    def colors(self) -> set[str]:
        """Colors from the mana cost and color indicator (as letters W/U/B/R/G)."""
        found: set[str] = set()
        for symbol in re.findall(r"\{([^}]*)\}", self.mana_cost):   # "{W/U}" counts both
            found.update(c for c in symbol if c in COLORS)
        indicator = self.color_indicator
        for name, letter in COLOR_NAMES.items():
            if name in indicator.lower():
                found.add(letter)
        found.update(c for c in indicator if c in COLORS)
        return found


class Card(BaseModel):
    id: str                             # stable slug, also the file name
    layout: Layout = Layout.NORMAL
    faces: list[Face]
    rarity: Rarity = Rarity.COMMON
    collector_number: str = ""
    frame: str | None = None            # card default; None = the set's default frame
    sheet: str | None = None            # bonus sheet name; None = main set
    archetypes: list[str] = Field(default_factory=list)
    mechanics: list[str] = Field(default_factory=list)   # derived/cached
    status: Status = Status.IDEA
    notes: str = ""

    def iter_faces(self) -> Iterator[tuple[int, Face]]:
        return iter(enumerate(self.faces))

    def frame_for(self, face_index: int, set_default: str) -> str:
        """The frame a face uses: face override, else card default, else the set's."""
        return self.faces[face_index].frame or self.frame or set_default

    @property
    def color_identity(self) -> str:
        """Union of the faces' colors, in WUBRG order."""
        found = set().union(*(face.colors() for face in self.faces))
        return "".join(c for c in COLORS if c in found)
