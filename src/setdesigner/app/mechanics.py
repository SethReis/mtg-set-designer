"""Working with a set's mechanics: word forms, where they're used, and renaming. No UI.

    suggest_forms("Want")                -> ["Wants", "Wanted", "Wanting"]
    find_uses(project, mechanic)         -> the cards (and faces) that mention it
    usage(project, mechanic)             -> how many cards, by color and rarity
    rename_plan(project, mechanic, "Hunt") -> the rules-text changes a rename would make

A card uses a mechanic when its rules text has the name or one of its word forms as a
whole word (mse.mechanics.words_pattern), so "Wanted" counts for "Want" but "Wantonly"
doesn't. Reminder text is still only drawn after the name itself, as on real cards.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..model import Card, Mechanic, Rarity, SetProject
from ..mse.mechanics import words_pattern
from .overview import COLOR_LABELS, color_key, number_key

VOWELS = "aeiou"
PARAMETER_TYPES = {"": "No parameter", "cost": "Cost ({2}{W})", "mana": "Mana ({G})",
                   "number": "Number (2)", "name": "Name", "action": "Action"}
EXAMPLE_VALUES = {"cost": "{2}", "mana": "{G}", "number": "2", "name": "NAME", "action": "draw a card"}


def suggest_forms(name: str) -> list[str]:
    """Common English forms of a one-word mechanic name (verb or noun):
    Want -> Wants, Wanted, Wanting; Explore -> Explores, Explored, Exploring;
    Ally -> Allies, Allied, Allying; Plot -> Plots, Plotted, Plotting.
    Names of several words get none (add their forms by hand)."""
    word = name.strip()
    if not word or " " in word or not word.isalpha():
        return []
    low = word.lower()
    if low.endswith("e") and not low.endswith("ee"):
        forms = [word + "s", word + "d", word[:-1] + "ing"]
    elif low.endswith("y") and len(low) > 1 and low[-2] not in VOWELS:
        forms = [word[:-1] + "ies", word[:-1] + "ied", word + "ing"]
    elif low.endswith(("s", "x", "z", "ch", "sh")):
        forms = [word + "es", word + "ed", word + "ing"]
    elif (len(low) <= 4 and len(low) >= 3 and low[-1] not in VOWELS + "wxy"
          and low[-2] in VOWELS and low[-3] not in VOWELS):
        forms = [word + "s", word + word[-1] + "ed", word + word[-1] + "ing"]   # plot, plotted
    else:
        forms = [word + "s", word + "ed", word + "ing"]
    return forms


@dataclass
class Use:
    card: Card
    face: int
    sentences: list[str]                 # the sentences of the rules text that mention it


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", text) if s.strip()]


def find_uses(project: SetProject, mechanic: Mechanic) -> list[Use]:
    """Every face that mentions the mechanic, in collector-number order."""
    pattern = words_pattern(mechanic)
    out = []
    for card in sorted(project.cards, key=number_key):
        for index, face in card.iter_faces():
            hits = [s for s in _sentences(face.rules_text) if pattern.search(s)]
            if hits:
                out.append(Use(card, index, hits))
    return out


@dataclass
class Usage:
    cards: int
    by_color: dict[str, int] = field(default_factory=dict)     # COLOR_LABELS keys
    by_rarity: dict[str, int] = field(default_factory=dict)    # Rarity values


def usage(project: SetProject, mechanic: Mechanic) -> Usage:
    cards = {use.card.id: use.card for use in find_uses(project, mechanic)}.values()
    by_color = {k: 0 for k in COLOR_LABELS}
    by_rarity = {r.value: 0 for r in Rarity}
    for card in cards:
        by_color[color_key(card)] += 1
        by_rarity[card.rarity.value] += 1
    return Usage(len(cards), {k: n for k, n in by_color.items() if n},
                 {k: n for k, n in by_rarity.items() if n})


def mechanic_ids(project: SetProject, card: Card) -> list[str]:
    """The ids of the mechanics a card uses (Card.mechanics)."""
    return [m.id for m in project.mechanics
            if any(words_pattern(m).search(face.rules_text) for face in card.faces)]


# ---------------------------------------------------------------------- renaming

@dataclass
class Change:
    card: Card
    face: int
    before: str
    after: str


def renamed_forms(mechanic: Mechanic, new_name: str) -> dict[str, str]:
    """Old word -> new word: the name, and each form that extends it (Wanted -> Hunted
    for Want -> Hunt; forms built differently stay as they are)."""
    old = mechanic.name
    mapping = {old.lower(): new_name}
    new_forms = dict(zip((f.lower() for f in suggest_forms(old)), suggest_forms(new_name)))
    for form in mechanic.forms:
        low = form.lower()
        if low in new_forms:                       # a regular form: same kind of ending
            mapping[low] = new_forms[low]
        elif low.startswith(old.lower()):          # name + something else
            mapping[low] = new_name + form[len(old):]
    return mapping


def _same_case(word: str, replacement: str) -> str:
    if word.isupper() and len(word) > 1:
        return replacement.upper()
    if word[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement[:1].lower() + replacement[1:]


def rename_plan(project: SetProject, mechanic: Mechanic, new_name: str) -> list[Change]:
    """The rules-text changes renaming the mechanic would make on each card."""
    mapping = renamed_forms(mechanic, new_name)
    pattern = words_pattern(mechanic)
    changes = []
    for card in sorted(project.cards, key=number_key):
        for index, face in card.iter_faces():
            after = pattern.sub(lambda m: _same_case(m.group(0), mapping.get(m.group(0).lower(), m.group(0))),
                                face.rules_text)
            if after != face.rules_text:
                changes.append(Change(card, index, face.rules_text, after))
    return changes


def new_forms_after_rename(mechanic: Mechanic, new_name: str) -> list[str]:
    mapping = renamed_forms(mechanic, new_name)
    return [_same_case(f, mapping.get(f.lower(), f)) for f in mechanic.forms]


def reminder_preview(mechanic: Mechanic) -> str:
    """How the mechanic reads on a card, with an example parameter and its reminder text."""
    value = EXAMPLE_VALUES.get(mechanic.parameter or "", "")
    head = f"{mechanic.name} {value}".strip()
    reminder = mechanic.reminder_text
    if mechanic.parameter:
        reminder = re.sub(r"\{(?:param|param1|" + re.escape(mechanic.parameter) + r")\}", value, reminder)
    return f"{head} ({reminder})" if reminder.strip() else head
