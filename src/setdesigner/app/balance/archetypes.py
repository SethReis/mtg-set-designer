"""How strong each archetype is, from the cards tagged to it.

    for a in archetype_strength(project): print(a.archetype.name, a.strength, a.missing)

Three parts, each 0-1, shown on their own and combined into a 0-100 strength:
  playables  cards tagged against the archetype's targets (Archetype.targets; without
             targets, against the set's typical archetype)
  power      the cards' average score delta, against the other archetypes'
  roles      how many of its key roles (Archetype.key_roles, else DEFAULT_ROLES) it has
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, median

from ...model import Archetype, Card, SetProject
from ..health.roles import ROLES, roles
from ..health.stats import is_creature
from ..overview import mana_value
from .score import Score, scores as all_scores

DEFAULT_ROLES = ["removal", "two_drop", "card_draw"]
ROLE_LABELS = {"two_drop": "Two-drops", **{rid: r.label for rid, r in ROLES.items()}}
WEIGHTS = {"playables": 0.4, "power": 0.3, "roles": 0.3}


def key_roles(archetype: Archetype) -> list[str]:
    return DEFAULT_ROLES if archetype.key_roles is None else archetype.key_roles


def card_roles(card: Card, project: SetProject) -> set[str]:
    found = set(roles(card, project))
    if is_creature(card) and mana_value(card.faces[0].mana_cost) == 2:
        found.add("two_drop")
    return found


@dataclass
class ArchetypeStrength:
    archetype: Archetype
    cards: list[Card]
    target: int                               # wanted cards (sum of targets, or the set's typical count)
    average_delta: float | None               # None: no scored cards
    role_counts: dict[str, int] = field(default_factory=dict)   # key role -> cards with it
    playables: float = 0.0
    power: float = 0.0
    roles: float = 0.0

    @property
    def missing(self) -> list[str]:
        return [r for r, n in self.role_counts.items() if n == 0]

    @property
    def strength(self) -> int:
        return round(100 * (WEIGHTS["playables"] * self.playables + WEIGHTS["power"] * self.power
                            + WEIGHTS["roles"] * self.roles))

    def curve(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for card in self.cards:
            mv = min(mana_value(card.faces[0].mana_cost), 7)
            out[mv] = out.get(mv, 0) + 1
        return dict(sorted(out.items()))


def archetype_strength(project: SetProject, scored: dict[str, Score] | None = None) -> list[ArchetypeStrength]:
    """Every archetype, strongest first."""
    scored = all_scores(project) if scored is None else scored
    out = []
    for archetype in project.archetypes:
        cards = [c for c in project.cards if archetype.id in c.archetypes]
        deltas = [scored[c.id].delta for c in cards if c.id in scored]
        counts = {r: sum(1 for c in cards if r in card_roles(c, project)) for r in key_roles(archetype)}
        out.append(ArchetypeStrength(archetype, cards, sum(archetype.targets.values()),
                                     round(mean(deltas), 2) if deltas else None, counts))
    typical = median([len(a.cards) for a in out]) if out else 0
    averages = [a.average_delta for a in out if a.average_delta is not None]
    middle = mean(averages) if averages else 0.0
    for a in out:
        wanted = a.target or typical
        a.target = int(wanted)
        a.playables = min(1.0, len(a.cards) / wanted) if wanted else (1.0 if a.cards else 0.0)
        a.power = 0.0 if a.average_delta is None else max(0.0, min(1.0, 0.5 + (a.average_delta - middle) / 2))
        a.roles = (sum(1 for n in a.role_counts.values() if n) / len(a.role_counts)) if a.role_counts else 1.0
    out.sort(key=lambda a: -a.strength)
    return out
