"""Set-level information."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .card import Rarity


class SetInfo(BaseModel):
    name: str
    code: str
    default_frame: str = "m15"          # see setdesigner.mse.frames
    symbol_path: str | None = None
    artist: str = ""                    # default illustrator credit
    copyright: str = ""
    language: str = "English"
    rarity_slots: dict[Rarity, int] = Field(default_factory=dict)
