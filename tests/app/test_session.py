"""SetSession: the editor's behaviour without UI (uses the built-in renderer, so no MSE)."""
import json

import pytest

from setdesigner.app.session import AUTOSAVE_DELAY, SessionError, SetSession
from setdesigner.model import Mechanic


def builtin(project):
    from setdesigner.render import CardRenderer
    return CardRenderer(project, use_mse=False)


@pytest.fixture
def session(tmp_path):
    s = SetSession.create(tmp_path / "myset", "My Set", "mys", "m15", renderer_factory=builtin)
    yield s
    s.close()


def card_file(session, card):
    return session.folder / "cards" / f"{card.id}.json"


def test_create_and_open(tmp_path, session) -> None:
    assert session.project.info.code == "MYS"
    assert (session.folder / "set.json").is_file()
    with pytest.raises(SessionError):
        SetSession.create(session.folder, "Again", "AGN")          # already a set there
    with pytest.raises(SessionError):
        SetSession.open(tmp_path / "nothing")
    reopened = SetSession.open(session.folder)
    assert reopened.project.info.name == "My Set"


def test_new_cards_get_files_ids_and_numbers(session) -> None:
    a, b = session.new_card(), session.new_card()
    assert (a.id, b.id) == ("new-card", "new-card-2")
    assert (a.collector_number, b.collector_number) == ("1", "2")
    assert card_file(session, a).is_file() and card_file(session, b).is_file()


def test_autosave_waits_for_a_pause_then_writes(session) -> None:
    card = session.new_card()
    session.update(card, "name", "Grizzly Bears")
    assert session.unsaved
    assert session.flush_due() == []                          # too soon
    import time
    assert session.flush_due(time.monotonic() + AUTOSAVE_DELAY) == [card.id]
    data = json.loads(card_file(session, card).read_text(encoding="utf-8"))
    assert data["faces"][0]["name"] == "Grizzly Bears"
    assert card.id == "new-card"                               # ids never change on rename


def test_fields_are_converted(session) -> None:
    card = session.new_card()
    session.update(card, "rarity", "mythic")
    session.update(card, "power", " ")
    session.update(card, "frame", "")
    session.update(card, "status", "draft")
    session.flush()
    assert card.rarity.value == "mythic" and card.faces[0].power is None
    assert card.frame is None and card.status.value == "draft"
    with pytest.raises(SessionError):
        session.update(card, "nonsense", 1)


def test_types_and_subtypes_edit_the_type_line(session) -> None:
    card = session.new_card()
    session.update(card, "types", "Creature")
    assert card.faces[0].type_line == "Creature"               # no dash yet
    session.update(card, "subtypes", "Elf Druid")
    assert card.faces[0].type_line == "Creature — Elf Druid"
    session.update(card, "types", "Legendary Creature ")
    assert card.faces[0].type_line == "Legendary Creature — Elf Druid"
    session.update(card, "subtypes", "")
    assert card.faces[0].type_line == "Legendary Creature"


def test_duplicate_and_delete(session) -> None:
    card = session.new_card("Shock")
    session.update(card, "rules_text", "Shock deals 2 damage to any target.")
    copy = session.duplicate(card)
    assert copy.id == "shock-2" and copy.faces[0].rules_text == card.faces[0].rules_text
    assert copy.collector_number == "2"
    session.delete(card)
    assert not card_file(session, card).exists()
    assert [c.id for c in session.cards()] == ["shock-2"]


def test_search_and_order(session) -> None:
    a = session.new_card("Grizzly Bears")
    b = session.new_card("Shock")
    session.update(b, "collector_number", "0")
    session.update(a, "rules_text", "Trample")
    assert [c.id for c in session.cards()] == ["shock", "grizzly-bears"]
    assert [c.id for c in session.search("trample")] == ["grizzly-bears"]
    assert [c.id for c in session.search("SHO")] == ["shock"]


def test_render_follows_edits(session) -> None:
    card = session.new_card("Grizzly Bears")
    session.update(card, "mana_cost", "{1}{G}")
    session.update(card, "type_line", "Creature — Bear")
    first = session.render(card)
    session.update(card, "rules_text", "Trample")
    second = session.render(card)
    assert first.size == (375, 523) and first.tobytes() != second.tobytes()
    assert session.renderer_note == "built-in renderer"


def test_close_saves_pending_edits(tmp_path) -> None:
    s = SetSession.create(tmp_path / "s", "S", "S", renderer_factory=builtin)
    card = s.new_card()
    s.update(card, "name", "Saved On Close")
    s.close()
    assert SetSession.open(tmp_path / "s").cards()[0].faces[0].name == "Saved On Close"
