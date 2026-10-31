"""Cycles: a family of similar cards across colors (dual lands, the five Dragonstorms,
Bloomburrow's Duos). A cycle keeps a shared template and its members; the generated cards
are ordinary cards that point back to it (Card.cycle)."""
from __future__ import annotations

from pydantic import BaseModel, Field

# the card fields a template can set (face fields, then card fields)
TEMPLATE_FACE_FIELDS = ("name", "mana_cost", "type_line", "rules_text", "flavor_text", "power",
                        "toughness")
TEMPLATE_CARD_FIELDS = ("rarity", "frame")
TEMPLATE_FIELDS = TEMPLATE_FACE_FIELDS + TEMPLATE_CARD_FIELDS


class CycleTemplate(BaseModel):
    """What every member shares, with color tokens ({c}, {color}, {basic}, {group}, …;
    see setdesigner.app.cycles). Empty fields are left empty on the cards."""
    name: str = ""
    mana_cost: str = ""
    type_line: str = ""
    rules_text: str = ""
    flavor_text: str = ""
    power: str = ""
    toughness: str = ""
    rarity: str = "common"
    frame: str = ""                      # "" = the set's default frame
    tag_archetypes: bool = False         # tag each card with the archetype of its colors


class CycleMember(BaseModel):
    colors: str = ""                     # "W", "WU", "WUB" (WUBRG order); "" = colorless
    card_id: str | None = None           # None until generated (or after the card was deleted)
    overrides: dict[str, str] = Field(default_factory=dict)   # field -> this member's own text


class Cycle(BaseModel):
    id: str
    name: str
    grouping: str = "mono"               # a key of app.cycles.GROUPINGS, or "custom" / "numbered"
    members: list[CycleMember] = Field(default_factory=list)
    template: CycleTemplate = Field(default_factory=CycleTemplate)
    notes: str = ""
