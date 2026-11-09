"""The design notebook view and quick capture (NiceGUI's simulated user)."""
from pathlib import Path

import pytest
from nicegui.testing import User

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


async def open_set(user: User):
    await user.open("/")
    user.find("Set name").type("Test Set")
    user.find("Code (3-4 letters)").type("TST")
    user.find("Create set").click()
    await user.should_see("No cards yet")
    state().settings.tiles = "text"
    await user.open("/set")
    return state().session


async def test_quick_capture_from_the_top_bar(user: User) -> None:
    session = await open_set(user)
    user.find(marker="catch-idea").click()
    await user.should_see("Catch an idea", retries=20)
    user.find(marker="capture-title").type("Blue needs an answer to fliers")
    user.find(marker="capture-save").click()
    await user.should_not_see(marker="capture-save", retries=20)
    assert [i.title for i in session.project.notebook] == ["Blue needs an answer to fliers"]
    assert session.project.notebook[0].lane == "inbox"


async def test_the_board_shows_ideas_and_makes_a_card(user: User) -> None:
    session = await open_set(user)
    idea = session.new_idea("card", "Surveil flier", sketch={"name": "Mistwing Scout", "type_line": "Creature — Bird"})
    user.find(marker="nav-notebook").click()
    await user.should_see(marker=f"idea-{idea.id}", retries=20)
    await user.should_see(marker="lane-promising")
    user.find(marker=f"idea-{idea.id}").click()
    await user.should_see(marker="idea-title", retries=20)
    user.find(marker="promote-card").click()
    await user.should_see("Mistwing Scout", retries=40)
    card = next(c for c in session.project.cards if c.faces[0].name == "Mistwing Scout")
    assert idea.lane == "used" and idea.links[0].id == card.id


async def test_a_card_from_an_idea_says_so_in_the_editor(user: User) -> None:
    session = await open_set(user)
    idea = session.new_idea("card", "A flier that surveils")
    card = session.promote_to_card(idea)
    await user.open(f"/set?card={card.id}")
    await user.should_see(marker="from-idea", retries=40)
    await user.should_see("From idea: A flier that surveils")
