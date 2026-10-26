"""Our model seen through MSE's scripts (field values, links, frames).
Exact agreement with real MSE is checked in tests/script/test_oracle.py (cards cases)."""
from pathlib import Path

import pytest

from fixtures.oracle_project import oracle_project
from setdesigner.model import Card, Face
from setdesigner.mse.mapping import (card_to_mse, loyalty_abilities, mse_color_indicator,
                                     mse_mana_cost, split_type_line)
from setdesigner.mse.script import run
from setdesigner.mse.script.builtins.tags import strip_tags

PACKAGES = Path(__file__).resolve().parents[1] / "resources" / "mse_packages"
needs_packages = pytest.mark.skipif(not PACKAGES.is_dir(), reason="resources/mse_packages not populated")


# ------------------------------------------------------------------ mapping

def test_mana_cost_conversion() -> None:
    assert mse_mana_cost("{2}{W}{W}") == "2WW"
    assert mse_mana_cost("{W/U}{X}") == "W/UX"
    assert mse_mana_cost("") == ""


def test_type_line_split() -> None:
    assert split_type_line("Legendary Creature — Elf Warrior") == ("Legendary Creature", "Elf Warrior")
    assert split_type_line("Instant") == ("Instant", "")
    assert split_type_line("Creature - Bear") == ("Creature", "Bear")


def test_color_indicator() -> None:
    assert mse_color_indicator("UR") == "blue, red"
    assert mse_color_indicator("Red, Green") == "red, green"
    assert mse_color_indicator("") == ""


def test_dfc_faces_become_linked_mse_cards() -> None:
    project = oracle_project()
    front, back = card_to_mse(project.card("delver"), project.info)
    assert (front.uid, back.uid) == ("delver/1", "delver/2")
    assert front.links == [("delver/2", "Back Face")]
    assert back.links == [("delver/1", "Front Face")]
    assert "casting cost" not in back.values or back.values["casting cost"] == ""


def test_face_frame_override_picks_stylesheet() -> None:
    project = oracle_project()
    card = Card(id="x", frame="old", faces=[Face(name="A")])
    assert card_to_mse(card, project.info)[0].stylesheet == "magic-old"


def test_loyalty_abilities_split() -> None:
    text = "+1: Draw a card.\n−2: Shock.\nStatic text\n-X: Boom.\n0: Rest."
    assert loyalty_abilities(text) == [("+1", "Draw a card."), ("-2", "Shock."), ("", "Static text"),
                                       ("-X", "Boom."), ("0", "Rest.")]


def test_planeswalker_gets_its_frame_and_ability_costs() -> None:
    project = oracle_project()
    card = Card(id="pw", frame="8th", faces=[Face(name="Ember", type_line="Legendary Planeswalker — Ember",
                                                  rules_text="+1: Draw a card.\n−3: Shock.", loyalty="4")])
    mse = card_to_mse(card, project.info)[0]
    assert mse.stylesheet == "magic-new-planeswalker"
    assert mse.values["loyalty cost 1"] == "+1" and mse.values["loyalty cost 2"] == "-3"
    assert mse.values["rule text"] == "Draw a card.\nShock."
    assert mse.values["loyalty"] == "4"
    creature = Card(id="c", faces=[Face(name="Bear", type_line="Creature — Planeswalker Hunter")])
    assert "planeswalker" not in card_to_mse(creature, project.info)[0].stylesheet


# -------------------------------------------------------------- environment

@pytest.fixture(scope="module")
def env():
    from setdesigner.mse.environment import ScriptEnvironment
    return ScriptEnvironment(oracle_project(), PACKAGES)


@needs_packages
def test_field_values(env) -> None:
    bears = env.card_values(env.project.card("grizzly-bears"))
    assert bears["cmc"] == "2"
    assert bears["card color"] == "green"
    assert strip_tags(bears["type"]).strip() == "Creature — Bear"     # MSE adds a soft space
    assert bears["card number"] == "0003"
    assert strip_tags(bears["pt"]) == "2/2"
    assert bears["illustrator"] == "Jeff A. Menges"
    assert len(bears) > 200                     # every MSE card field has a value


@needs_packages
def test_field_scripts_all_run(env) -> None:
    """A failing field script would fall back to its raw value with a warning; none do."""
    card = env.card_object(env.project.card("lightning-helix"))
    card.fields.all()
    assert card.warnings == []


@needs_packages
def test_links_and_scripts_see_the_card(env) -> None:
    delver = env.project.card("delver")
    front, back = env.card_object(delver, 0), env.card_object(delver, 1)
    ctx = env.context(env.default_style)
    assert run("get_front_face(c).name", {"c": back}, ctx=ctx) == "Delver of Secrets"
    assert run("get_back_face(c) == nil", {"c": back}, ctx=ctx) is True
    assert run("is_linked_dfc()", {"card": front}, ctx=ctx) is True
    assert front.script_member("linked_relation_1") == "Back Face"


@needs_packages
def test_styling_and_extra_card(env) -> None:
    card = env.card_object(env.project.card("grizzly-bears"))
    assert card.script_member("styling").script_member("tap_symbol") == "modern"
    assert card.extra_card.script_member("nonexistent") .message.startswith("extra card has no member")


@needs_packages
def test_other_frames_use_their_own_scripts() -> None:
    from setdesigner.mse.environment import ScriptEnvironment
    project = oracle_project()
    project.card("grizzly-bears").frame = "old"
    env = ScriptEnvironment(project, PACKAGES)
    bears = env.card_object(project.card("grizzly-bears"))
    assert bears.style == "magic-old"
    assert bears.fields.get("cmc") == "2"
    assert env.load_reports["magic-old"].failures == []
