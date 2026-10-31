"""Our data model -> MSE field values.

MSE's magic game has one *card* per face: a double-faced card becomes two MSE
cards linked to each other ("Front Face" / "Back Face" relations), as MSE 2.6 does.
Values are the raw, unscripted values a user would type into MSE; the game's
field scripts (run by setdesigner.mse.objects) derive the rest.

    Face / Card              MSE card field
    -----------------------  ------------------------------------------------
    name                     name
    mana_cost "{2}{W}{W}"    casting cost "2WW"  ({W/U} -> "W/U")
    type_line "A B — C D"    super type "A B", sub type "C D"
    rules_text               rule text
    flavor_text              flavor text
    power / toughness        power / toughness
    loyalty                  loyalty
    rules_text "+1: Draw."   loyalty cost 1 "+1", rule text "Draw."  (planeswalkers:
                             one ability per line, see loyalty_abilities)
    color_indicator          indicator  (multiple choice: "blue, red")
    art_path + art_crop      image  (the cropped art, packed into the set by the renderer:
                             see MSECard.art)
    artist                   illustrator
    card.rarity              rarity
    card.notes               notes (a card property, not a field)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..model import ArtCrop, Card, Face, Rarity, SetInfo
from ..model.card import COLOR_NAMES
from ..model.layouts import LAYOUTS
from .frames import frame_styling, stylesheet_package

TYPE_SEPARATORS = (" — ", " - ", " -- ")
LETTER_TO_COLOR = {letter: name for name, letter in COLOR_NAMES.items()}
MSE_RARITY = {Rarity.COMMON: "common", Rarity.UNCOMMON: "uncommon", Rarity.RARE: "rare",
              Rarity.MYTHIC: "mythic rare", Rarity.SPECIAL: "special"}


@dataclass
class ArtRef:
    """A face's art: the file (full path) and which part of it shows."""
    path: Path
    crop: ArtCrop | None = None


@dataclass
class MSECard:
    """One MSE card (= one face of our card)."""
    uid: str
    stylesheet: str                         # package name, e.g. "magic-m15-altered"
    values: dict[str, str]                  # field name -> raw value
    notes: str = ""
    links: list[tuple[str, str]] = field(default_factory=list)   # (linked uid, its relation)
    # MSE only reads art packed inside the set file, cropped to the frame's art box, so the
    # renderer prepares it (and fills in the "image" value) from this
    art: ArtRef | None = None
    # styling options for this card only (MSE's "styling data"), e.g. the Universes Beyond
    # frame is M15 with frames: universes beyond
    styling: dict[str, str] = field(default_factory=dict)


def face_uid(card: Card, face_index: int) -> str:
    return card.id if len(card.faces) == 1 else f"{card.id}/{face_index + 1}"


def mse_mana_cost(cost: str) -> str:
    """"{2}{W}{W}" -> "2WW", "{W/U}" -> "W/U"; text without braces is kept."""
    return "".join(re.findall(r"\{([^}]*)\}", cost)) if "{" in cost else cost


def split_type_line(type_line: str) -> tuple[str, str]:
    for sep in TYPE_SEPARATORS:
        if sep in type_line:
            supertype, subtype = type_line.split(sep, 1)
            return supertype.strip(), subtype.strip()
    return type_line.strip(), ""


def join_type_line(types: str, subtypes: str) -> str:
    """("Legendary Creature", "Elf Druid") -> "Legendary Creature — Elf Druid"; the dash
    only appears when both parts are given."""
    types, subtypes = types.strip(), subtypes.strip()
    return f"{types} — {subtypes}" if types and subtypes else types or subtypes


def mse_color_indicator(indicator: str) -> str:
    """"U" / "blue" / "red, green" -> MSE's multiple choice "blue" / "red, green"."""
    text = indicator.strip()
    if not text:
        return ""
    if all(c in LETTER_TO_COLOR for c in text):
        return ", ".join(LETTER_TO_COLOR[c] for c in text)
    return ", ".join(part.strip().lower() for part in text.split(","))


def mse_text(text: str) -> str:
    """Rules/flavor text: mana symbols "{2}{W}" become MSE's "<sym>2W</sym>" tags (as
    the game's own Scryfall import does with convert_scryfall_braces)."""
    tagged = re.sub(r"\{([^{}\s]+)\}", r"<sym>\1</sym>", text)
    return tagged.replace("</sym><sym>", "")


def is_planeswalker(face: Face) -> bool:
    return "planeswalker" in split_type_line(face.type_line)[0].lower()


