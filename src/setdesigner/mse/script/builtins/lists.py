"""Collections: length, number_of_items, position, filter_list, sort_list.

`length`, `number_of_items` and `position` also accept a *set*, meaning its cards;
then `filter` and `order_by` are functions evaluated with `card` bound to each card
(this is how the game numbers cards: position(of: card, in: set, order_by: ...)).
"""
from __future__ import annotations

from ..spec_sort import sort_spec
from ..values import equal, is_number, iterate, to_bool, to_str
from .registry import builtin


def _is_set(value) -> bool:
    return hasattr(value, "script_items") and hasattr(value, "cards")


def _set_cards(set_obj, script, filter=None, order_by=None) -> list:
    cards = list(set_obj.cards)
    if filter is not None:
        cards = [c for c in cards if to_bool(script.call(filter, card=c))]
    if order_by is not None:
        cards.sort(key=lambda c: to_str(script.call(order_by, card=c)))
    return cards


@builtin("length")
def length(input):
    if isinstance(input, str):
        return len(input)
    return len(iterate(input))


@builtin("number_of_items", rename={"in_": "in"})
def number_of_items(in_, script, filter=None):
    """Like length (deprecated in MSE). For text, `filter` is a sort_text order spec
    applied first, e.g. number_of_items(in: colors, filter: "<WUBRG>"); for a set,
    it is a function selecting cards."""
    if _is_set(in_):
        return len(_set_cards(in_, script, filter))
    if isinstance(in_, str) and filter is not None:
        return len(sort_spec(to_str(filter), in_))
    return length(in_)


@builtin("position", rename={"in_": "in"})
def position(of, in_, script, order_by=None, filter=None):
    """Index of `of` in a string, collection or set (cards filtered and ordered), or -1."""
    if _is_set(in_):
        cards = _set_cards(in_, script, filter, order_by)
        return next((i for i, card in enumerate(cards) if card is of), -1)
    if isinstance(in_, str):
        return in_.find(to_str(of))
    for i, (_, value) in enumerate(iterate(in_)):
        if equal(value, of):
            return i
    return -1


@builtin("filter_list")
def filter_list(input, filter, script):
    """The items for which filter(input: item) is true (map keys are dropped)."""
    return [v for _, v in iterate(input) if to_bool(script.call(filter, input=v))]


def _sort_key(value):
    # numbers before text; numbers by value, text by character
    return (0, value, "") if is_number(value) else (1, 0, to_str(value))


@builtin("sort_list")
def sort_list(input, script, order_by=None, remove_duplicates=False):
    """Sort a collection (or the characters of a string), optionally by order_by(input: item)."""
    if isinstance(input, str):
        chars = sorted(input)
        if remove_duplicates:
            chars = sorted(set(chars))
        return "".join(chars)
    items = [v for _, v in iterate(input)]
    if order_by is not None:
        keyed = [(_sort_key(script.call(order_by, input=v)), v) for v in items]
    else:
        keyed = [(_sort_key(v), v) for v in items]
    keyed.sort(key=lambda kv: kv[0])
    out = []
    for _, v in keyed:
        if not (remove_duplicates and out and equal(out[-1], v)):
            out.append(v)
    return out
