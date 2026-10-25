"""The start page and editor, driven by NiceGUI's simulated user (no browser needed)."""
import json
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

MAIN = str(Path(__file__).with_name("main_app.py"))
pytestmark = pytest.mark.nicegui_main_file(MAIN)


@pytest.fixture(autouse=True)
def test_dir(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("SETDESIGNER_TEST_DIR", str(tmp_path))
    return tmp_path


def state():
    from setdesigner.ui.app import STATE
    return STATE


async def create_set(user: User) -> None:
    await user.open("/")
    user.find("Set name").type("Test Set")
    user.find("Code (3-4 letters)").type("TST")
    user.find("Create set").click()
    await user.should_see("New card")


async def test_create_set_opens_the_editor(user: User, test_dir: Path) -> None:
    await create_set(user)
    assert (test_dir / "sets" / "tst" / "set.json").is_file()
    await user.should_see("No cards yet")


async def test_new_card_and_edit_are_saved(user: User, test_dir: Path) -> None:
    await create_set(user)
    user.find("New card").click()
    await user.should_see("New Card")
    user.find("Name").type(" Bear")                     # appends to "New Card"
    await user.should_see("New Card Bear")
    state().session.flush()
    data = json.loads((test_dir / "sets" / "tst" / "cards" / "new-card.json").read_text(encoding="utf-8"))
    assert data["faces"][0]["name"] == "New Card Bear"


async def test_reopen_from_recent(user: User, test_dir: Path) -> None:
    await create_set(user)
    state().close()
    await user.open("/")
    await user.should_see("Recent")
    user.find(content="tst").click()
    await user.should_see("New card")
