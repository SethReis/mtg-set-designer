"""Set-health roles: detection from real-style rules text, and per-card overrides."""
import pytest

from setdesigner.app.health.roles import detected_roles, plain_text, roles
from setdesigner.model import Card, Face


def card(text: str, types: str = "Instant", name: str = "Test Card") -> Card:
    return Card(id="t", faces=[Face(name=name, type_line=types, rules_text=text)])


@pytest.mark.parametrize("text, types, role", [
    ("Destroy target creature.", "Instant", "removal"),
    ("Exile target nonland permanent an opponent controls.", "Sorcery", "removal"),
    ("Shock deals 2 damage to any target.", "Instant", "removal"),
    ("Target creature gets -3/-3 until end of turn.", "Instant", "removal"),
    ("Target creature you control fights target creature you don't control.", "Sorcery", "removal"),
    ("Return target creature to its owner's hand.", "Instant", "removal"),
    ("Enchant creature\nEnchanted creature can't attack or block.", "Enchantment — Aura", "removal"),
    ("Counter target noncreature spell.", "Instant", "counterspell"),
    ("Draw two cards.", "Sorcery", "card_draw"),
    ("When this creature enters, investigate.", "Creature", "card_draw"),
    ("Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
     "Sorcery", "ramp"),
    ("{T}: Add {G}.", "Creature — Elf Druid", "ramp"),
    ("{T}: Add one mana of any color.", "Artifact", "fixing"),
    ("{T}: Add {W} or {U}.", "Land", "fixing"),
    ("Flying", "Creature — Bird", "evasion"),
    ("This creature can't be blocked.", "Creature", "evasion"),
    ("Target creature gets +2/+2 until end of turn.", "Instant", "combat_trick"),
    ("Target creature you control gains indestructible until end of turn.", "Instant", "combat_trick"),
    ("Create two 1/1 white Soldier creature tokens.", "Sorcery", "token_maker"),
    ("You gain 3 life.", "Instant", "lifegain"),
    ("Lifelink", "Creature", "lifegain"),
])
def test_detects(text, types, role) -> None:
    assert role in detected_roles(card(text, types))


@pytest.mark.parametrize("text, types, role", [
    ("Target creature gets +2/+2 until end of turn.", "Sorcery", "combat_trick"),   # not at instant speed
    ("{T}: Add {G}.", "Land", "ramp"),                                             # lands aren't ramp
    ("{T}: Add {G}.", "Land", "fixing"),                                           # one color only
    ("Flying (This creature can't be blocked except by creatures with flying or reach.)", "Creature",
     "removal"),
    ("When this creature dies, you may draw a card.", "Creature", "removal"),
])
def test_does_not_detect(text, types, role) -> None:
    assert role not in detected_roles(card(text, types))


def test_plain_text_drops_reminders_and_names() -> None:
    c = card("Flying (Reminder.)\nWhen Test Card enters, CARDNAME deals 1 damage to any target.")
    assert plain_text(c) == "Flying \nWhen this enters, this deals 1 damage to any target."


def test_overrides_add_and_remove() -> None:
    c = card("Draw a card.")
    assert roles(c) == ["card_draw"]
    c.role_overrides = {"card_draw": False, "removal": True}
    assert roles(c) == ["removal"]
    assert detected_roles(c) == ["card_draw"]
