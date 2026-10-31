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
    state().settings.tiles = "text"               # no rendering needed in these tests
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


def choose(user: User, option: str, value: str) -> None:
    """Pick a toggle button (the toggle containing `option`)."""
    element = next(iter(user.find(kind=ui.toggle, content=option).elements))
    element.value = value


async def test_stacks_in_rows_and_matrix(user: User) -> None:
    _, bear, _ = await open_set_with_cards(user)
    choose(user, "Stacks", "stacks")
    await user.should_see(marker="stack")
    await user.should_see("White · 1")                 # group headings above the stacks
    choose(user, "Matrix", "matrix")
    await user.should_see("Columns")
    await user.should_see(marker="stack")
    choose(user, "Matrix", "rows")
    await user.should_see("Group by")
    user.find(marker=f"tile-{bear.id}").click()        # stacked cards still open the editor
    await user.should_see("Rules text")


async def test_set_settings_panel_saves(user: User) -> None:
    session, _, _ = await open_set_with_cards(user)
    user.find(content="Set", kind=ui.button).click()
    await user.should_see("Set settings")
    await user.should_see("Set symbol")
    code = user.find("Code")
    code.clear().type("NEW").trigger("blur")
    assert session.project.info.code == "NEW"
    slot = next(iter(user.find(kind=ui.number, content="Common").elements))
    slot.value = 12
    user.find(kind=ui.number, content="Common").trigger("blur")
    assert session.project.info.rarity_slots[Rarity.COMMON] == 12


async def test_mechanics_page_create_rename_and_editor_reminders(user: User) -> None:
    session, bear, _ = await open_set_with_cards(user)
    session.update(bear, "rules_text", "Want target creature.")
    user.find(content="Mechanics", kind=ui.button).click()
    await user.should_see("No mechanics yet.")
    user.find("New mechanic").click()
    await user.should_see("Reminder text")
    mechanic = session.project.mechanics[0]
    user.find("Name").clear().type("Want").trigger("blur")
    await user.should_see("Used on 1 card")
    assert mechanic.name == "Want" and bear.mechanics == [mechanic.id]

    user.find("Name").clear().type("Hunt").trigger("blur")
    await user.should_see("Update 1 card")                    # the rename dialog
    user.find("Update 1 card").click()
    await user.should_see("Updated 1 card face")
    assert bear.faces[0].rules_text == "Hunt target creature."
    await user.open("/set/mechanics")                          # opening with a mechanic there
    await user.should_see("Used on 1 card")

    await user.open(f"/set/card/{bear.id}")
    await user.should_see("Hunt: reminder as policy (on commons only)")
    select = next(iter(user.find(content="Hunt: reminder as policy").elements))
    select.value = "hide"
    assert bear.reminders == {mechanic.id: False}


async def test_ability_word_variants_and_phrase_update(user: User) -> None:
    from setdesigner.model import AbilityTemplate
    session, bear, _ = await open_set_with_cards(user)
    session.update(bear, "rules_text", "Settled - When this creature dies, if you control four or more "
                                       "lands that share a land type, draw a card.")
    settled = session.new_mechanic("Settled")
    session.update_mechanic(settled, kind="ability_word",
                            phrases={"condition": "you control four or more lands that share a land type"},
                            templates=[AbilityTemplate(label="Trigger", text="{trigger}, if {=condition}, {effect}")])
    await user.open("/set/mechanics")
    await user.should_see("Shared phrases")
    await user.should_see("trigger: When this creature dies · effect: draw a card.")
    wording = user.find("Wording")
    wording.clear().type("you control lands of four types").trigger("blur")
    await user.should_see("Update 1 card")
    user.find("Update 1 card").click()
    await user.should_see("Updated 1 card face")
    assert bear.faces[0].rules_text == ("Settled — When this creature dies, if you control lands of four types, "
                                        "draw a card.")


async def saved(check, tries: int = 40) -> None:
    """Wait for a background save (e.g. after a field's blur) to land."""
    import asyncio
    for _ in range(tries):
        if check():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("not saved")


async def test_cycles_page_generate_recreate_and_update(user: User) -> None:
    session, _, _ = await open_set_with_cards(user)
    user.find(content="Cycles", kind=ui.button).click()
    await user.should_see("No cycles yet.")
    user.find("New cycle").click()
    await user.should_see("Shared template")
    cycle = session.project.cycles[0]
    user.find(kind=ui.input, content="Name").clear().type("{Color} Dragonstorm").trigger("blur")
    await user.should_see("Create 5 cards")
    await saved(lambda: cycle.template.name)                   # the blur handler runs in the background
    user.find("Create 5 cards").click()
    await user.should_see("Created 5 cards")
    names = [session.card(m.card_id).faces[0].name for m in cycle.members]
    assert names == ["White Dragonstorm", "Blue Dragonstorm", "Black Dragonstorm", "Red Dragonstorm",
                     "Green Dragonstorm"]

    session.delete(session.card(cycle.members[2].card_id))
    await user.open("/set/cycles")
    await user.should_see("Members · 4 of 5 made")
    user.find("Create 1 card").click()
    await user.should_see("Created 1 card")
    assert session.card(cycle.members[2].card_id).faces[0].name == "Black Dragonstorm"

    user.find(kind=ui.input, content="Type line").type("Enchantment").trigger("blur")
    await user.should_see("Update 5 cards")
    user.find("Update 5 cards").click()
    await user.should_see("Updated 5 cards")
    assert all(session.card(m.card_id).faces[0].type_line == "Enchantment" for m in cycle.members)
