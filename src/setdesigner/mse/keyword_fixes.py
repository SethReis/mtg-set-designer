"""Corrections to the MSE game's reminder text for Magic keywords (mse.game_keywords).

The game's templates were written for older wording and sometimes read wrong on modern
cards: Explore looks for "this explores", so "When this creature enters, it explores."
got "put a +1/+1 counter on that creature". Each fix is the reminder text to use instead,
or a function of the card's rules text when the right words depend on it. {N} is the
keyword's value. tools/keyword_survey.py lists the game's texts that look wrong.
"""
from __future__ import annotations

import re
from typing import Callable

def _which(rules_text: str, verb: str) -> str:
    """ "this creature" when the card does it itself ("it explores"), else "that creature"."""
    self_ = re.search(r"\b(?:it|this creature|this permanent|CARDNAME) " + verb + r"\b", rules_text, re.IGNORECASE)
    return "this creature" if self_ else "that creature"


def _explore(rules_text: str) -> str:
    return ("Reveal the top card of your library. Put that card into your hand if it's a land. "
            f"Otherwise, put a +1/+1 counter on {_which(rules_text, 'explores')}, then put the card "
            "back or put it into your graveyard.")


def _connives(rules_text: str) -> str:
    return ("Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 "
            f"counter on {_which(rules_text, 'connives')}.")


def _connives_n(rules_text: str) -> str:
    return ("Draw {N} cards, then discard {N} cards. Put a +1/+1 counter on "
            f"{_which(rules_text, 'connives')} for each nonland card discarded this way.")


FIXES: dict[str, str | Callable[[str], str]] = {
    "explore": _explore,
    "connives": _connives,
    "connives n": _connives_n,
}
