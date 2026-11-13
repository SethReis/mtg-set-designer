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


def _decide(policy: ReminderPolicy, override: bool | None, card: Card, seen_colors: set[str]) -> bool:
    """One card's reminder choice: its own override, else the policy (updates seen_colors
    for first-per-color)."""
    if override is not None:                # the card's own choice wins
        if policy == ReminderPolicy.FIRST_PER_COLOR:
            seen_colors |= set(card.color_identity or "C")
        return override
    if policy == ReminderPolicy.ALWAYS:
        return True
    if policy == ReminderPolicy.NEVER:
        return False
    if policy == ReminderPolicy.COMMONS_ONLY:
        return card.rarity == Rarity.COMMON
    colors = set(card.color_identity or "C")    # first per color ("C" = colorless)
    show = not colors <= seen_colors
    seen_colors |= colors
    return show


def reminder_choices(project: SetProject, keywords=None, all_keywords: bool = False) -> dict[str, dict[str, bool]]:
    """card id -> {mechanic or keyword name: show reminder?} for every set mechanic and
    every Magic keyword (mse.game_keywords; `keywords` defaults to the game's) the card
    uses. A card's own override (Card.reminders) wins over the policy. A keyword is only
    listed where its choice differs from what MSE does by default (gk.mse_default), so
    MSE's own output is untouched otherwise; `all_keywords` lists every one."""
    from . import game_keywords as gk
    choices: dict[str, dict[str, bool]] = {card.id: {} for card in project.cards}
    ordered = sorted(project.cards, key=_collector_order)
    for mechanic in project.mechanics:
        seen_colors: set[str] = set()
        for card in ordered:
            if not uses(card, mechanic):
                continue
            if mechanic.kind == MechanicKind.ABILITY_WORD or not mechanic.reminder_text.strip():
                show = False                        # nothing to show (ability words have none)
            else:
                show = _decide(mechanic.reminder_policy, card.reminders.get(mechanic.id), card, seen_colors)
            choices[card.id][mechanic.name] = show
    keywords = gk.game_keywords() if keywords is None else keywords
    seen: dict[str, set[str]] = {}
    for card in ordered:
        for kw in gk.used(card, project, keywords):
            show = _decide(gk.policy(project, kw), card.reminders.get(kw.card_key), card,
                           seen.setdefault(kw.key, set()))
            if all_keywords or show != gk.mse_default(kw) or gk.custom_text(project.info, kw, ""):
                choices[card.id][kw.name] = show
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
    from . import game_keywords as gk
    choices = reminder_choices(project)
    forms = {m.name: [f for f in m.forms if f.strip()] for m in project.mechanics if not m.parameter}
    for kw in gk.game_keywords():               # "Explore" is "explores" on cards
        if kw.literal.lower() != kw.name.lower():
            forms.setdefault(kw.name, [kw.literal])
    return [mse_card for card in project.cards
            for mse_card in card_to_mse(card, project.info, choices[card.id], project.resolve, forms,
                                        custom_reminders(project, card))]


def custom_reminders(project: SetProject, card: Card) -> dict:
    """keyword name -> (GameKeyword, reminder text) for the Magic keywords on the card whose
    reminder text is replaced (the set's own text or our correction: game_keywords)."""
    from . import game_keywords as gk
    text = "\n".join(face.rules_text for face in card.faces)
    out = {}
    for kw in gk.used(card, project):
        custom = gk.custom_text(project.info, kw, text)
        if custom:
            out[kw.name] = (kw, custom)
    return out
