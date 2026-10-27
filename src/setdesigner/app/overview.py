"""The set overview's logic: which group a card belongs to, grouping, the matrix, filters,
sorting and targets. No UI code.

    groups = group(cards, FACTORS["color"], project)          # rows mode
    m = matrix(cards, FACTORS["color"], FACTORS["rarity"], project)
    cards = apply(Filters(text="flying", rarities={"common"}), project.cards)

A *factor* is something to group by. For each card it gives one or more group keys
(a card tagged with two archetypes is in both groups); `options(project)` lists every
key in display order, so empty groups show up too (a gap is what you want to see).
Like HANDOFF's set-health rules, analysis looks at the front face.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from ..model import Card, Rarity, SetProject, Status
from ..mse.mapping import split_type_line

COLOR_LABELS = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green",
                "M": "Multicolor", "C": "Colorless", "L": "Land"}
# Checked in this order: an artifact creature is a Creature, a land creature too
TYPE_PRECEDENCE = ["Creature", "Planeswalker", "Battle", "Instant", "Sorcery", "Land",
                   "Artifact", "Enchantment"]
TYPE_ORDER = ["Creature", "Instant", "Sorcery", "Artifact", "Enchantment", "Planeswalker",
              "Battle", "Land"]
OTHER_TYPE = "Other"
MANA_VALUES = ["0", "1", "2", "3", "4", "5", "6", "7+"]
NO_ARCHETYPE = ""


# ------------------------------------------------------------------ card facts

def main_types(card: Card) -> list[str]:
    """The front face's card types, e.g. ["Legendary", "Artifact", "Creature"]."""
    return split_type_line(card.faces[0].type_line)[0].split()


def card_type(card: Card) -> str:
    """One type per card for grouping (see TYPE_PRECEDENCE)."""
    types = {t.capitalize() for t in main_types(card)}
    return next((t for t in TYPE_PRECEDENCE if t in types), OTHER_TYPE)


def color_key(card: Card) -> str:
    """W/U/B/R/G, M (multicolor), C (colorless) or L (land)."""
    if card_type(card) == "Land":
        return "L"
    colors = "".join(sorted(card.faces[0].colors(), key="WUBRG".index))
    return colors if len(colors) == 1 else "M" if colors else "C"


def mana_value(cost: str) -> int:
    """"{2}{W}{W}" -> 4. X counts 0, hybrid {W/U} and Phyrexian {W/P} count 1, {2/W} 2."""
    total = 0
    for symbol in re.findall(r"\{([^}]*)\}", cost):
        first = symbol.split("/")[0]
        if first.isdigit():
            total += int(first)
        elif first.upper() not in ("X", "Y", "Z"):
            total += 1
    return total


def mana_value_key(card: Card) -> str:
    value = mana_value(card.faces[0].mana_cost)
    return str(value) if value < 7 else "7+"


def number_key(card: Card) -> tuple:
    """Collector-number order: 1, 2, 10, then non-numeric numbers, then unnumbered."""
    digits = re.match(r"\d+", card.collector_number)
    return (int(digits.group()) if digits else float("inf"), card.collector_number, card.id)


def card_text(card: Card) -> str:
    """What text search looks through (all faces)."""
    return " ".join(f"{f.name} {f.type_line} {f.rules_text}" for f in card.faces).lower()


def matches_text(card: Card, text: str) -> bool:
    haystack = card_text(card)
    return all(word in haystack for word in text.lower().split())


# ------------------------------------------------------------------ factors

@dataclass(frozen=True)
class Factor:
    name: str
    label: str
    keys_of: Callable[[Card], list[str]]                      # the card's group keys
    options: Callable[[SetProject], list[tuple[str, str]]]    # (key, label) in display order


def _archetype_keys(card: Card, project: SetProject) -> list[str]:
    known = {a.id for a in project.archetypes}
    keys = [a for a in card.archetypes if a in known]
    return keys or [NO_ARCHETYPE]


FACTORS: dict[str, Factor] = {
    "color": Factor("color", "Color", lambda c: [color_key(c)],
                    lambda p: list(COLOR_LABELS.items())),
    "rarity": Factor("rarity", "Rarity", lambda c: [c.rarity.value],
                     lambda p: [(r.value, r.value.title()) for r in Rarity]),
    "archetype": Factor("archetype", "Archetype", lambda c: [],   # needs the project: see keys()
                        lambda p: [(a.id, a.name) for a in p.archetypes] + [(NO_ARCHETYPE, "No archetype")]),
    "type": Factor("type", "Card type", lambda c: [card_type(c)],
                   lambda p: [(t, t) for t in TYPE_ORDER] + [(OTHER_TYPE, OTHER_TYPE)]),
    "mana_value": Factor("mana_value", "Mana value", lambda c: [mana_value_key(c)],
                         lambda p: [(v, f"Mana value {v}") for v in MANA_VALUES]),
    "status": Factor("status", "Status", lambda c: [c.status.value],
                     lambda p: [(s.value, s.value.title()) for s in Status]),
}
# shown only when a card is in them (nobody needs an empty "Other" or "No archetype")
HIDE_WHEN_EMPTY = {OTHER_TYPE, NO_ARCHETYPE}


