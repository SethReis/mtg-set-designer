"""Cycles: groupings of colors, the color tokens in a cycle's template, member previews,
and keeping generated cards in step with the template. No UI.

    members_for("allied_pairs")             -> WU, UB, BR, RG, GW
    render("{basic} Sanctum", "WU")         -> "Plains or Island Sanctum"
    member_fields(cycle, member, n)         -> {"name": ..., "mana_cost": ..., ...}

Tokens (lowercase; uppercase {W} {2} {T} stay mana and other symbols):
    {c}  {c1} {c2} {c3} {c4}   mana symbols: {W}{U} / {W} / {U}
    {color} {Color}            white and blue / White and blue
    {basic} {basic1} {basic2}  Plains or Island / Plains / Island
    {group}                    White / Azorius / Esper / Non-green
    {n}                        the member's number in the cycle (1, 2, …)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..model import Card, Cycle, CycleMember, CycleTemplate, SetProject
from ..model.cycle import TEMPLATE_FIELDS

COLOR_NAMES = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}
BASICS = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}
GROUP_NAMES = {
    "W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green", "": "Colorless",
    "WU": "Azorius", "UB": "Dimir", "BR": "Rakdos", "RG": "Gruul", "GW": "Selesnya",
    "WB": "Orzhov", "UR": "Izzet", "BG": "Golgari", "RW": "Boros", "GU": "Simic",
    "GWU": "Bant", "WUB": "Esper", "UBR": "Grixis", "BRG": "Jund", "RGW": "Naya",
    "WBG": "Abzan", "URW": "Jeskai", "BGU": "Sultai", "RWB": "Mardu", "GUR": "Temur",
    "WUBR": "Non-green", "UBRG": "Non-white", "BRGW": "Non-blue", "RGWU": "Non-black",
    "GWUB": "Non-red", "WUBRG": "Five-color",
}
ALLIED = ["WU", "UB", "BR", "RG", "GW"]
ENEMY = ["WB", "UR", "BG", "RW", "GU"]
SHARDS = ["GWU", "WUB", "UBR", "BRG", "RGW"]
WEDGES = ["WBG", "URW", "BGU", "RWB", "GUR"]
GROUPINGS: dict[str, tuple[str, list[str]]] = {
    "mono": ("Mono-color (5)", ["W", "U", "B", "R", "G"]),
    "allied_pairs": ("Allied pairs (5)", ALLIED),
    "enemy_pairs": ("Enemy pairs (5)", ENEMY),
    "pairs": ("All pairs (10)", ALLIED + ENEMY),
    "shards": ("Shards (5)", SHARDS),
    "wedges": ("Wedges (5)", WEDGES),
    "triads": ("All three-color (10)", SHARDS + WEDGES),
    "four_color": ("Four-color (5)", ["WUBR", "UBRG", "BRGW", "RGWU", "GWUB"]),
    "custom": ("Custom colors", []),
    "numbered": ("Numbered, colorless", []),
}
# every combination the custom picker offers, in a sensible order
ALL_COMBINATIONS = (GROUPINGS["mono"][1] + ALLIED + ENEMY + SHARDS + WEDGES
                    + GROUPINGS["four_color"][1] + ["WUBRG", ""])
TOKEN = re.compile(r"\{(c[1-5]?|[cC]olor|basic[1-5]?|group|n)\}")


def members_for(grouping: str, custom: list[str] | None = None, count: int = 5,
                old: list[CycleMember] | None = None) -> list[CycleMember]:
    """The members of a grouping (custom: the given combinations; numbered: `count`
    colorless ones). A member already in `old` with the same colors keeps its card and
    overrides."""
    if grouping == "custom":
        combos = list(custom or [])
    elif grouping == "numbered":
        combos = [""] * max(1, count)
    else:
        combos = GROUPINGS[grouping][1]
    kept = {m.colors: m for m in old or [] if grouping != "numbered"}
    if grouping == "numbered":
        previous = list(old or [])
        return [previous[i] if i < len(previous) and not previous[i].colors else CycleMember()
                for i in range(len(combos))]
    return [kept.get(c, CycleMember(colors=c)) for c in combos]


def _join(words: list[str], conjunction: str) -> str:
    if len(words) <= 2:
        return f" {conjunction} ".join(words)
    return ", ".join(words[:-1]) + f", {conjunction} " + words[-1]


def render(text: str, colors: str, n: int = 1) -> str:
    """The text with this member's color tokens filled in."""
    def token(m: re.Match) -> str:
        key = m.group(1)
        if key == "c":
            return "".join(f"{{{c}}}" for c in colors)
        if key.startswith("c") and key[1:].isdigit():
            i = int(key[1:]) - 1
            return f"{{{colors[i]}}}" if i < len(colors) else ""
        if key in ("color", "Color"):
            words = _join([COLOR_NAMES[c] for c in colors], "and") or "colorless"
            return words[:1].upper() + words[1:] if key == "Color" else words
        if key == "basic":
            return _join([BASICS[c] for c in colors], "or")
        if key.startswith("basic"):
            i = int(key[5:]) - 1
            return BASICS[colors[i]] if i < len(colors) else ""
        if key == "group":
            return GROUP_NAMES.get(colors, colors)
        return str(n)                                # {n}
    return TOKEN.sub(token, text)


