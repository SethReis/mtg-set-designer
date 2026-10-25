"""Card links (MSE 2.6): get_card_from_uid, get_cards_from_link, get_link_from_cards,
get_front_face, get_back_face.

Each card lists the cards it is linked to and *their* relation to it: the front
face of a transform card links to its back with relation "Back Face", the back
links to the front with "Front Face". Cards are found through the `set` variable
(a SetObject, see mse/objects.py).
"""
from __future__ import annotations

from ..values import ScriptError, ScriptFunction, is_object, to_str
from .registry import builtin


def _set(script):
    set_obj = script.var("set")
    if not hasattr(set_obj, "card_by_uid"):
        raise ScriptError("card links need a set with cards")
    return set_obj


def _card(value, what: str = "input"):
    if not is_object(value) or not hasattr(value, "links"):
        raise ScriptError(f"{what} must be a card")
    return value


def _relation(card, other) -> str | None:
    """How `card` names its link to `other` (other's relation), or None."""
    return next((rel for uid, rel in card.links if uid == other.uid), None)


@builtin("get_card_from_uid")
def get_card_from_uid(input, script):
    return _set(script).card_by_uid(to_str(input))


@builtin("get_cards_from_link")
def get_cards_from_link(input, linked_relation, script):
    """The cards linked to `input` whose relation to it is `linked_relation`."""
    set_obj, relation = _set(script), to_str(linked_relation)
    found = (set_obj.card_by_uid(uid) for uid, rel in _card(input).links if rel == relation)
    return [card for card in found if card is not None]


@builtin("get_link_from_cards")
def get_link_from_cards(input, linked_card, script):
    """[input's relation to linked_card, linked_card's relation to input] (nil if unlinked)."""
    card, other = _card(input), _card(linked_card, "linked_card")
    return [_relation(other, card), _relation(card, other)]


def _game_script(script, key: str, card):
    node = _set(script).env.game_script(key)
    return script.call(ScriptFunction(node), input=_card(card))


@builtin("get_front_face")
def get_front_face(input, script):
    """Runs the game's `get front face script` (nil unless input is a back face)."""
    return _game_script(script, "get front face script", input)


@builtin("get_back_face")
def get_back_face(input, script):
    """Runs the game's `get back face script` (nil unless input has a back face)."""
    return _game_script(script, "get back face script", input)
