"""The set skeleton: generating a grid of slots, adjusting it, and filling it. No UI.

    columns = default_columns(project)                # W U B R G, archetype color sets, C, L
    counts = default_counts("play_booster", columns)  # column -> rarity -> slots
    skeleton = Skeleton(preset="play_booster", columns=columns, counts=counts,
                        slots=generate(columns, counts, project.archetypes))
    outside = place_cards(skeleton, project)          # existing cards into slots that fit
    suggest(skeleton, slot, project)                  # unassigned cards for an empty slot

A column is a single color, a color set ("WU", "WUB"), "C" (colorless) or "L" (land).
Multicolor columns follow the archetypes' color sets; more can be added by hand. A card
belongs to a column by its front face's colors (as Health counts cards): see column_of.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..model import Archetype, Card, Rarity, SetProject
from ..model.skeleton import ANY, Skeleton, Slot
from .health.roles import roles as card_roles
from .overview import card_type, main_types, mana_value, number_key

MONO = ["W", "U", "B", "R", "G"]       # the single-color columns (a list: "WU" isn't one)
COLORLESS, LAND = "C", "L"
PAIRS = ["WU", "UB", "BR", "RG", "GW", "WB", "UR", "BG", "RW", "GU"]      # the usual order
RARITIES = [Rarity.COMMON, Rarity.UNCOMMON, Rarity.RARE, Rarity.MYTHIC]
RARITY_LETTERS = {Rarity.COMMON: "C", Rarity.UNCOMMON: "U", Rarity.RARE: "R", Rarity.MYTHIC: "M",
                  Rarity.SPECIAL: "S"}
COLUMN_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green",
                COLORLESS: "Colorless", LAND: "Land"}


@dataclass(frozen=True)
class Preset:
    label: str
    totals: dict[str, int]           # rarity value -> slots; a cube has one ANY total
    description: str = ""


PRESETS: dict[str, Preset] = {
    "play_booster": Preset("Play Booster set", {"common": 81, "uncommon": 100, "rare": 60, "mythic": 20},
                           "A modern main set: about 81 commons, 100 uncommons, 60 rares, 20 mythics."),
    "classic": Preset("Classic draft set", {"common": 101, "uncommon": 80, "rare": 53, "mythic": 15},
                      "The older draft-booster shape: 101 commons, 80 uncommons, 53 rares, 15 mythics."),
    "cube": Preset("Cube", {ANY: 360},
                   "No rarities: one of each card, about 45 per color plus multicolor, artifacts and lands."),
}


# ---------------------------------------------------------------------- columns

def canonical(colors: str) -> str:
    """A color set's column name: pairs in their usual order ("GW", not "WG"), larger sets
    and single colors in WUBRG order. Accepts any order and case."""
    found = "".join(c for c in "WUBRG" if c in colors.upper())
    if len(found) == 2:
        return next(p for p in PAIRS if set(p) == set(found))
    return found


def is_multicolor(column: str) -> bool:
    return len(column) >= 2


def column_label(column: str) -> str:
    return COLUMN_NAMES.get(column, column)


def column_order(column: str) -> tuple:
    """W U B R G, then pairs in their usual order, then larger sets, then C, L."""
    if column in MONO:
        return (0, MONO.index(column), "")
    if column == COLORLESS:
        return (3, 0, "")
    if column == LAND:
        return (4, 0, "")
    if len(column) == 2:
        return (1, PAIRS.index(column) if column in PAIRS else 99, column)
    return (2, len(column), "".join(str("WUBRG".index(c)) for c in column))


def default_columns(project: SetProject) -> list[str]:
    """W U B R G, a column per archetype color set of two or more colors, C and L."""
    sets = {canonical(a.colors) for a in project.archetypes if len(canonical(a.colors)) >= 2}
    return sorted([*MONO, *sets, COLORLESS, LAND], key=column_order)


def rarities_of(preset: str) -> list[str]:
    return [ANY] if ANY in PRESETS[preset].totals else [r.value for r in RARITIES]


def default_counts(preset: str, columns: list[str]) -> dict[str, dict[str, int]]:
    """A starting table: mono colors share each rarity evenly; multicolor columns get
    signpost-like counts (an uncommon pair, a rare, a few commons in a big set);
    colorless and land a small share. Every rarity adds up to the preset's total."""
    gold = [c for c in columns if is_multicolor(c)]
    mono = [c for c in columns if c in MONO] or [c for c in columns if c not in gold][:1]
    counts: dict[str, dict[str, int]] = {c: {} for c in columns}
    if ANY in PRESETS[preset].totals:                          # cube: a count per column
        for c in columns:
            counts[c][ANY] = 45 if c in MONO else 30 if c == COLORLESS else 25 if c == LAND else 4
        return counts
    for rarity, total in PRESETS[preset].totals.items():
        per_gold = {"common": 1 if total >= 100 else 0, "uncommon": 2, "rare": 1,
                    "mythic": 1 if total >= len(gold) * 2 else 0}[rarity]
        if gold and per_gold * len(gold) > total * 0.4:          # never most of a rarity
            per_gold = int(total * 0.4) // len(gold)
        share = {COLORLESS: {"common": 0.03, "uncommon": 0.05, "rare": 0.05, "mythic": 0.05},
                 LAND: {"common": 0.05, "uncommon": 0.02, "rare": 0.05, "mythic": 0.0}}
        left = total
        for c in columns:
            if c in gold:
                counts[c][rarity] = per_gold
            elif c in share:
                counts[c][rarity] = round(total * share[c][rarity])
            else:
                continue
            left -= counts[c][rarity]
        each, extra = divmod(max(0, left), len(mono))
        for i, c in enumerate(mono):
            counts[c][rarity] = each + (1 if i < extra else 0)
    return counts


