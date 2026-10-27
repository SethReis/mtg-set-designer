"""The set overview, driven by NiceGUI's simulated user (built-in renderer, no MSE)."""
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from setdesigner.model import Rarity

MAIN = str(Path(__file__).with_name("main_app.py"))
pytestmark = pytest.mark.nicegui_main_file(MAIN)


@pytest.fixture(autouse=True)
def test_dir(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("SETDESIGNER_TEST_DIR", str(tmp_path))
    monkeypatch.setenv("SETDESIGNER_CACHE_DIR", str(tmp_path / "cache"))
    return tmp_path


def state():
    from setdesigner.ui.app import STATE
    return STATE


async def open_set_with_cards(user: User):
    await user.open("/")
    user.find("Set name").type("Test Set")
    user.find("Code (3-4 letters)").type("TST")
    user.find("Create set").click()
    await user.should_see("Group by")
    session = state().session
    bear = session.new_card("Grizzly Bears")
    session.update(bear, "mana_cost", "{1}{G}")
    session.update(bear, "types", "Creature")
    angel = session.new_card("Serra Angel")
    session.update(angel, "mana_cost", "{3}{W}{W}")
    session.update(angel, "rarity", "uncommon")
    state().settings.tiles = "compact"            # no rendering needed in these tests
    await user.open("/set")
    return session, bear, angel


def select(user: User, label: str, value) -> None:
    element = next(iter(user.find(kind=ui.select, content=label).elements))
    element.value = value


async def test_opening_a_set_shows_the_overview(user: User) -> None:
    await open_set_with_cards(user)
    await user.should_see("White · 1")
    await user.should_see("Green · 1")
    await user.should_see("2 cards")


async def test_group_by_and_matrix(user: User) -> None:
    session, _, _ = await open_set_with_cards(user)
    session.project.info.rarity_slots = {Rarity.COMMON: 10}
    select(user, "Group by", "rarity")
    await user.should_see("Common · 1 / 10")
    await user.should_see("Uncommon · 1")
    user.find("Matrix").click()
    await user.should_see("Rows")
    await user.should_see("Common · 1")           # column heading


async def test_tile_opens_editor_and_back_keeps_grouping(user: User) -> None:
    _, bear, _ = await open_set_with_cards(user)
    select(user, "Group by", "mana_value")
    await user.should_see("Mana value 2 · 1")
    user.find(marker=f"tile-{bear.id}").click()
    await user.should_see("Rules text")
    await user.should_see("Grizzly Bears")
    user.find(marker="back").click()
    await user.should_see("Group by")
    await user.should_see("Mana value 2 · 1")


async def test_filters_hide_targets(user: User) -> None:
    session, _, _ = await open_set_with_cards(user)
    session.project.info.rarity_slots = {Rarity.COMMON: 10}
    select(user, "Group by", "rarity")
    await user.should_see("Common · 1 / 10")
    user.find("Search name, type, rules").type("angel")
    await user.should_see("1 of 2 cards")
    await user.should_see("Common · 0")
    await user.should_not_see("Common · 0 / 10")      # partial counts: no targets


async def test_archetype_groups(user: User) -> None:
    session, bear, _ = await open_set_with_cards(user)
    ramp = session.new_archetype("UG Ramp", "UG")
    session.update_archetype(ramp, targets={"common": 5})
    session.update(bear, "archetypes", [ramp.id])
    await user.open("/set")
    select(user, "Group by", "archetype")
    await user.should_see("UG Ramp · 1 / 5")
    await user.should_see("No archetype · 1")
