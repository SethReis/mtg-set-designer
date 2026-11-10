"""The Balance view and the editor's balance badge (NiceGUI's simulated user)."""
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

MAIN = str(Path(__file__).with_name("main_app.py"))
pytestmark = pytest.mark.nicegui_main_file(MAIN)


@pytest.fixture(autouse=True)
def test_dir(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("SETDESIGNER_TEST_DIR", str(tmp_path))
    monkeypatch.setenv("SETDESIGNER_CACHE_DIR", str(tmp_path / "cache"))
    return tmp_path


async def open_set(user: User):
    from setdesigner.ui.app import STATE
    await user.open("/")
    user.find("Set name").type("Test Set")
    user.find("Code (3-4 letters)").type("TST")
    user.find("Create set").click()
    await user.should_see("No cards yet")
    STATE.settings.tiles = "text"
    session = STATE.session
    bird = session.new_card("Gull")
    for field, value in [("mana_cost", "{2}{U}"), ("type_line", "Creature — Bird"), ("rules_text", "Flying"),
                         ("power", "2"), ("toughness", "2")]:
        session.update(bird, field, value)
    await user.open("/set")
    return session, bird


async def test_a_card_opens_its_breakdown(user: User) -> None:
    session, bird = await open_set(user)
    user.find(marker="nav-balance").click()
    await user.should_see(marker=f"balance-card-{bird.id}", retries=20)
    user.find(marker=f"balance-card-{bird.id}").click()
    await user.should_see(marker="balance-parts", retries=20)
    await user.should_see("2/2 body")
    await user.should_see("Flying")


async def test_a_norm_changes_scores(user: User) -> None:
    session, bird = await open_set(user)
    user.find(marker="nav-balance").click()
    await user.should_see(marker="balance-tabs", retries=20)
    next(iter(user.find(marker="balance-tabs").elements)).value = "norms"
    await user.should_see(marker="norm-keyword.flying", retries=20)
    field = next(iter(user.find(marker="norm-keyword.flying").elements))
    field.value = 3
    user.find(marker="norm-keyword.flying").trigger("blur")
    assert session.project.info.balance.get("keyword.flying") == 3.0


async def test_the_editor_shows_a_balance_badge(user: User) -> None:
    session, bird = await open_set(user)
    await user.open(f"/set?card={bird.id}")
    await user.should_see(marker="balance-badge", retries=40)
    badge = next(iter(user.find(marker="balance-badge").elements))
    assert isinstance(badge, ui.label) and badge.text == "Balance: On curve"
