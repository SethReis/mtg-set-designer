"""Set-level information."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .card import Rarity
from .mechanic import ReminderPolicy


class CheckSetting(BaseModel):
    """One set-health check's settings (see setdesigner.app.health.checks); None threshold
    = the check's default."""
    enabled: bool = True
    threshold: float | None = None


class SetInfo(BaseModel):
    name: str
    code: str
    default_frame: str = "m15"          # see setdesigner.mse.frames
    symbol_path: str | None = None
    artist: str = ""                    # default illustrator credit
    copyright: str = ""
    language: str = "English"
    rarity_slots: dict[Rarity, int] = Field(default_factory=dict)
    health: dict[str, CheckSetting] = Field(default_factory=dict)   # check id -> settings
    balance: dict[str, float] = Field(default_factory=dict)         # norm key -> value (app.balance.norms)
    # Magic's own keywords (mse.game_keywords): lower-case name -> reminder policy, where
    # the set changes the default
    keyword_reminders: dict[str, ReminderPolicy] = Field(default_factory=dict)
    # Magic keywords whose reminder text the set replaces: lower-case name -> text ({N} = value)
    keyword_text: dict[str, str] = Field(default_factory=dict)
