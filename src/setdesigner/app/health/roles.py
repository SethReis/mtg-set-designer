"""What a card does in the set: removal, card draw, fixing, ... detected from its rules
text and its custom mechanics' roles (Mechanic.roles), with the card's own corrections on
top (Card.role_overrides).

Detection reads the front face's rules text with reminder text left out and the card's
name written as "this". It knows common Magic templating, not every card: when it gets
one wrong, remove or add the role on the card in the editor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..overview import main_types
from ...model import Card, SetProject

N = r"(?:a|an|one|two|three|four|five|x|\d+)"
EVASION_WORDS = ("flying", "menace", "trample", "skulk", "shadow", "fear", "intimidate", "horsemanship")


@dataclass(frozen=True)
class Role:
    id: str
    label: str
    patterns: tuple[str, ...] = ()


ROLES: dict[str, Role] = {r.id: r for r in [
    Role("removal", "Removal", (
        r"\b(?:destroy|exile)s? (?:up to (?:one|two|three) )?(?:another )?(?:other )?target\b",
        r"\bdeals? (?:\d+|x|that much) damage to (?:any target|target|each creature|each other creature"
        r"|up to (?:one|two) target)",
        r"\btarget creature(?: an opponent controls)? gets -(?:\d+|x)/-(?:\d+|x)",
        r"\bfights?\b",
        r"\bdeals? damage equal to (?:its|this creature's|their) power to (?:another |up to one )?target",
        r"\breturn (?:up to one )?target (?:\w+ )?(?:creature|nonland permanent)\w* to (?:its|their) owner(?:'s|s'|s)? hands?",
        r"\b(?:opponent|player) sacrifices\b",
        r"\benchanted creature can't attack or block",
    )),
    Role("counterspell", "Counterspell", (r"\bcounter target (?:\w+ )*?spell",)),
    Role("card_draw", "Card draw", (rf"\bdraws? {N} cards?\b", r"\binvestigate\b", r"\bconnives?\b")),
    Role("ramp", "Ramp", (
        r"\bsearch your library for (?:a |up to (?:one|two) )?basic land cards?[^.]*onto the battlefield",
    )),
    Role("fixing", "Fixing", (
        r"\badd one mana of any (?:color|type)",
        r"\badd \{[wubrg]\}(?:, \{[wubrg]\})*,? or \{[wubrg]\}",
        r"\bsearch your library for (?:a|up to one|up to two) basic land",
        r"\bsearch your library for an? (?:plains|island|swamp|mountain|forest)",
    )),
    Role("evasion", "Evasion", (
        r"\bcan't be blocked\b",
        r"\b(?:gains?|has|have) (?:" + "|".join(EVASION_WORDS) + r")\b",
    )),
    Role("combat_trick", "Combat trick"),            # see detected_roles (needs the card type)
    Role("token_maker", "Makes tokens", (rf"\bcreates? {N}\b[^.]*\btokens?\b",)),
    Role("lifegain", "Lifegain", (r"\bgains? (?:\d+|x) life\b", r"\blifelink\b")),
]}
TRICK = re.compile(r"\btarget creature(?: you control)? gets \+\d+/\+\d+|\btarget creature(?: you control)? "
                   r"gains? (?:hexproof|indestructible|first strike|double strike)", re.IGNORECASE)
MANA_ABILITY = re.compile(r"\{t\}: add \{", re.IGNORECASE)
COMPILED = {rid: [re.compile(p, re.IGNORECASE) for p in role.patterns] for rid, role in ROLES.items()}


def plain_text(card: Card) -> str:
    """The front face's rules text as detection reads it: no reminder text, the card's
    name as "this"."""
    face = card.faces[0]
    text = re.sub(r"\([^)]*\)", "", face.rules_text)
    text = text.replace("CARDNAME", "this")
    if face.name:
        text = text.replace(face.name, "this")
    return text


def _keyword_lines(text: str) -> list[str]:
    """Lines that are only keywords ("Flying, vigilance")."""
    return [line.strip().lower() for line in text.split("\n")
            if line.strip() and re.fullmatch(r"[A-Za-z][A-Za-z ]*(?:, [A-Za-z][A-Za-z ]*)*", line.strip())]


def mechanic_roles(card: Card, project: SetProject | None) -> dict[str, list[str]]:
    """role -> names of the card's mechanics tagged with it (Mechanic.roles)."""
    out: dict[str, list[str]] = {}
    for mechanic in project.mechanics if project is not None else []:
        if mechanic.id in card.mechanics:
            for rid in mechanic.roles:
                out.setdefault(rid, []).append(mechanic.name)
    return out


def detected_roles(card: Card, project: SetProject | None = None) -> list[str]:
    """The roles read from the card's rules text, plus those of its mechanics when the
    project is given, in ROLES order."""
    text = plain_text(card)
    types = {t.lower() for t in main_types(card)}
    found = {rid for rid, patterns in COMPILED.items() if any(p.search(text) for p in patterns)}
    keywords = [w for line in _keyword_lines(text) for w in line.split(", ")]
    if any(w.strip() in EVASION_WORDS for w in keywords):
        found.add("evasion")
    if "lifelink" in keywords:
        found.add("lifegain")
    if "land" not in types and MANA_ABILITY.search(text):
        found.add("ramp")                                     # mana creatures and rocks
    if "land" in types and len(set(re.findall(r"\{([WUBRG])\}", text))) >= 2:
        found.add("fixing")                                   # lands making two colors
    if ("instant" in types or "flash" in keywords) and TRICK.search(text):
        found.add("combat_trick")
    found.update(mechanic_roles(card, project))
    return [rid for rid in ROLES if rid in found]


def roles(card: Card, project: SetProject | None = None) -> list[str]:
    """The card's roles: detected ones (with its mechanics' when the project is given),
    corrected by its overrides."""
    found = set(detected_roles(card, project))
    for rid, add in card.role_overrides.items():
        if add:
            found.add(rid)
        else:
            found.discard(rid)
    return [rid for rid in ROLES if rid in found]
