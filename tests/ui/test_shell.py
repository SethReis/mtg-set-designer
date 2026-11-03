"""The app shell around an open set (rail, top bar, filters, deep links), driven by
NiceGUI's simulated user (built-in renderer, no MSE)."""
import asyncio
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from setdesigner.app.settings import Settings

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
    state().settings.tiles = "text"               # no rendering needed in these tests
    await user.open("/set")
    return session, bear


async def test_empty_set_offers_the_first_card(user: User) -> None:
    await user.open("/")
    user.find("Set name").type("Test Set")
    user.find("Code (3-4 letters)").type("TST")
    user.find("Create set").click()
    await user.should_see("No cards yet")
    user.find("Create the first card").click()
    await user.should_see("Rules text")
    assert len(state().session.project.cards) == 1


async def test_top_bar_shows_the_set_and_searches(user: User) -> None:
    await open_set(user)
    await user.should_see("Test Set")
    await user.should_see("TST")
    user.find("Search name, type, rules").type("nothing like it")
    await user.should_see("0 of 1 cards")


async def test_rail_opens_archetypes_over_the_workspace(user: User) -> None:
    await open_set(user)
    user.find(marker="nav-archetypes").click()
    await user.should_see("Add archetype")
    await user.should_see("Group by")                  # the workspace is still there


async def test_rail_pages_and_back_to_sets(user: User) -> None:
    await open_set(user)
    user.find(marker="nav-mechanics").click()
    await user.should_see("No mechanics yet.")
    await user.open("/set")
    user.find(marker="nav-sets").click()
    await user.should_see("Recent")
    assert state().session is None


@pytest.mark.parametrize("query, expected", [("open=archetypes", "Add archetype"),
                                             ("open=settings", "Set symbol"),
                                             ("open=mechanics", "No mechanics yet."),
                                             ("open=health", "Set health")])
async def test_deep_links_reopen_a_view(user: User, query: str, expected: str) -> None:
    await open_set(user)
    await user.open(f"/set?{query}")
    await user.should_see(expected)


async def test_deep_link_to_a_card_and_to_a_cycle(user: User) -> None:
    session, bear = await open_set(user)
    await user.open(f"/set?card={bear.id}")
    await user.should_see("Rules text")
    cycle = session.new_cycle("Dragons")
    await user.open(f"/set?open=cycles&id={cycle.id}")
    await user.should_see("Dragons")


async def test_filters_show_as_removable_chips(user: User) -> None:
    await open_set(user)
    status = next(iter(user.find(kind=ui.select, content="Status").elements))
    status.value = ["final"]
    await user.should_see("Status: Final")
    await user.should_see("0 of 1 cards")
    user.find("Clear all").click()
    await user.should_not_see("Status: Final")
    await user.should_see("1 card")


async def test_rail_and_theme_are_remembered(user: User, test_dir: Path) -> None:
    await open_set(user)
    open_before = state().settings.rail_open
    user.find(marker="rail-toggle").click()
    user.find(marker="theme-light").click()
    saved = Settings.load(test_dir / "settings.json")
    assert saved.rail_open is not open_before
    assert saved.theme == "light"


async def test_editor_steps_through_the_workspace_order(user: User) -> None:
    session, bear = await open_set(user)
    wolf = session.new_card("Timber Wolf")
    await user.open(f"/set?card={bear.id}")
    await user.should_see("Rules text")

    async def showing(name: str) -> None:
        """Wait for the editor's Name field to show `name` (clicks run as tasks)."""
        for _ in range(40):
            if {e.value for e in user.find(kind=ui.input, content="Name").elements} == {name}:
                return
            await asyncio.sleep(0.05)
        raise AssertionError(f"the editor doesn't show {name}")
    await showing("Grizzly Bears")
    user.find(marker="next-card").click()
    await showing(wolf.faces[0].name)
    user.find(marker="prev-card").click()
    await showing("Grizzly Bears")


async def test_a_card_opened_from_mechanics_returns_to_them(user: User) -> None:
    session, bear = await open_set(user)
    session.update(bear, "rules_text", "Hunt target creature.")
    session.new_mechanic("Hunt")
    await user.open("/set?open=mechanics")
    await user.should_see("Used on 1 card")
    user.find(kind=ui.button, content="Grizzly Bears").click()
    await user.should_see("Rules text")
    user.find(marker="modal-close").click()
    await user.should_see("Used on 1 card")
    user.find(marker="modal-close").click()
    await user.should_not_see("Used on 1 card", retries=20)    # gone after the leave animation
    await user.should_see("Group by")


@pytest.mark.parametrize("route, expected", [("/set/mechanics", "No mechanics yet."),
                                             ("/set/health", "Set health"),
                                             ("/set/cycles", "No cycles yet.")])
async def test_old_routes_open_their_view(user: User, route: str, expected: str) -> None:
    await open_set(user)
    await user.open(route)
    await user.should_see(expected)
    await user.should_see("Group by")                  # over the workspace


def block_mse(session) -> None:
    """As if Windows had blocked Magic Set Editor (these tests draw without it)."""
    from setdesigner.ui import renderer_notice
    session.mse_status = lambda: ("blocked", "Windows blocked Magic Set Editor")    # what checks see
    renderer_notice.health(session).update(kind="blocked", message="Windows blocked Magic Set Editor")


async def test_a_blocked_renderer_is_explained_with_one_action(user: User) -> None:
    session, _ = await open_set(user)
    block_mse(session)
    await user.should_see("Your cards are being drawn by a stand-in renderer", retries=20)
    await user.should_see(marker="renew-mse")
    user.find(marker="renderer-not-now").click()
    await user.should_not_see("Your cards are being drawn by a stand-in renderer", retries=20)
    user.find(marker="renderer-chip").click()                 # the top bar keeps a way back
    await user.should_see("Your cards are being drawn by a stand-in renderer", retries=20)


async def test_renewing_says_when_mse_works_again(user: User, monkeypatch) -> None:
    from setdesigner.app import mse_trust
    session, _ = await open_set(user)
    block_mse(session)
    monkeypatch.setattr(mse_trust, "renew", lambda s, launcher=None: "hidden-cli")
    await user.should_see(marker="renew-mse", retries=20)
    user.find(marker="renew-mse").click()
    await user.should_see("Magic Set Editor is working again", retries=20)
