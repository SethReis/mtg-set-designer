"""Printer-friendly cards: plain symbols, reminder text, fitting the text."""
import io
import re

from setdesigner.app.mechanics import with_reminders
from setdesigner.export.pdf import write_pdf
from setdesigner.export.playtest import markup, plain_symbols, playtest_drawer, printable
from setdesigner.export.selection import PrintOptions, print_faces
from setdesigner.export.sheet import fit, pages
from setdesigner.model import Card, Face, Mechanic, MechanicKind, Rarity, SetInfo, SetProject

CYCLING = Mechanic(id="cycling", name="Cycling", parameter="cost",
                   reminder_text="{cost}, Discard this card: Draw a card.")
SURVEIL = Mechanic(id="surveil", name="Surveil", kind=MechanicKind.KEYWORD_ACTION, parameter="number",
                   reminder_text="Look at the top {number} cards of your library.", reminder_policy="always")


def project(*cards) -> SetProject:
    p = SetProject(info=SetInfo(name="Test", code="TST"), mechanics=[CYCLING, SURVEIL])
    p.cards.extend(cards)
    return p


def card(card_id, text, rarity=Rarity.COMMON, **kw) -> Card:
    return Card(id=card_id, rarity=rarity, collector_number="1",
                faces=[Face(name=card_id.title(), rules_text=text)], **kw)


def test_plain_symbols() -> None:
    assert plain_symbols("{2}{W}{W}") == "2WW"
    assert plain_symbols("{T}, {Q}: Add {C}.") == "T, Q: Add C."
    assert plain_symbols("{W/U}{2/B}{G/P}{X}") == "(W/U)(2/B)(G/P)X"


def test_printable_and_markup() -> None:
    assert printable("−2: Draw ∞ cards — ok") == "-2: Draw inf cards — ok"
    assert printable("漢") == "?"
    assert markup("Flying (It can't be blocked.) & <more>") == \
        "Flying <i>(It can&#x27;t be blocked.)</i> &amp; &lt;more&gt;".replace("&#x27;", "'")


def test_keywords_get_their_reminder_after_the_value() -> None:
    common = card("bear", "Cycling {2}\nCycling {3}")
    p = project(common)
    assert with_reminders(p, common, common.faces[0].rules_text) == \
        "Cycling {2} ({2}, Discard this card: Draw a card.)\nCycling {3}"   # first mention only


def test_reminders_follow_the_policy_and_the_cards_choice() -> None:
    rare = card("dragon", "Cycling {2}", Rarity.RARE)
    chosen = card("chosen", "Cycling {1}", Rarity.RARE, reminders={"cycling": True})
    p = project(rare, chosen)
    assert with_reminders(p, rare, "Cycling {2}") == "Cycling {2}"       # commons only
    assert with_reminders(p, chosen, "Cycling {1}") == "Cycling {1} ({1}, Discard this card: Draw a card.)"


def test_keyword_actions_get_their_reminder_after_the_sentence() -> None:
    c = card("seer", "When this enters, surveil 2. Then draw a card.")
    p = project(c)
    assert with_reminders(p, c, c.faces[0].rules_text) == \
        "When this enters, surveil 2. (Look at the top 2 cards of your library.) Then draw a card."


def pdf(cards, p):
    overflow = []
    out = io.BytesIO()
    grid = fit("a4")
    write_pdf(out, pages(print_faces(cards, PrintOptions()), grid), grid, playtest_drawer(p, overflow))
    return out.getvalue(), overflow


def test_a_printer_friendly_page_is_text_only() -> None:
    c = card("bear", "Cycling {2}")
    data, overflow = pdf([c], project(c))
    assert overflow == [] and b"/Subtype /Image" not in data
    assert len(re.findall(rb"/Type /Page\b", data)) == 1


def test_text_that_cannot_fit_is_reported() -> None:
    long = card("wall", "This is a lot of text. " * 150)
    data, overflow = pdf([long], project(long))
    assert overflow == ["Wall"]