def totals(counts: dict[str, dict[str, int]]) -> dict[str, int]:
    """Slots per rarity (or ANY) across the columns."""
    out: dict[str, int] = {}
    for per_rarity in counts.values():
        for rarity, n in per_rarity.items():
            out[rarity] = out.get(rarity, 0) + n
    return out


# ---------------------------------------------------------------------- slots

def label(column: str, rarity: str, index: int) -> str:
    return f"{column}-{index:02d}" if rarity == ANY else f"{column}-{RARITY_LETTERS[Rarity(rarity)]}{index:02d}"


def _archetype_for(column: str, archetypes: list[Archetype]) -> str | None:
    """The archetype a multicolor column stands for, if one has exactly its colors."""
    if not is_multicolor(column):
        return None
    return next((a.id for a in archetypes if canonical(a.colors) == column), None)


def _new_slot(column: str, rarity: str, index: int, archetypes: list[Archetype]) -> Slot:
    return Slot(id=label(column, rarity, index), column=column,
                rarity=None if rarity == ANY else Rarity(rarity), archetypes=[a] if (a := _archetype_for(column, archetypes)) else [])


def _rarity_key(slot: Slot) -> str:
    return ANY if slot.rarity is None else slot.rarity.value


def generate(columns: list[str], counts: dict[str, dict[str, int]], archetypes: list[Archetype]) -> list[Slot]:
    """Empty slots, labelled by column, rarity and number (W-C01); multicolor columns
    are tagged with their archetype."""
    return [_new_slot(column, rarity, i, archetypes)
            for column in columns for rarity, n in counts.get(column, {}).items() for i in range(1, n + 1)]


def cell(skeleton: Skeleton, column: str, rarity: str) -> list[Slot]:
    return [s for s in skeleton.slots if s.column == column and _rarity_key(s) == rarity]


def adjust(skeleton: Skeleton, columns: list[str], counts: dict[str, dict[str, int]],
           archetypes: list[Archetype], remove_filled: bool = False) -> list[Slot]:
    """Reach new counts in place: new slots go at the end of their cell; removed ones are
    the cell's empty slots, plain ones first, from the end. Filled slots are only removed
    with `remove_filled`; otherwise they are returned (and kept) for the UI to ask about."""
    blocked: list[Slot] = []
    for column in columns:
        for rarity, want in counts.get(column, {}).items():
            have = cell(skeleton, column, rarity)
            if want > len(have):
                used = {s.id for s in skeleton.slots}
                index = 1
                for _ in range(want - len(have)):
                    while label(column, rarity, index) in used:
                        index += 1
                    slot = _new_slot(column, rarity, index, archetypes)
                    used.add(slot.id)
                    skeleton.slots.append(slot)
            elif want < len(have):
                extra = len(have) - want
                order = ([s for s in reversed(have) if s.card_id is None and not s.annotated]
                         + [s for s in reversed(have) if s.card_id is None and s.annotated]
                         + [s for s in reversed(have) if s.card_id is not None])
                for slot in order[:extra]:
                    if slot.card_id is not None and not remove_filled:
                        blocked.append(slot)
                    else:
                        skeleton.slots.remove(slot)
    # columns that are gone lose their empty slots (filled ones are asked about too)
    for slot in [s for s in skeleton.slots if s.column not in columns]:
        if slot.card_id is not None and not remove_filled:
            blocked.append(slot)
        else:
            skeleton.slots.remove(slot)
    skeleton.columns = list(columns)
    skeleton.counts = {c: dict(counts.get(c, {})) for c in columns}
    return blocked


