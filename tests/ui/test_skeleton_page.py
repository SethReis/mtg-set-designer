"""The Skeleton view, driven by NiceGUI's simulated user (built-in renderer, no MSE)."""
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


async def open_set(user: User):
    await user.open("/")
    user.find("Set name").type("Test Set")
    user.find("Code (3-4 letters)").type("TST")
    user.find("Create set").click()
    await user.should_see("No cards yet")
    session = state().session
    bear = session.new_card("Grizzly Bears")
    session.update(bear, "mana_cost", "{1}{G}")
    state().settings.tiles = "text"
    await user.open("/set")
    return session, bear


def small_skeleton(session):
    counts = {"W": {"common": 2}, "G": {"common": 2, "rare": 1}}
    session.create_skeleton("play_booster", list(counts), counts)
    return session.project.skeleton


async def test_the_rail_opens_the_skeleton_and_generates_one(user: User) -> None:
    session, bear = await open_set(user)
    user.find(marker="nav-skeleton").click()
    await user.should_see("Plan the set's slots", retries=20)
    user.find("Generate skeleton…").click()
    await user.should_see("Generate a skeleton", retries=20)
    user.find(marker="skeleton-apply").click()
    await user.should_see(marker="skeleton-summary", retries=40)
    skeleton = session.project.skeleton
    assert len(skeleton.slots) == 261                       # the Play Booster preset
    assert skeleton.slot_of(bear.id) is not None             # the existing card was placed
    await user.should_see(marker="slot-W-C01")


async def test_an_empty_slot_creates_a_card(user: User) -> None:
    session, bear = await open_set(user)
    skeleton = small_skeleton(session)
    await user.open("/set?open=skeleton")
    await user.should_see(marker="slot-W-C01", retries=20)
    user.find(marker="slot-W-C01").click()
    await user.should_see(marker="slot-create", retries=20)
    user.find(marker="slot-create").click()
    await user.should_see("On this card", retries=40)        # the editor, on the new card
    slot = skeleton.slot("W-C01")
    assert slot.card_id is not None and session.card(slot.card_id).rarity.value == "common"


async def test_suggestions_fill_a_slot(user: User) -> None:
    session, bear = await open_set(user)
    skeleton = small_skeleton(session)
    session.assign(skeleton.slot_of(bear.id), None)          # the bear is outside again
    await user.open("/set?open=skeleton")
    await user.should_see(marker="loose-grizzly-bears", retries=20)
    user.find(marker="slot-G-C02").click()
    await user.should_see(marker="suggest-grizzly-bears", retries=20)
    user.find(marker="suggest-grizzly-bears").click()
    assert skeleton.slot("G-C02").card_id == bear.id


async def test_adding_a_slot_and_editing_the_table(user: User) -> None:
    session, bear = await open_set(user)
    skeleton = small_skeleton(session)
    await user.open("/set?open=skeleton")
    await user.should_see(marker="add-W-common", retries=20)
    user.find(marker="add-W-common").click()
    await user.should_see(marker="slot-W-C03", retries=20)
    user.find(marker="skeleton-mode").elements.pop().value = "table"
    await user.should_see(marker="table-note-W-C01", retries=20)
    user.find(marker="table-note-W-C01").type("2-drop flyer")
    assert skeleton.slot("W-C01").note == "2-drop flyer"


async def test_editing_counts_adjusts_in_place(user: User) -> None:
    session, bear = await open_set(user)
    skeleton = small_skeleton(session)
    skeleton.slot("W-C01").note = "keep me"
    await user.open("/set?open=skeleton")
    await user.should_see(marker="skeleton-counts", retries=20)
    user.find(marker="skeleton-counts").click()
    await user.should_see("Edit the skeleton's counts", retries=20)
    count = user.find(marker="count-W-common").elements.pop()
    count.value = 1
    user.find(marker="skeleton-apply").click()
    await user.should_not_see(marker="slot-W-C02", retries=40)       # the plain slot went
    assert [s.id for s in skeleton.slots if s.column == "W"] == ["W-C01"]     # the noted one stayed
