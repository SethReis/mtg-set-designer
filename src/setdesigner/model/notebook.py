"""The design notebook: ideas caught before they are cards (card and mechanic ideas, loose
thoughts, design problems), on a board of lanes. An idea that became a card, a filled
slot or a mechanic keeps a link to it. Saved as notebook.json (docs/notebook.md)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

IdeaKind = Literal["card", "mechanic", "thought", "problem"]
Lane = Literal["inbox", "promising", "used", "parked"]
LANES: dict[str, str] = {"inbox": "Inbox", "promising": "Promising", "used": "Used", "parked": "Parked"}
KINDS: dict[str, str] = {"card": "Card idea", "mechanic": "Mechanic idea", "thought": "Thought",
                         "problem": "Design problem"}


class IdeaSketch(BaseModel):
    """A rough card: any of it may be empty."""
    name: str = ""
    mana_cost: str = ""
    type_line: str = ""
    rules_text: str = ""
    power: str = ""
    toughness: str = ""

    def empty(self) -> bool:
        return not any(self.model_dump().values())


class IdeaLink(BaseModel):
    kind: Literal["card", "slot", "mechanic"]
    id: str


class Idea(BaseModel):
    id: str
    kind: IdeaKind = "card"
    title: str = ""
    body: str = ""
    lane: Lane = "inbox"
    tags: list[str] = Field(default_factory=list)
    colors: str = ""                     # WUBRG letters
    archetypes: list[str] = Field(default_factory=list)
    sketch: IdeaSketch = Field(default_factory=IdeaSketch)
    author: str = ""
    created: str = ""                    # ISO times
    updated: str = ""
    links: list[IdeaLink] = Field(default_factory=list)
