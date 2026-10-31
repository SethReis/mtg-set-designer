"""Set statistics for the health page: curves, ratios, roles per color, mechanic spread,
archetype coverage, cycles and complexity. Front faces are analyzed (HANDOFF's default).

Colors are the overview's groups (app.overview.color_key): W U B R G, M (multicolor),
C (colorless), L (land).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ...model import Card, MechanicKind, Rarity, SetProject
from ..overview import COLOR_LABELS, MANA_VALUES, card_type, color_key, mana_value, mana_value_key
from .roles import ROLES, _keyword_lines, plain_text, roles

COLORS = list(COLOR_LABELS)                      # W U B R G M C L
RARITIES = [r.value for r in Rarity]


def cards_at(project: SetProject, rarity: str | None = None) -> list[Card]:
    return [c for c in project.cards if rarity is None or c.rarity.value == rarity]


def is_creature(card: Card) -> bool:
    return card_type(card) == "Creature"


def curve(project: SetProject, rarity: str | None = None) -> dict[str, dict[str, list[int]]]:
    """color -> mana value ("0".."7+") -> [creatures, other spells]; lands aren't counted."""
    out = {c: {mv: [0, 0] for mv in MANA_VALUES} for c in COLORS if c != "L"}
    for card in cards_at(project, rarity):
        key = color_key(card)
        if key == "L":
            continue
        out[key][mana_value_key(card)][0 if is_creature(card) else 1] += 1
    return out


def color_rarity_counts(project: SetProject) -> dict[str, dict[str, int]]:
    """color -> rarity -> number of cards (lands included as their own row)."""
    out = {c: {r: 0 for r in RARITIES} for c in COLORS}
    for card in project.cards:
        out[color_key(card)][card.rarity.value] += 1
    return out


def creature_ratio(project: SetProject, rarity: str | None = None) -> dict[str, tuple[int, int]]:
    """color -> (creatures, nonland cards)."""
    out = {c: [0, 0] for c in COLORS if c != "L"}
    for card in cards_at(project, rarity):
        key = color_key(card)
        if key == "L":
            continue
        out[key][1] += 1
        out[key][0] += is_creature(card)
    return {k: (v[0], v[1]) for k, v in out.items()}


def creature_size(project: SetProject, rarity: str | None = "common") -> dict[str, tuple[float, float, int]]:
    """mana value -> (average power, average toughness, creatures counted); creatures with
    a number for both only."""
    sums: dict[str, list[float]] = {}
    for card in cards_at(project, rarity):
        face = card.faces[0]
        if not is_creature(card) or not (face.power or "").isdigit() or not (face.toughness or "").isdigit():
            continue
        s = sums.setdefault(mana_value_key(card), [0, 0, 0])
        s[0] += int(face.power)
        s[1] += int(face.toughness)
        s[2] += 1
    return {mv: (s[0] / s[2], s[1] / s[2], int(s[2])) for mv, s in sorted(sums.items(),
                                                                          key=lambda kv: MANA_VALUES.index(kv[0]))}


def role_table(project: SetProject, rarity: str | None = None) -> dict[str, dict[str, list[Card]]]:
    """color -> role -> the cards with that role."""
    out = {c: {r: [] for r in ROLES} for c in COLORS}
    for card in cards_at(project, rarity):
        for role in roles(card):
            out[color_key(card)][role].append(card)
    return out


@dataclass
class MechanicSpread:
    mechanic: object
    cards: int
    by_color: dict[str, int]
    by_rarity: dict[str, int]

    @property
    def commons(self) -> int:
        return self.by_rarity.get("common", 0)


def mechanic_spread(project: SetProject) -> list[MechanicSpread]:
    from ..mechanics import usage
    out = []
    for mechanic in project.mechanics:
        u = usage(project, mechanic)
        out.append(MechanicSpread(mechanic, u.cards, u.by_color, u.by_rarity))
    return out


@dataclass
class ArchetypeCoverage:
    archetype: object
    counts: dict[str, int]                 # rarity -> cards tagged
    targets: dict[str, int]                # rarity -> wanted (only where set)


def archetype_coverage(project: SetProject) -> list[ArchetypeCoverage]:
    out = []
    for a in project.archetypes:
        counts = {r: 0 for r in RARITIES}
        for card in project.cards:
            if a.id in card.archetypes:
                counts[card.rarity.value] += 1
        out.append(ArchetypeCoverage(a, counts, {r.value: n for r, n in a.targets.items()}))
    return out


@dataclass
class CycleState:
    cycle: object
    made: int
    total: int
    edited: int
    missing: list[str] = field(default_factory=list)     # member color codes


def cycle_completeness(project: SetProject) -> list[CycleState]:
    from ..cycles import status
    out = []
    for cycle in project.cycles:
        states = status(cycle, project)
        made = [s for s in states if s.card is not None]
        made_any = bool(made)
        missing = [s.member.colors or f"#{s.n}" for s in states if s.card is None] if made_any else []
        out.append(CycleState(cycle, len(made), len(states), sum(1 for s in made if s.edited), missing))
    return out


def ability_word_issues(project: SetProject) -> list:
    """Card lines of ability words that follow none of the variants (app.ability_words)."""
    from ..ability_words import template_uses
    out = []
    for m in project.mechanics:
        if m.kind == MechanicKind.ABILITY_WORD and m.templates:
            out += [u for u in template_uses(project, m) if u.match is None]
    return out


@dataclass
class Complexity:
    card: Card
    words: int
    abilities: int
    keywords: int


def complexity(card: Card) -> Complexity:
    """Words of rules text (no reminder text), abilities (non-empty lines), keywords."""
    text = plain_text(card)
    words = len(re.findall(r"[A-Za-z0-9+/\-']+|\{[^}]*\}", text))
    abilities = sum(1 for line in text.split("\n") if line.strip())
    keywords = sum(len(line.split(", ")) for line in _keyword_lines(text))
    return Complexity(card, words, abilities, keywords)


def complexity_by_rarity(project: SetProject) -> dict[str, tuple[float, float, int]]:
    """rarity -> (average words, average abilities, cards)."""
    out = {}
    for r in RARITIES:
        cs = [complexity(c) for c in cards_at(project, r)]
        if cs:
            out[r] = (sum(c.words for c in cs) / len(cs), sum(c.abilities for c in cs) / len(cs), len(cs))
    return out


def mana_values(project: SetProject, rarity: str | None = None) -> list[int]:
    """Mana values of the nonland cards (for an average)."""
    return [mana_value(c.faces[0].mana_cost) for c in cards_at(project, rarity) if color_key(c) != "L"]
