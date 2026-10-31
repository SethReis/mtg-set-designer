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


class AbilityTemplate(BaseModel):
    """One shape of an ability word's ability: the text after "Name — ".
    {slot} is filled per card ({effect}, {cost}, {trigger}, any name); {=phrase} is one of
    the mechanic's shared phrases. E.g. "{cost}: {effect}. Activate only if {=condition}."."""
    label: str = ""
    text: str = ""


class Mechanic(BaseModel):
    id: str
    name: str
    kind: MechanicKind = MechanicKind.KEYWORD
    parameter: str | None = None        # e.g. "cost" for "Cycling {2}"
    reminder_text: str = ""             # may use {param} placeholders
    design_intent: str = ""
    reminder_policy: ReminderPolicy = ReminderPolicy.COMMONS_ONLY
    # other word forms that count as this mechanic ("Wanted", "Wants" for "Want"): used to
    # find, count and rename it, and the first mention on a card gets the reminder text
    forms: list[str] = Field(default_factory=list)
    # ability words (Flurry, Settled): the shared throughline instead of reminder text.
    # Shared wording is written once in `phrases` and used in each variant as {=name}.
    phrases: dict[str, str] = Field(default_factory=dict)
    templates: list[AbilityTemplate] = Field(default_factory=list)
