"""Set-health warnings: built-in checks with thresholds you can tune per set
(SetInfo.health: check id -> enabled, threshold).

    for warning in run_checks(project): print(warning.message, warning.card_ids)

Each check looks at the five colors (W U B R G) where it's about colors, counts front faces,
and stays quiet on a set without cards.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ...model import MechanicKind, Rarity, SetProject
from ..overview import COLOR_LABELS, color_key, mana_value
from . import stats
from .roles import roles

FIVE = ["W", "U", "B", "R", "G"]


@dataclass
class Warning:
    check_id: str
    message: str
    card_ids: list[str] = field(default_factory=list)
    severity: str = "warning"              # "warning" or "info"


@dataclass
class Check:
    id: str
    label: str
    default: float | None                  # None: the check has no threshold
    unit: str                              # how the threshold reads ("cards", "%", "words", ...)
    run: Callable[[SetProject, float | None], list[Warning]]


def _commons(project: SetProject, color: str):
    return [c for c in project.cards if c.rarity == Rarity.COMMON and color_key(c) == color]


def _plural(n: float, word: str) -> str:
    n = int(n) if float(n).is_integer() else n
    return f"{n} {word}{'' if n == 1 else 's'}"


# ---------------------------------------------------------------------- the checks

def common_removal(project, threshold):
    out = []
    for color in FIVE:
        cards = [c for c in _commons(project, color) if "removal" in roles(c)]
        if len(cards) < threshold:
            out.append(Warning("common_removal", f"{COLOR_LABELS[color]} has {len(cards)} common removal "
                               f"(wanted ≥ {int(threshold)})", [c.id for c in cards]))
    return out


def any_removal(project, threshold):
    out = []
    for color in FIVE:
        cards = [c for c in project.cards if color_key(c) == color
                 and c.rarity in (Rarity.COMMON, Rarity.UNCOMMON) and "removal" in roles(c)]
        if len(cards) < threshold:
            out.append(Warning("any_removal", f"{COLOR_LABELS[color]} has {len(cards)} removal at common or "
                               f"uncommon (wanted ≥ {int(threshold)})", [c.id for c in cards]))
    return out


def creature_share(project, threshold):
    out = []
    for color in FIVE:
        cards = _commons(project, color)
        if not cards:
            continue
        creatures = [c for c in cards if stats.is_creature(c)]
        share = 100 * len(creatures) / len(cards)
        if share < threshold:
            out.append(Warning("creature_share", f"{COLOR_LABELS[color]} commons are {share:.0f}% creatures "
                               f"(wanted ≥ {threshold:.0f}%)", [c.id for c in cards if c not in creatures]))
    return out


def two_drops(project, threshold):
    out = []
    for color in FIVE:
        cards = [c for c in _commons(project, color)
                 if stats.is_creature(c) and mana_value(c.faces[0].mana_cost) == 2]
        if len(cards) < threshold:
            out.append(Warning("two_drops", f"{COLOR_LABELS[color]} has {_plural(len(cards), 'common two-drop creature')} "
                               f"(wanted ≥ {int(threshold)})", [c.id for c in cards]))
    return out


def color_balance(project, threshold):
    counts = {color: len(_commons(project, color)) for color in FIVE}
    if not any(counts.values()):
        return []
    average = sum(counts.values()) / 5
    out = []
    for color, n in counts.items():
        if abs(n - average) > threshold:
            more = "more" if n > average else "fewer"
            out.append(Warning("color_balance", f"{COLOR_LABELS[color]} has {n} commons, {abs(n - average):.1f} "
                               f"{more} than the average {average:.1f}",
                               [c.id for c in _commons(project, color)], "info"))
    return out


def rarity_slots(project, _threshold):
    out = []
    for rarity, wanted in project.info.rarity_slots.items():
        n = sum(1 for c in project.cards if c.rarity == rarity)
        if n != wanted:
            word = "short of" if n < wanted else "over"
            out.append(Warning("rarity_slots", f"{rarity.value.title()}: {n} of {wanted} cards ({abs(wanted - n)} {word} "
                               "the target)", [], "info" if n < wanted else "warning"))
    return out


def wordy_commons(project, threshold):
    cards = [cx for cx in (stats.complexity(c) for c in project.cards if c.rarity == Rarity.COMMON)
             if cx.words > threshold]
    if not cards:
        return []
    return [Warning("wordy_commons", f"{_plural(len(cards), 'common')} over {int(threshold)} words "
                    f"(longest: {max(c.words for c in cards)})", [c.card.id for c in cards])]


def complex_commons(project, threshold):
    cards = [cx for cx in (stats.complexity(c) for c in project.cards if c.rarity == Rarity.COMMON)
             if cx.abilities > threshold]
    if not cards:
        return []
    return [Warning("complex_commons", f"{_plural(len(cards), 'common')} with more than "
                    f"{_plural(threshold, 'ability')}", [c.card.id for c in cards])]


def mechanic_commons(project, threshold):
    out = []
    for spread in stats.mechanic_spread(project):
        m = spread.mechanic
        if m.kind == MechanicKind.ABILITY_WORD and not spread.cards:
            continue
        if spread.commons < threshold:
            from ..mechanics import find_uses
            ids = list(dict.fromkeys(u.card.id for u in find_uses(project, m)))
            out.append(Warning("mechanic_commons", f"{m.name} is on {_plural(spread.commons, 'common')} "
                               f"(wanted ≥ {int(threshold)})", ids))
    return out


def archetype_targets(project, _threshold):
    out = []
    for cov in stats.archetype_coverage(project):
        short = [f"{r} {cov.counts[r]}/{n}" for r, n in cov.targets.items() if cov.counts.get(r, 0) < n]
        if short:
            ids = [c.id for c in project.cards if cov.archetype.id in c.archetypes]
            out.append(Warning("archetype_targets", f"{cov.archetype.name} is below target: {', '.join(short)}",
                               ids, "info"))
    return out


def cycles_missing(project, _threshold):
    out = []
    for state in stats.cycle_completeness(project):
        if state.missing:
            out.append(Warning("cycles_missing", f"Cycle {state.cycle.name} is missing "
                               f"{', '.join(state.missing)} ({state.made} of {state.total} made)", []))
    return out


def ability_words(project, _threshold):
    issues = stats.ability_word_issues(project)
    if not issues:
        return []
    return [Warning("ability_words", f"{_plural(len(issues), 'ability-word line')} follow none of the "
                    "mechanic's variants", list(dict.fromkeys(u.card.id for u in issues)))]


def fixing(project, threshold):
    multicolor = [c for c in project.cards if color_key(c) == "M"]
    if not multicolor:
        return []
    cards = [c for c in project.cards if c.rarity in (Rarity.COMMON, Rarity.UNCOMMON) and "fixing" in roles(c)]
    if len(cards) >= threshold:
        return []
    return [Warning("fixing", f"{_plural(len(multicolor), 'multicolor card')} but only "
                    f"{len(cards)} fixing at common/uncommon (wanted ≥ {int(threshold)})", [c.id for c in cards])]


CHECKS: dict[str, Check] = {c.id: c for c in [
    Check("common_removal", "Common removal per color", 2, "cards", common_removal),
    Check("any_removal", "Removal per color at common or uncommon", 1, "cards", any_removal),
    Check("creature_share", "Creatures among each color's commons", 55, "%", creature_share),
    Check("two_drops", "Common two-drop creatures per color", 2, "cards", two_drops),
    Check("color_balance", "Commons balanced across colors", 2, "cards off the average", color_balance),
    Check("rarity_slots", "Cards per rarity against the set's targets", None, "", rarity_slots),
    Check("wordy_commons", "Wordy commons", 40, "words", wordy_commons),
    Check("complex_commons", "Complex commons", 3, "abilities", complex_commons),
    Check("mechanic_commons", "Each mechanic on enough commons", 3, "commons", mechanic_commons),
    Check("archetype_targets", "Archetypes against their targets", None, "", archetype_targets),
    Check("cycles_missing", "Cycles with missing members", None, "", cycles_missing),
    Check("ability_words", "Ability-word lines that follow a variant", None, "", ability_words),
    Check("fixing", "Fixing at common/uncommon when the set has multicolor cards", 5, "cards", fixing),
]}


def threshold(project: SetProject, check: Check) -> float | None:
    setting = project.info.health.get(check.id)
    return setting.threshold if setting is not None and setting.threshold is not None else check.default


def enabled(project: SetProject, check: Check) -> bool:
    setting = project.info.health.get(check.id)
    return setting is None or setting.enabled


def run_checks(project: SetProject) -> list[Warning]:
    """Every enabled check's warnings, in CHECKS order (none for a set without cards)."""
    if not project.cards:
        return []
    out = []
    for check in CHECKS.values():
        if enabled(project, check):
            out += check.run(project, threshold(project, check))
    return out
