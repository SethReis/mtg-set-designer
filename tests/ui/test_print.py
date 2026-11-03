"""The Print dialog, driven by NiceGUI's simulated user (built-in renderer, no MSE)."""
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


async def open_set(user: User, print_options: dict | None = None):
    await user.open("/")
    user.find("Set name").type("Test Set")
    user.find("Code (3-4 letters)").type("TST")
    user.find("Create set").click()
    await user.should_see("No cards yet")
    session = state().session
    session.new_card("Grizzly Bears")
    rare = session.new_card("Shivan Dragon")
    session.update(rare, "rarity", "rare")
    state().settings.tiles = "text"
    state().settings.print_options = {"paper": "a4", **(print_options or {})}
    await user.open("/set")
    return session


def choose(user: User, marker: str, value: str) -> None:
    user.find(marker=marker).elements.pop().value = value


async def test_rail_opens_print_and_copies_change_the_count(user: User) -> None:
    await open_set(user)
    user.find(marker="nav-print").click()
    await user.should_see("Export PDF")
    await user.should_see("2 cards · 1 page · 3 × 3 per page")
    choose(user, "print-copies", "rarity")              # 4 commons + 1 rare
    await user.should_see("5 cards · 1 page · 3 × 3 per page")
    assert state().settings.print_options["distribution"] == "rarity"   # remembered


async def test_a_cards_own_copies_win(user: User) -> None:
    session = await open_set(user, {"distribution": "rarity"})
    session.update(session.project.cards[0], "print_copies", 9)
    await user.open("/set?open=print")
    await user.should_see("10 cards · 2 pages · 3 × 3 per page")


async def test_current_filter_is_offered_while_filtering(user: User) -> None:
    await open_set(user)
    user.find("Search name, type, rules").type("Shivan")
    await user.should_see("1 of 2 cards")
    user.find(marker="nav-print").click()
    await user.should_see("Current filter · 1")
    choose(user, "print-scope", "filter")
    await user.should_see("1 card · 1 page · 3 × 3 per page")


async def test_export_writes_a_pdf(user: User, tmp_path, monkeypatch) -> None:
    out = tmp_path / "out"
    out.mkdir()
    import setdesigner.ui.print_dialog as print_dialog
    monkeypatch.setattr(print_dialog.tempfile, "mkdtemp", lambda **_: str(out))
    await open_set(user, {"style": "friendly"})          # text only: quick, no renderer
    await user.open("/set?open=print")
    await user.should_see("Export PDF")
    user.find(marker="print-export").click()
    await user.should_see("Saved 1 page to TST-print.pdf", retries=40)
    assert (out / "TST-print.pdf").read_bytes().startswith(b"%PDF")
    assert state().settings.print_folder == str(out)