# ---------------------------------------------------------------------- cards and slots

def column_of(card: Card, columns: list[str]) -> str:
    """The column a card belongs in: lands in L, colorless cards in C, one color in its
    column, more colors in their color set's column or else the closest one (most colors
    shared, fewest extra). The front face decides, as in Health."""
    if card_type(card) == "Land" and LAND in columns:
        return LAND
    colors = canonical("".join(card.faces[0].colors()))
    if not colors:
        return COLORLESS
    if len(colors) == 1 or colors in columns:
        return colors
    multi = [c for c in columns if is_multicolor(c)]
    if not multi:
        return colors[0]
    return max(multi, key=lambda c: (len(set(c) & set(colors)), -len(set(c) ^ set(colors)), -column_order(c)[1]))


def fits(card: Card, slot: Slot, columns: list[str], project: SetProject | None = None) -> int | None:
    """How well a card fits a slot: None if its column or rarity differ, else a score
    (higher is better) from the slot's type, mana value, role and archetype."""
    if column_of(card, columns) != slot.column:
        return None
    if slot.rarity is not None and card.rarity != slot.rarity:
        return None
    score = 1
    if slot.types:
        types = {t.lower() for t in main_types(card)}
        score += 2 if all(t.lower() in types for t in slot.types.split()) else -1
    if slot.mana_value is not None:
        mv = mana_value(card.faces[0].mana_cost)
        score += 2 if mv == slot.mana_value else 1 if abs(mv - slot.mana_value) == 1 else -1
    if slot.role:
        score += 2 if slot.role in card_roles(card, project) else -1
    if slot.archetypes:
        score += 2 if set(slot.archetypes) & set(card.archetypes) else -1 if card.archetypes else 0
    return score


def outside(skeleton: Skeleton, cards: list[Card]) -> list[Card]:
    """Cards that aren't in any slot."""
    placed = {s.card_id for s in skeleton.slots if s.card_id}
    return [c for c in cards if c.id not in placed]


def place_cards(skeleton: Skeleton, project: SetProject) -> list[Card]:
    """Put cards that aren't in a slot yet into empty slots that fit, best fits first (each
    card in one slot). Returns the cards still outside the skeleton."""
    loose = outside(skeleton, project.cards)
    pairs = []
    for slot in skeleton.slots:
        if slot.card_id is None:
            for card in loose:
                score = fits(card, slot, skeleton.columns, project)
                if score is not None:
                    pairs.append((score, number_key(card), slot.id, card, slot))
    pairs.sort(key=lambda p: (-p[0], p[1], p[2]))
    used: set[str] = set()
    for _score, _key, _id, card, slot in pairs:
        if card.id in used or slot.card_id is not None:
            continue
        slot.card_id = card.id
        used.add(card.id)
    return outside(skeleton, project.cards)


def suggest(skeleton: Skeleton, slot: Slot, project: SetProject, n: int = 5) -> list[Card]:
    """Cards outside the skeleton that fit the slot, best first."""
    scored = [(fits(card, slot, skeleton.columns, project), card) for card in outside(skeleton, project.cards)]
    return [card for score, card in sorted(((s, c) for s, c in scored if s is not None),
                                           key=lambda p: (-p[0], number_key(p[1])))][:n]


def targets(skeleton: Skeleton) -> dict[Rarity, int]:
    """Slots per rarity: the set's rarity targets while it has a skeleton."""
    out: dict[Rarity, int] = {}
    for slot in skeleton.slots:
        if slot.rarity is not None:
            out[slot.rarity] = out.get(slot.rarity, 0) + 1
    return out


def slot_archetypes(slot: Slot, project: SetProject) -> list[str]:
    """A slot's archetypes: its card's tags once filled, else the archetypes it plans for."""
    if slot.card_id is not None:
        card = next((c for c in project.cards if c.id == slot.card_id), None)
        if card is not None:
            return list(card.archetypes)
    return list(slot.archetypes)


def describe(slot: Slot, project: SetProject | None = None) -> str:
    """What an empty slot asks for, in a few words: "Creature · 2 MV · Removal · note"."""
    from .health.roles import ROLES
    parts = [slot.types, f"{slot.mana_value} MV" if slot.mana_value is not None else "",
             ROLES[slot.role].label if slot.role in ROLES else ""]
    if project is not None:
        names = {a.id: a.name for a in project.archetypes}
        parts.extend(names.get(a, "") for a in slot_archetypes(slot, project))
    parts.append(slot.note)
    return " · ".join(p for p in parts if p)