def keys(card: Card, factor: Factor, project: SetProject) -> list[str]:
    if factor.name == "archetype":
        return _archetype_keys(card, project)
    return factor.keys_of(card)


# ------------------------------------------------------------------ grouping

@dataclass
class Group:
    key: str
    label: str
    cards: list[Card]


def group(cards: list[Card], factor: Factor, project: SetProject) -> list[Group]:
    """Cards split into the factor's groups, in display order (cards keep their order)."""
    groups = {key: Group(key, label, []) for key, label in factor.options(project)}
    for card in cards:
        for key in keys(card, factor, project):
            groups[key].cards.append(card)
    return [g for g in groups.values() if g.cards or g.key not in HIDE_WHEN_EMPTY]


@dataclass
class Matrix:
    rows: list[tuple[str, str]]                 # (key, label)
    columns: list[tuple[str, str]]
    cells: dict[tuple[str, str], list[Card]] = field(default_factory=dict)

    def cell(self, row: str, column: str) -> list[Card]:
        return self.cells.get((row, column), [])


def matrix(cards: list[Card], rows: Factor, columns: Factor, project: SetProject) -> Matrix:
    """Cards in a grid: rows by one factor, columns by another."""
    out = Matrix(rows.options(project), columns.options(project))
    for card in cards:
        for r in keys(card, rows, project):
            for c in keys(card, columns, project):
                out.cells.setdefault((r, c), []).append(card)

    def used(options, index):
        return [(k, label) for k, label in options
                if k not in HIDE_WHEN_EMPTY or any(key[index] == k for key in out.cells)]
    out.rows, out.columns = used(out.rows, 0), used(out.columns, 1)
    return out


STACK_MAX = 12                   # cards per stack before a group splits into more stacks


def stacks(cards: list[Card], max_len: int = STACK_MAX) -> list[list[Card]]:
    """Split a group into stacks of at most max_len cards, as evenly as possible
    (25 cards, at most 12 each -> 9 + 8 + 8, not 12 + 12 + 1)."""
    if not cards:
        return []
    count = -(-len(cards) // max_len)              # stacks needed (rounded up)
    size, extra = divmod(len(cards), count)
    out, start = [], 0
    for i in range(count):
        end = start + size + (1 if i < extra else 0)
        out.append(cards[start:end])
        start = end
    return out


# ------------------------------------------------------------------ filters, sorting

@dataclass
class Filters:
    text: str = ""
    statuses: set[str] = field(default_factory=set)       # empty = all
    rarities: set[str] = field(default_factory=set)
    colors: set[str] = field(default_factory=set)         # color_key values

    @property
    def active(self) -> bool:
        return bool(self.text.strip() or self.statuses or self.rarities or self.colors)


def apply(filters: Filters, cards: list[Card]) -> list[Card]:
    return [c for c in cards
            if (not filters.text.strip() or matches_text(c, filters.text))
            and (not filters.statuses or c.status.value in filters.statuses)
            and (not filters.rarities or c.rarity.value in filters.rarities)
            and (not filters.colors or color_key(c) in filters.colors)]


SORTS: dict[str, tuple[str, Callable[[Card], tuple]]] = {
    "number": ("Collector number", number_key),
    "name": ("Name", lambda c: (c.faces[0].name.lower(), number_key(c))),
    "mana_value": ("Mana value", lambda c: (mana_value(c.faces[0].mana_cost), number_key(c))),
}


def sort(cards: list[Card], by: str = "number") -> list[Card]:
    return sorted(cards, key=SORTS[by][1])


# ------------------------------------------------------------------ targets

def target(project: SetProject, factor: Factor, key: str,
           column: Factor | None = None, column_key: str | None = None) -> int | None:
    """How many cards the user wants in a group (or matrix cell), if they said so.
    Rarity groups: SetInfo.rarity_slots. Archetype groups: the archetype's targets summed;
    an archetype x rarity cell: its target for that rarity. Anything else: None."""
    pairs = {factor.name: key}
    if column is not None:
        pairs[column.name] = column_key
    archetype = next((a for a in project.archetypes if a.id == pairs.get("archetype")), None)
    rarity = pairs.get("rarity")
    if column is not None and set(pairs) != {"archetype", "rarity"}:
        return None                                    # only archetype x rarity cells
    if archetype is not None:
        if rarity is not None:
            return archetype.targets.get(Rarity(rarity))
        return sum(archetype.targets.values()) if archetype.targets else None
    if rarity is not None and column is None:
        return project.info.rarity_slots.get(Rarity(rarity))
    return None