LOYALTY_COST = re.compile(r"^\s*([+\-−–]?\s*(?:\d+|X))\s*:\s*(.*)$")
MAX_LOYALTY_ABILITIES = 4          # the planeswalker frames have four cost boxes


def loyalty_abilities(rules_text: str) -> list[tuple[str, str]]:
    """Planeswalker rules text, one ability per line -> (cost, text) pairs.
    "+1: Draw a card." -> ("+1", "Draw a card."); a line without a cost (a static
    ability) gets cost "". Unicode minus signs become "-", which MSE expects."""
    out = []
    for line in rules_text.split("\n"):
        match = LOYALTY_COST.match(line)
        if match:
            cost = re.sub(r"\s+", "", match.group(1)).replace("−", "-").replace("–", "-")
            out.append((cost, match.group(2)))
        else:
            out.append(("", line))
    return out


def face_values(card: Card, face: Face, reminders: dict[str, bool] | None = None,
                forms: dict[str, list[str]] | None = None) -> dict[str, str]:
    """`reminders`: mechanic name -> show its reminder text on this card (see mechanics.py);
    `forms`: mechanic name -> word forms that count as a mention too."""
    from .mechanics import tag_reminders
    supertype, subtype = split_type_line(face.type_line)
    rules_text = face.rules_text
    costs: dict[str, str] = {}
    if is_planeswalker(face):
        abilities = loyalty_abilities(rules_text)
        rules_text = "\n".join(text for _, text in abilities)
        costs = {f"loyalty cost {i}": cost
                 for i, (cost, _) in enumerate(abilities[:MAX_LOYALTY_ABILITIES], 1)}
    values = {
        "name": face.name,
        "casting cost": mse_mana_cost(face.mana_cost),
        "super type": supertype,
        "sub type": subtype,
        "rule text": mse_text(tag_reminders(rules_text, reminders or {}, forms)),
        **costs,
        "flavor text": mse_text(face.flavor_text),
        "power": face.power or "",
        "toughness": face.toughness or "",
        "loyalty": face.loyalty or "",
        "rarity": MSE_RARITY[card.rarity],
        "indicator": mse_color_indicator(face.color_indicator),
        "illustrator": face.artist,
    }
    # Leave empty optional values unset so MSE's defaults apply (e.g. illustrator
    # defaults to the set's artist, indicator to the card color).
    return {k: v for k, v in values.items() if v != "" or k in ("name", "casting cost", "rule text")}


def set_values(info: SetInfo, resolve: Callable[[str], Path | None] | None = None) -> dict[str, str]:
    """Set fields we know, as MSE set field values (unset ones keep MSE's defaults).
    `resolve` turns the set's relative symbol path into a full one (SetProject.resolve)."""
    symbol = resolve(info.symbol_path) if resolve and info.symbol_path else info.symbol_path
    values = {"title": info.name, "set code": info.code, "artist": info.artist,
              "copyright": info.copyright, "card language": info.language,
              "symbol": str(symbol or "")}
    return {k: v for k, v in values.items() if v}


def card_to_mse(card: Card, set_info: SetInfo, reminders: dict[str, bool] | None = None,
                resolve: Callable[[str], Path | None] | None = None,
                forms: dict[str, list[str]] | None = None) -> list[MSECard]:
    """The MSE cards for one of our cards (one per face), linked if multi-faced.
    `reminders` are this card's reminder-text choices per mechanic name
    (mechanics.reminder_choices); use mechanics.project_to_mse for a whole project.
    `resolve` turns relative art paths into full ones (SetProject.resolve)."""
    out = []
    for index, face in card.iter_faces():
        art_path = (resolve(face.art_path) if resolve else Path(face.art_path)) if face.art_path else None
        frame, planeswalker = card.frame_for(index, set_info.default_frame), is_planeswalker(face)
        out.append(MSECard(
            uid=face_uid(card, index),
            stylesheet=stylesheet_package(frame, planeswalker=planeswalker),
            values=face_values(card, face, reminders, forms),
            notes=card.notes,
            art=ArtRef(art_path, face.art_crop) if art_path is not None else None,
            styling=frame_styling(frame, planeswalker=planeswalker),
        ))
    relations = LAYOUTS[card.layout].mse_relations
    if relations and len(out) == 2:
        front, back = out
        front.links.append((back.uid, relations[1]))     # the back is my "Back Face"
        back.links.append((front.uid, relations[0]))     # the front is my "Front Face"
    return out
