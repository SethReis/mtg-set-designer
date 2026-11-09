"""Where a card's editable parts are (CardRenderer.field_boxes), for the editor's hotspots.
Needs the templates, not MSE."""
from pathlib import Path

import pytest

from fixtures.oracle_project import oracle_project
from setdesigner.model import Card, Face
from setdesigner.render import CardRenderer

PACKAGES = Path(__file__).resolve().parents[2] / "resources" / "mse_packages"
pytestmark = pytest.mark.skipif(not PACKAGES.is_dir(), reason="resources/mse_packages not populated")


@pytest.fixture(scope="module")
def renderer():
    project = oracle_project()
    project.cards.append(Card(id="old-bear", frame="old", faces=[
        Face(name="Old Bear", mana_cost="{1}{G}", type_line="Creature — Bear", power="2", toughness="2")]))
    return CardRenderer(project, use_mse=False)


def inside(box) -> bool:
    left, top, width, height = box
    return 0 <= left and 0 <= top and width > 0 and height > 0 and left + width <= 1 and top + height <= 1


def test_an_m15_creature_has_its_parts_in_order(renderer) -> None:
    boxes = renderer.field_boxes(renderer.project.card("grizzly-bears"))
    assert {"name", "cost", "type", "text", "pt", "art"} <= set(boxes)
    assert all(inside(box) for box in boxes.values())
    assert boxes["name"][1] < boxes["art"][1] < boxes["type"][1] < boxes["text"][1]   # top to bottom
    assert boxes["cost"][0] > boxes["name"][0]                                         # cost on the right
    assert boxes["pt"][0] > 0.6 and boxes["pt"][1] > 0.8                               # bottom right


def test_a_planeswalker_has_loyalty(renderer) -> None:
    boxes = renderer.field_boxes(renderer.project.card("ajani-goldmane"))
    assert "loyalty" in boxes and "text" in boxes and all(inside(box) for box in boxes.values())


def test_a_back_face_has_its_color_indicator(renderer) -> None:
    assert "indicator" in renderer.field_boxes(renderer.project.card("delver"), 1)


def test_old_frames_have_their_own_boxes(renderer) -> None:
    old = renderer.field_boxes(renderer.project.card("old-bear"))
    m15 = renderer.field_boxes(renderer.project.card("grizzly-bears"))
    assert {"name", "type", "text"} <= set(old) and all(inside(box) for box in old.values())
    assert old["name"] != m15["name"]
