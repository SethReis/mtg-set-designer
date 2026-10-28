"""Mechanics are first-class: editing one updates every card that uses it.
Reminder text is rendered from the definition, never stored on cards."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class MechanicKind(str, Enum):
    KEYWORD = "keyword"                 # Flying, Cycling {2}
    ABILITY_WORD = "ability_word"       # Landfall — ...
    KEYWORD_ACTION = "keyword_action"   # Scry 2


class ReminderPolicy(str, Enum):
    ALWAYS = "always"
    COMMONS_ONLY = "commons_only"
    FIRST_PER_COLOR = "first_per_color"
    NEVER = "never"


class Mechanic(BaseModel):
    id: str
    name: str
    kind: MechanicKind = MechanicKind.KEYWORD
    parameter: str | None = None        # e.g. "cost" for "Cycling {2}"
    reminder_text: str = ""             # may use {param} placeholders
    design_intent: str = ""
    reminder_policy: ReminderPolicy = ReminderPolicy.COMMONS_ONLY
    # other word forms that count as this mechanic ("Wanted", "Wants" for "Want"): used to
    # find, count and rename it on cards. Reminder text goes on the name itself only.
    forms: list[str] = Field(default_factory=list)
