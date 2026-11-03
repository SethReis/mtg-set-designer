"""Which faces a print holds, how many copies and in what order."""
from setdesigner.export.selection import PrintOptions, copies, print_faces
from setdesigner.model import Card, Face, Layout, Rarity


def card(card_id, number, rarity=Rarity.COMMON, cost="", faces=1, **kw):
    return Card(id=card_id, collector_number=str(number), rarity=rarity,
                layout=Layout.TRANSFORM if faces == 2 else Layout.NORMAL,
                faces=[Face(name=f"{card_id} {i}", mana_cost=cost if i == 0 else "")
                       for i in range(faces)], **kw)


def keys(faces):
    return [(f.card.id, f.face, f.copy) for f in faces]


def test_one_of_each_prints_every_card_once() -> None:
    cards = [card("b", 2, Rarity.MYTHIC), card("a", 1)]
    assert keys(print_faces(cards, PrintOptions(distribution="cube"))) == [("a", 0, 0), ("b", 0, 0)]


def test_by_rarity_repeats_cards_and_keeps_copies_together() -> None:
    cards = [card("c", 1), card("u", 2, Rarity.UNCOMMON), card("r", 3, Rarity.RARE)]
    options = PrintOptions(distribution="rarity", copies={"common": 3, "uncommon": 2, "rare": 1})
    assert keys(print_faces(cards, options)) == [
        ("c", 0, 0), ("c", 0, 1), ("c", 0, 2), ("u", 0, 0), ("u", 0, 1), ("r", 0, 0)]


def test_a_card_can_override_its_copies() -> None:
    options = PrintOptions(distribution="rarity")
    assert copies(card("a", 1, print_copies=7), options) == 7
    assert copies(card("a", 1, print_copies=0), options) == 0
    assert copies(card("a", 1, print_copies=7), PrintOptions(distribution="cube")) == 1


def test_two_faced_cards_print_front_then_back() -> None:
    cards = [card("dfc", 1, faces=2), card("next", 2)]
    options = PrintOptions(distribution="rarity", copies={"common": 2})
    assert keys(print_faces(cards, options)) == [
        ("dfc", 0, 0), ("dfc", 1, 0), ("dfc", 0, 1), ("dfc", 1, 1), ("next", 0, 0), ("next", 0, 1)]


def test_sort_orders() -> None:
    cards = [card("red", 1, Rarity.RARE, "{R}"), card("white", 2, Rarity.COMMON, "{W}"),
             card("blue", 3, Rarity.UNCOMMON, "{U}")]
    order = lambda by: [f.card.id for f in print_faces(cards, PrintOptions(sort=by))]  # noqa: E731
    assert order("number") == ["red", "white", "blue"]
    assert order("color") == ["white", "blue", "red"]
    assert order("rarity") == ["white", "blue", "red"]


def test_saved_options_round_trip_and_bad_values_fall_back() -> None:
    options = PrintOptions(distribution="rarity", bleed_mm=1.0, paper="letter")
    options.copies["common"] = 5
    assert PrintOptions.from_dict(options.to_dict()) == options
    loaded = PrintOptions.from_dict({"distribution": "nonsense", "bleed_mm": "x", "copies": {"common": -2},
                                     "unknown": 1, "crop_marks": False})
    assert loaded.distribution == "cube" and loaded.bleed_mm == 0.0 and not loaded.crop_marks
    assert loaded.copies["common"] == 0 and loaded.copies["uncommon"] == 2
