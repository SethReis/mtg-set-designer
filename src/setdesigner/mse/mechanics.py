"""Our mechanics as MSE keywords, and their reminder-text policies.

A Mechanic becomes one of the set's own MSE keywords:
    keyword   = mechanic.name
    match     = "Bloodpact <atom-param>cost</atom-param>"   (if it has a parameter;
                the parameter names one of the game's keyword parameter types)
    reminder  = the reminder text, with {cost} / {param} written as {param1}
    mode      = custom (keyword), pseudo (ability word), action (keyword action)

Its word forms ("Wanted" for "Want") become keywords too, with the same reminder text,
so a card that only says "Wanted" can still show it (mechanics without a parameter only:
a form has no value to fill in).

Reminder policies become MSE's own per-occurrence switches: a <kw-1> (show) or <kw-0>
(hide) tag around each mention of the mechanic (its name or a form) in the rules text.
Only the first mention on a card gets the card's choice; later ones are hidden, as on
real cards. MSE's keyword expansion honors these, so the result is exactly what MSE
would draw.
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


def mechanic_keywords(mechanic: Mechanic) -> list[dict[str, str]]:
    """All MSE keywords for a mechanic: its name, plus each word form when it has no
    parameter (so "Wanted" expands to the same reminder text as "Want")."""
    out = [mechanic_keyword(mechanic)]
    if not mechanic.parameter:
        for form in mechanic.forms:
            if form.strip() and form.lower() != mechanic.name.lower():
                out.append({**out[0], "keyword": form, "match": form})
    return out


def _words_regex(words) -> re.Pattern:
    words = sorted(set(words) - {""}, key=len, reverse=True)
    return re.compile(r"(?<![\w])(?:" + "|".join(re.escape(w) for w in words) + r")(?![\w])",
                      re.IGNORECASE)


def words_pattern(mechanic: Mechanic) -> re.Pattern:
    """The mechanic's name or any of its word forms, as whole words, longest first."""
    return _words_regex([mechanic.name, *mechanic.forms])


def uses(card: Card, mechanic: Mechanic) -> bool:
    """Whether the card mentions the mechanic (its name or one of its word forms)."""
    pattern = words_pattern(mechanic)
    return any(pattern.search(face.rules_text) for face in card.faces)


def _collector_order(card: Card) -> tuple:
    digits = re.match(r"\d+", card.collector_number)
    return (int(digits.group()) if digits else float("inf"), card.collector_number, card.id)


def reminder_choices(project: SetProject) -> dict[str, dict[str, bool]]:
    """card id -> {mechanic name: show reminder?} for every mechanic the card uses.
    A card's own override (Card.reminders) wins over the mechanic's policy."""
    choices: dict[str, dict[str, bool]] = {card.id: {} for card in project.cards}
    ordered = sorted(project.cards, key=_collector_order)
    for mechanic in project.mechanics:
        seen_colors: set[str] = set()
        for card in ordered:
            if not uses(card, mechanic):
                continue
            policy = mechanic.reminder_policy
            if mechanic.id in card.reminders:       # the card's own choice wins
                show = card.reminders[mechanic.id]
                if policy == ReminderPolicy.FIRST_PER_COLOR:
                    seen_colors |= set(card.color_identity or "C")
            elif policy == ReminderPolicy.ALWAYS:
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


def tag_reminders(text: str, choices: dict[str, bool],
                  forms: dict[str, list[str]] | None = None) -> str:
    """Put <kw-1>/<kw-0> around each mention of a mechanic (its name or a word form from
    `forms`): the first mention gets the card's choice, later ones are hidden."""
    for name, show in choices.items():
        first = [True]

        def tag(m: re.Match) -> str:
            letter = "1" if show and first[0] else "0"
            first[0] = False
            return f"<kw-{letter}>{m.group(0)}</kw-{letter}>"
        text = _words_regex([name, *(forms or {}).get(name, [])]).sub(tag, text)
    return text


def project_to_mse(project: SetProject) -> list[MSECard]:
    """All MSE cards of a project, in card order, with reminder policies applied."""
    choices = reminder_choices(project)
    forms = {m.name: [f for f in m.forms if f.strip()] for m in project.mechanics if not m.parameter}
    return [mse_card for card in project.cards
            for mse_card in card_to_mse(card, project.info, choices[card.id], project.resolve, forms)]
