"""Our mechanics as MSE keywords, and their reminder-text policies.

A Mechanic becomes one of the set's own MSE keywords:
    keyword   = mechanic.name
    match     = "Bloodpact <atom-param>cost</atom-param>"   (if it has a parameter;
                the parameter names one of the game's keyword parameter types)
    reminder  = the reminder text, with {cost} / {param} written as {param1}
    mode      = custom (keyword), pseudo (ability word), action (keyword action)

Reminder policies become MSE's own per-occurrence switches: a <kw-1> (show) or <kw-0>
(hide) tag around the mechanic's name in the rules text. MSE's keyword expansion
honors these, so the result is exactly what MSE would draw.
    always           -> show
    never            -> hide
    commons_only     -> show on commons
    first_per_color  -> show on the first card (collector-number order) of each of its
                        colors that uses the mechanic
"""
from __future__ import annotations

import re

from ..model import Card, Mechanic, MechanicKind, Rarity, ReminderPolicy, SetProject
from .mapping import MSECard, card_to_mse

MODES = {MechanicKind.KEYWORD: "custom", MechanicKind.ABILITY_WORD: "pseudo",
         MechanicKind.KEYWORD_ACTION: "action"}


def name_pattern(name: str) -> re.Pattern:
    return re.compile(r"(?<![\w])" + re.escape(name) + r"(?![\w])", re.IGNORECASE)


def mechanic_keyword(mechanic: Mechanic) -> dict[str, str]:
    """The MSE keyword definition for a mechanic (keys as in a `keyword:` block)."""
    match = mechanic.name
    reminder = mechanic.reminder_text
    if mechanic.parameter:
        match += f" <atom-param>{mechanic.parameter}</atom-param>"
        reminder = re.sub(r"\{(?:param|" + re.escape(mechanic.parameter) + r")\}", "{param1}", reminder)
    return {"keyword": mechanic.name, "match": match, "reminder": reminder,
            "mode": MODES[mechanic.kind]}


def uses(card: Card, mechanic: Mechanic) -> bool:
    pattern = name_pattern(mechanic.name)
    return any(pattern.search(face.rules_text) for face in card.faces)


def _collector_order(card: Card) -> tuple:
    digits = re.match(r"\d+", card.collector_number)
    return (int(digits.group()) if digits else float("inf"), card.collector_number, card.id)


def reminder_choices(project: SetProject) -> dict[str, dict[str, bool]]:
    """card id -> {mechanic name: show reminder?} for every mechanic the card uses."""
    choices: dict[str, dict[str, bool]] = {card.id: {} for card in project.cards}
    ordered = sorted(project.cards, key=_collector_order)
    for mechanic in project.mechanics:
        seen_colors: set[str] = set()
        for card in ordered:
            if not uses(card, mechanic):
                continue
            policy = mechanic.reminder_policy
            if policy == ReminderPolicy.ALWAYS:
                show = True
            elif policy == ReminderPolicy.NEVER:
                show = False
            elif policy == ReminderPolicy.COMMONS_ONLY:
                show = card.rarity == Rarity.COMMON
            else:                                   # first per color ("C" = colorless)
                colors = set(card.color_identity or "C")
                show = not colors <= seen_colors
                seen_colors |= colors
            choices[card.id][mechanic.name] = show
    return choices


def tag_reminders(text: str, choices: dict[str, bool]) -> str:
    """Put <kw-1>/<kw-0> around each mention of a mechanic, per its choice."""
    for name, show in choices.items():
        letter = "1" if show else "0"
        text = name_pattern(name).sub(lambda m: f"<kw-{letter}>{m.group(0)}</kw-{letter}>", text)
    return text


def project_to_mse(project: SetProject) -> list[MSECard]:
    """All MSE cards of a project, in card order, with reminder policies applied."""
    choices = reminder_choices(project)
    return [mse_card for card in project.cards
            for mse_card in card_to_mse(card, project.info, choices[card.id], project.resolve)]