def member_fields(cycle: Cycle, member: CycleMember, n: int,
                  template: CycleTemplate | None = None) -> dict[str, str]:
    """A member's card fields: the template (or the member's own override), tokens filled."""
    template = cycle.template if template is None else template
    out = {}
    for name in TEMPLATE_FIELDS:
        text = member.overrides.get(name, getattr(template, name))
        out[name] = render(text, member.colors, n)
    return out


def card_field(card: Card, name: str) -> str:
    """A card's current value of a template field, as text."""
    if name == "rarity":
        return card.rarity.value
    if name == "frame":
        return card.frame or ""
    value = getattr(card.faces[0], name)
    return value or ""


@dataclass
class MemberStatus:
    member: CycleMember
    n: int
    card: Card | None                      # None: missing (never made, or deleted)
    edited: list[str] = field(default_factory=list)   # fields changed on the card


def status(cycle: Cycle, project: SetProject) -> list[MemberStatus]:
    cards = {c.id: c for c in project.cards}
    out = []
    for n, member in enumerate(cycle.members, 1):
        card = cards.get(member.card_id) if member.card_id else None
        edited = []
        if card is not None:
            expected = member_fields(cycle, member, n)
            edited = [f for f in TEMPLATE_FIELDS if card_field(card, f) != expected[f]]
        out.append(MemberStatus(member, n, card, edited))
    return out


@dataclass
class CycleChange:
    card: Card
    fields: dict[str, tuple[str, str]]     # field -> (before, after)


@dataclass
class CyclePlan:
    changes: list[CycleChange]
    kept: dict[str, list[str]] = field(default_factory=dict)   # card id -> fields left alone


def template_change_plan(cycle: Cycle, project: SetProject, new_template: CycleTemplate) -> CyclePlan:
    """What changing the template would do to the members' cards: each field that still
    equals what the old template gave follows the new one; fields edited on a card stay."""
    plan = CyclePlan([])
    for st in status(cycle, project):
        if st.card is None:
            continue
        old = member_fields(cycle, st.member, st.n)
        new = member_fields(cycle, st.member, st.n, new_template)
        fields, kept = {}, []
        for name in TEMPLATE_FIELDS:
            if old[name] == new[name]:
                continue
            if card_field(st.card, name) == old[name]:
                fields[name] = (old[name], new[name])
            else:
                kept.append(name)
        if fields:
            plan.changes.append(CycleChange(st.card, fields))
        if kept:
            plan.kept[st.card.id] = kept
    return plan


def matching_archetypes(project: SetProject, colors: str) -> list[str]:
    """Archetypes whose colors are exactly these (signpost tagging)."""
    return [a.id for a in project.archetypes if a.colors and set(a.colors) == set(colors)]
