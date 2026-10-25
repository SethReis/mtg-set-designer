from fixtures.oracle_project import oracle_project
from setdesigner.model import (Archetype, Card, Face, FaceRole, Layout, Mechanic, Rarity,
                               load_project, save_project, validate_card)


def project_with_extras():
    project = oracle_project()
    project.mechanics.append(Mechanic(id="cycling", name="Cycling", parameter="cost",
                                      reminder_text="{cost}, Discard this card: Draw a card."))
    project.archetypes.append(Archetype(id="ug-flyers", name="UG Flyers", colors="UG",
                                        key_mechanics=["cycling"], targets={Rarity.COMMON: 6}))
    return project


def test_round_trip(tmp_path) -> None:
    project = project_with_extras()
    save_project(project, tmp_path)
    assert (tmp_path / "cards" / "delver.json").is_file()
    project.cards.sort(key=lambda c: c.id)          # cards load in id (file name) order
    assert load_project(tmp_path) == project


def test_save_removes_deleted_cards(tmp_path) -> None:
    project = oracle_project()
    save_project(project, tmp_path)
    project.cards = [c for c in project.cards if c.id != "forest"]
    save_project(project, tmp_path)
    assert not (tmp_path / "cards" / "forest.json").exists()


def test_color_identity_spans_faces() -> None:
    project = oracle_project()
    assert project.card("delver").color_identity == "U"
    assert project.card("boros-guildmage").color_identity == "WR"
    assert project.card("steel-overseer").color_identity == ""


def test_iter_faces() -> None:
    names = [face.name for _, _, face in oracle_project().iter_faces()]
    assert "Insectile Aberration" in names and len(names) == 8


def test_fixture_cards_are_valid() -> None:
    assert {c.id: validate_card(c) for c in oracle_project().cards if validate_card(c)} == {}


def test_validation_messages() -> None:
    bad = Card(id="x", layout=Layout.TRANSFORM, faces=[
        Face(name="Front"),
        Face(name="Back", role=FaceRole.BACK, mana_cost="{U}", power="1"),
    ])
    problems = validate_card(bad)
    assert any("should not have a mana cost" in p for p in problems)
    assert any("power or toughness but not both" in p for p in problems)
    assert validate_card(Card(id="y", layout=Layout.TRANSFORM, faces=[Face(name="Only")])) == [
        "transform cards need 2 face(s), this one has 1"]


def test_frame_resolution() -> None:
    card = Card(id="z", frame="old", faces=[Face(name="A"), Face(name="B", frame="m15")])
    assert card.frame_for(0, "m15") == "old"
    assert card.frame_for(1, "4th") == "m15"
