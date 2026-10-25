"""User-defined archetypes (any color identity, or none), tagged onto cards."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .card import Rarity


class Archetype(BaseModel):
    id: str
    name: str
    colors: str = ""                    # "WU", "BRG", "" for colorless/none
    description: str = ""
    key_mechanics: list[str] = Field(default_factory=list)    # mechanic ids
    targets: dict[Rarity, int] = Field(default_factory=dict)  # wanted card count per rarity
