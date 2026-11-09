"""The set's skeleton: the slots a set plans to fill, kept apart from the cards (slots.json).

A skeleton is a grid of slots by column (a color, a color set such as "WU", "C" for
colorless, "L" for land) and rarity, each slot optionally describing the card it wants
(type, mana value, role, archetype, a note) and linked to the card that fills it. See
setdesigner.app.skeleton for generating, adjusting and filling it.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .card import Rarity

ANY = "any"                      # the rarity key of a cube's counts (cubes have no rarities)


class Slot(BaseModel):
    id: str                          # its label, unique in the skeleton: "W-C03", "WU-U01", "B-07" (cube)
    column: str                      # "W" "U" "B" "R" "G", a color set "WU" / "WUB", "C" colorless, "L" land
    rarity: Rarity | None = None     # None in a cube
    types: str = ""                  # the type line's left part it wants: "Creature", "Instant"
    mana_value: int | None = None
    role: str | None = None          # a Health role id (app/health/roles.ROLES)
    archetype: str | None = None     # an archetype id
    note: str = ""
    card_id: str | None = None       # the card that fills it
    cycle: str | None = None         # the cycle whose card was placed here

    @property
    def annotated(self) -> bool:
        return bool(self.types or self.mana_value is not None or self.role or self.note)


class Skeleton(BaseModel):
    preset: str = "play_booster"     # see app.skeleton.PRESETS
    columns: list[str] = Field(default_factory=list)                 # display order
    counts: dict[str, dict[str, int]] = Field(default_factory=dict)  # column -> rarity (or ANY) -> slots
    slots: list[Slot] = Field(default_factory=list)

    def slot(self, slot_id: str) -> Slot:
        return next(s for s in self.slots if s.id == slot_id)

    def slot_of(self, card_id: str) -> Slot | None:
        return next((s for s in self.slots if s.card_id == card_id), None)
