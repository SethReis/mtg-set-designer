from setdesigner.app.text_input import apply, insert, suggestions
from setdesigner.model import Mechanic

MECHANICS = [Mechanic(id="b", name="Bloodpact", parameter="cost"),
             Mechanic(id="g", name="Glimmer")]


def labels(text, caret=None, mechanics=MECHANICS):
    return [s.label for s in suggestions(text, len(text) if caret is None else caret, mechanics)]


def test_symbols_after_an_open_brace() -> None:
    assert "{W}" in labels("Add {")
    assert labels("Add {W/")[:2] == ["{W/U}", "{W/B}"]
    assert labels("{T")[0].startswith("{T}")
    assert labels("{W} done") == []                           # closed brace
    assert labels("{hello world") == []                       # not a symbol


def test_mechanics_by_prefix() -> None:
    assert labels("Bl") == ["Bloodpact {cost}"]
    assert labels("Flying, gli") == ["Glimmer"]
    assert labels("B") == []                                   # needs 2 letters
    assert labels("Bloodpact") == []                           # already complete
    assert labels("Blxx", caret=2) == []                       # in the middle of a word


def test_apply_and_insert_move_the_caret() -> None:
    text = "Add {W"
    option = suggestions(text, len(text), MECHANICS)[0]
    assert apply(text, len(text), option) == ("Add {W}", 7)
    option = suggestions("Bl", 2, MECHANICS)[0]
    assert apply("Bl and more", 2, option) == ("Bloodpact {1} and more", 13)
    assert insert("Deals damage", 0, "CARDNAME ") == ("CARDNAME Deals damage", 9)
