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
    monkeypatch.setenv("SETDESIGNER_CACHE_DIR", str(tmp_path / "cache"))
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


async def test_create_set_opens_the_overview(user: User, test_dir: Path) -> None:
    await create_set(user)
    assert (test_dir / "sets" / "tst" / "set.json").is_file()
    await user.should_see("No cards yet")


async def test_new_card_and_edit_are_saved(user: User, test_dir: Path) -> None:
    await create_set(user)
    user.find("New card").click()
    await user.should_see("On this card")
    user.find(marker="row-name").click()                # the side panel's line opens its editor
    await user.should_see(marker="face-name", retries=20)
    user.find(marker="face-name").type(" Bear")         # appends to "New Card"
    await user.should_see("New Card Bear")
    state().session.flush()
    data = json.loads((test_dir / "sets" / "tst" / "cards" / "new-card.json").read_text(encoding="utf-8"))
    assert data["faces"][0]["name"] == "New Card Bear"


async def test_reopen_from_recent(user: User, test_dir: Path) -> None:
    await create_set(user)
    state().close()
    await user.open("/")
    await user.should_see("Recent")
    user.find(marker="recent-tst").click()
    await user.should_see("New card")


async def test_a_slow_preview_after_the_editor_closed_is_dropped(user: User, caplog) -> None:
    """At startup the renderer can be busy (card pictures, checking MSE): a preview that
    finishes after the editor closed mustn't touch the removed preview."""
    import asyncio
    import time

    await create_set(user)
    session = state().session
    card = session.new_card("Grizzly Bears")
    render = session.render
    session.render = lambda c, face=0: (time.sleep(1.0), render(c, face))[1]
    await user.open(f"/set?card={card.id}")
    await user.should_see("On this card")
    await asyncio.sleep(0.3)                                 # the preview has started
    user.find(marker="modal-close").click()
    await asyncio.sleep(1.5)                                 # ...and finishes after the close
    assert "deleted but is still being used" not in caplog.text


async def test_two_faced_cards_edit_each_face(user: User) -> None:
    import asyncio

    await create_set(user)
    session = state().session
    card = session.new_card("Village Messenger")
    await user.open(f"/set?card={card.id}")
    await user.should_see("On this card")
    user.find(marker="card-layout").elements.pop().value = "transform"
    await user.should_see("Back · (no name)", retries=20)          # the new back is shown
    await user.should_see(marker="row-indicator")                   # backs: a color indicator
    await user.should_not_see(marker="row-cost")                    # transform backs: no cost
    user.find(marker="row-name").click()
    await user.should_see(marker="face-name", retries=20)
    user.find(marker="face-name").type("Moonrise Intruder")
    await user.should_see("Village Messenger // Moonrise Intruder", retries=20)   # list and title
    assert card.faces[1].name == "Moonrise Intruder" and card.faces[0].name == "Village Messenger"

    user.find(marker="flip-face").click()                           # back to the front
    await asyncio.sleep(0.3)
    await user.should_see(marker="row-cost")
    await user.should_see(marker="transform-symbol")

    user.find(marker="card-layout").elements.pop().value = "normal"  # the back has content
    await user.should_see("Remove the back face “Moonrise Intruder”?", retries=20)
    assert len(card.faces) == 2                                      # not before you confirm


async def open_card(user: User, **values):
    await create_set(user)
    session = state().session
    card = session.new_card("Grizzly Bears")
    for field, value in values.items():
        session.update(card, field, value)
    await user.open(f"/set?card={card.id}")
    await user.should_see("On this card")
    return session, card


async def wait_for_hotspots(user: User) -> None:
    """The parts appear on the card once its layout has been measured (with the preview)."""
    await user.should_see(marker="part-name", retries=40)


async def test_clicking_a_part_of_the_card_edits_it(user: User) -> None:
    session, card = await open_card(user, types="Creature")
    await wait_for_hotspots(user)
    for part in ("name", "cost", "type", "text", "pt", "art"):     # an M15 creature's parts
        await user.should_see(marker=f"part-{part}")
    user.find(marker="part-name").click()
    await user.should_see(marker="face-name", retries=20)
    user.find(marker="face-name").clear().type("Runeclaw Bear")
    assert card.faces[0].name == "Runeclaw Bear"


async def test_the_rules_editor_suggests_symbols_and_saves_flavor(user: User) -> None:
    session, card = await open_card(user)
    await wait_for_hotspots(user)
    user.find(marker="part-text").click()
    await user.should_see("Flavor text", retries=20)
    user.find("Rules text").type("Add {")
    await user.should_see("Tab to accept the first", retries=20)   # symbol suggestions
    user.find("Flavor text").type("Grr.")
    assert card.faces[0].flavor_text == "Grr."
    assert card.faces[0].rules_text.startswith("Add {")


async def test_tab_moves_to_the_next_part(user: User) -> None:
    session, card = await open_card(user)
    await wait_for_hotspots(user)
    user.find(marker="part-name").click()
    await user.should_see(marker="editor-name", retries=20)
    user.find(marker="editor-name").trigger("keydown", 1)          # Tab out of the last field
    await user.should_see(marker="editor-cost", retries=20)
    await user.should_not_see(marker="editor-name", retries=20)


async def test_a_link_can_open_a_part(user: User) -> None:
    session, card = await open_card(user)
    await user.open(f"/set?card={card.id}&part=type")
    await user.should_see(marker="editor-type", retries=100)


async def test_the_editor_shows_the_cached_picture_until_the_render(user: User) -> None:
    import time

    await create_set(user)
    session = state().session
    card = session.new_card("Grizzly Bears")
    session.thumbnails.request([card])
    assert session.thumbnails.wait_idle()
    cached = session.thumbnails.get(card)
    render = session.render
    session.render = lambda c, face=0: (time.sleep(2.0), render(c, face))[1]
    await user.open(f"/set?card={card.id}")
    await user.should_see("On this card")
    sources = [image.source for image in user.find(kind=ui.image).elements]
    assert any(cached.name in str(source) for source in sources)       # the overview's picture
