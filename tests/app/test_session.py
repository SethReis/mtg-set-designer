"""SetSession: the editor's behaviour without UI (uses the built-in renderer, so no MSE)."""
import json
from pathlib import Path

import pytest

from setdesigner.app.session import AUTOSAVE_DELAY, SessionError, SetSession
from setdesigner.model import Mechanic, Rarity

PACKAGES = Path(__file__).resolve().parents[2] / "resources" / "mse_packages"
# drawing cards needs the MSE templates (tools/sync_packages.py fills resources/)
needs_packages = pytest.mark.skipif(not PACKAGES.is_dir(), reason="resources/mse_packages not populated")


def builtin(project):
    from setdesigner.render import CardRenderer
    return CardRenderer(project, use_mse=False)


@pytest.fixture
def session(tmp_path):
    s = SetSession.create(tmp_path / "myset", "My Set", "mys", "m15", renderer_factory=builtin)
    yield s
    s.close()


def card_file(session, card):
    return session.folder / "cards" / f"{card.id}.json"


def test_create_and_open(tmp_path, session) -> None:
    assert session.project.info.code == "MYS"
    assert (session.folder / "set.json").is_file()
    with pytest.raises(SessionError):
        SetSession.create(session.folder, "Again", "AGN")          # already a set there
    with pytest.raises(SessionError):
        SetSession.open(tmp_path / "nothing")
    reopened = SetSession.open(session.folder)
    assert reopened.project.info.name == "My Set"


def test_new_cards_get_files_ids_and_numbers(session) -> None:
    a, b = session.new_card(), session.new_card()
    assert (a.id, b.id) == ("new-card", "new-card-2")
    assert (a.collector_number, b.collector_number) == ("1", "2")
    assert card_file(session, a).is_file() and card_file(session, b).is_file()


def test_autosave_waits_for_a_pause_then_writes(session) -> None:
    card = session.new_card()
    session.update(card, "name", "Grizzly Bears")
    assert session.unsaved
    assert session.flush_due() == []                          # too soon
    import time
    assert session.flush_due(time.monotonic() + AUTOSAVE_DELAY) == [card.id]
    data = json.loads(card_file(session, card).read_text(encoding="utf-8"))
    assert data["faces"][0]["name"] == "Grizzly Bears"
    assert card.id == "new-card"                               # ids never change on rename


def test_fields_are_converted(session) -> None:
    card = session.new_card()
    session.update(card, "rarity", "mythic")
    session.update(card, "power", " ")
    session.update(card, "frame", "")
    session.update(card, "status", "draft")
    session.flush()
    assert card.rarity.value == "mythic" and card.faces[0].power is None
    assert card.frame is None and card.status.value == "draft"
    with pytest.raises(SessionError):
        session.update(card, "nonsense", 1)


def test_types_and_subtypes_edit_the_type_line(session) -> None:
    card = session.new_card()
    session.update(card, "types", "Creature")
    assert card.faces[0].type_line == "Creature"               # no dash yet
    session.update(card, "subtypes", "Elf Druid")
    assert card.faces[0].type_line == "Creature — Elf Druid"
    session.update(card, "types", "Legendary Creature ")
    assert card.faces[0].type_line == "Legendary Creature — Elf Druid"
    session.update(card, "subtypes", "")
    assert card.faces[0].type_line == "Legendary Creature"


def test_duplicate_and_delete(session) -> None:
    card = session.new_card("Shock")
    session.update(card, "rules_text", "Shock deals 2 damage to any target.")
    copy = session.duplicate(card)
    assert copy.id == "shock-2" and copy.faces[0].rules_text == card.faces[0].rules_text
    assert copy.collector_number == "2"
    session.delete(card)
    assert not card_file(session, card).exists()
    assert [c.id for c in session.cards()] == ["shock-2"]


def test_search_and_order(session) -> None:
    a = session.new_card("Grizzly Bears")
    b = session.new_card("Shock")
    session.update(b, "collector_number", "0")
    session.update(a, "rules_text", "Trample")
    assert [c.id for c in session.cards()] == ["shock", "grizzly-bears"]
    assert [c.id for c in session.search("trample")] == ["grizzly-bears"]
    assert [c.id for c in session.search("SHO")] == ["shock"]


@needs_packages
def test_render_follows_edits(session) -> None:
    card = session.new_card("Grizzly Bears")
    session.update(card, "mana_cost", "{1}{G}")
    session.update(card, "type_line", "Creature — Bear")
    first = session.render(card)
    session.update(card, "rules_text", "Trample")
    second = session.render(card)
    assert first.size == (375, 523) and first.tobytes() != second.tobytes()
    assert session.renderer_note == "built-in renderer"


def test_close_saves_pending_edits(tmp_path) -> None:
    s = SetSession.create(tmp_path / "s", "S", "S", renderer_factory=builtin)
    card = s.new_card()
    s.update(card, "name", "Saved On Close")
    s.close()
    assert SetSession.open(tmp_path / "s").cards()[0].faces[0].name == "Saved On Close"


def test_archetypes_create_update_delete(session) -> None:
    ug = session.new_archetype("UG Ramp", "UG")
    again = session.new_archetype("UG Ramp")
    assert (ug.id, again.id) == ("ug-ramp", "ug-ramp-2")
    session.update_archetype(ug, description="Big stuff", targets={"common": "8", "rare": 0})
    saved = json.loads((session.folder / "archetypes.json").read_text(encoding="utf-8"))
    assert saved[0]["targets"] == {"common": 8} and saved[0]["description"] == "Big stuff"

    card = session.new_card()
    session.update(card, "archetypes", [ug.id, again.id])
    session.flush()
    session.delete_archetype(ug)
    assert card.archetypes == [again.id]
    assert json.loads(card_file(session, card).read_text(encoding="utf-8"))["archetypes"] == [again.id]
    assert [a.id for a in session.project.archetypes] == [again.id]


@needs_packages
def test_set_info_changes_restart_the_renderer(session) -> None:
    card = session.new_card()
    m15 = session.render(card)
    session.update_info(default_frame="8th", rarity_slots={"common": "20", "rare": 0})
    assert session.project.info.rarity_slots == {Rarity.COMMON: 20}
    assert session.render(card).tobytes() != m15.tobytes()        # drawn in the new frame


def test_layouts_add_and_drop_the_back_face(session) -> None:
    from setdesigner.model import FaceRole, Layout, validate_card
    card = session.new_card("Village Messenger")
    session.set_layout(card, "transform")
    assert card.layout == Layout.TRANSFORM and [f.role for f in card.faces] == [FaceRole.FRONT, FaceRole.BACK]
    session.update(card, "name", "Moonrise Intruder", face=1)
    session.update(card, "color_indicator", "R", face=1)
    session.update(card, "transform_symbol", "day")
    assert card.faces[1].name == "Moonrise Intruder" and card.faces[0].name == "Village Messenger"
    assert validate_card(card) == []

    session.set_layout(card, "mdfc")                   # faces stay, the symbol goes
    session.update(card, "mana_cost", "{1}{R}", face=1)
    assert len(card.faces) == 2 and card.transform_symbol == ""
    session.set_layout(card, "transform")              # transform backs have no cost
    assert card.faces[1].mana_cost == ""
    session.set_layout(card, "normal")
    assert len(card.faces) == 1 and card.layout == Layout.NORMAL
    session.flush()
    saved = json.loads(card_file(session, card).read_text(encoding="utf-8"))
    assert saved["layout"] == "normal" and len(saved["faces"]) == 1


def test_mechanics_on_the_back_face_count(session) -> None:
    from setdesigner.model import Mechanic
    session.project.mechanics.append(Mechanic(id="hunt", name="Hunt"))
    card = session.new_card("Front")
    session.set_layout(card, "mdfc")
    session.update(card, "rules_text", "Hunt.", face=1)
    assert card.mechanics == ["hunt"]


@needs_packages
def test_both_faces_render_after_a_layout_change(session) -> None:
    card = session.new_card("Front")
    session.render(card)                               # the renderer knows the single card
    session.set_layout(card, "mdfc")
    session.update(card, "name", "Back", face=1)
    front, back = session.render(card, 0), session.render(card, 1)
    assert front.size == back.size and front.tobytes() != back.tobytes()


def test_interactive_renderer_calls_go_before_waiting_background_work() -> None:
    import threading
    import time

    from setdesigner.app.session import PriorityLock
    lock, order = PriorityLock(), []
    lock.acquire(background=True)                       # a batch is being drawn

    def background():
        with lock.background():
            order.append("background")

    def interactive():
        with lock:
            order.append("interactive")
    waiting = threading.Thread(target=background)
    waiting.start()
    time.sleep(0.05)                                    # the next batch is queued first...
    preview = threading.Thread(target=interactive)
    preview.start()
    time.sleep(0.05)
    lock.release()                                      # ...but the preview goes first
    waiting.join(2)
    preview.join(2)
    assert order == ["interactive", "background"]


def make_skeleton(session, counts=None):
    counts = counts or {"W": {"common": 3}, "U": {"common": 2}}
    session.create_skeleton("play_booster", list(counts), counts)
    return session.project.skeleton


def test_a_skeleton_places_existing_cards_and_is_saved(session) -> None:
    from setdesigner.model import load_project
    bear = session.new_card("Bear")
    session.update(bear, "mana_cost", "{1}{W}")
    red = session.new_card("Red Thing")
    session.update(red, "mana_cost", "{R}")
    left = session.create_skeleton("play_booster", ["W", "U"], {"W": {"common": 3}, "U": {"common": 2}})
    assert [c.id for c in left] == [red.id]                       # no red column
    assert session.project.skeleton.slot_of(bear.id) is not None
    loaded = load_project(session.folder)
    assert loaded.skeleton == session.project.skeleton
    session.delete_skeleton()
    assert load_project(session.folder).skeleton is None and not (session.folder / "slots.json").exists()


def test_assign_moves_and_swaps(session) -> None:
    a, b = session.new_card("A"), session.new_card("B")
    for x in (a, b):
        session.update(x, "mana_cost", "{W}")
    skeleton = make_skeleton(session, {"W": {"common": 3}})
    s1, s2, s3 = skeleton.slots
    session.assign(s1, a)
    session.assign(s2, b)
    session.assign(s3, a)                                          # move: s1 empties
    assert (s1.card_id, s2.card_id, s3.card_id) == (None, b.id, a.id)
    session.assign(s2, a)                                          # swap
    assert (s2.card_id, s3.card_id) == (a.id, b.id)
    session.assign(s2, None)
    assert s2.card_id is None


def test_a_card_from_a_slot_starts_from_its_description(session) -> None:
    from setdesigner.model import Archetype
    session.project.archetypes.append(Archetype(id="flyers", name="WU flyers", colors="WU"))
    skeleton = make_skeleton(session, {"W": {"uncommon": 1}})
    slot = skeleton.slots[0]
    session.update_slot(slot, types="Creature", mana_value="2", archetypes=["flyers"], note="2-drop flyer")
    card = session.new_card_from_slot(slot)
    assert card.rarity == Rarity.UNCOMMON and card.faces[0].type_line == "Creature"
    assert card.archetypes == ["flyers"] and card.notes == "2-drop flyer"
    assert slot.card_id == card.id and slot.mana_value == 2


def test_deleting_a_card_empties_its_slot(session) -> None:
    card = session.new_card("Bear")
    session.update(card, "mana_cost", "{W}")
    skeleton = make_skeleton(session, {"W": {"common": 1}})
    session.delete(card)
    assert skeleton.slots[0].card_id is None


def test_add_and_delete_slots_update_the_counts(session) -> None:
    skeleton = make_skeleton(session, {"W": {"common": 1}})
    slot = session.add_slot("W", "common")
    assert slot.id == "W-C02" and skeleton.counts["W"]["common"] == 2
    session.add_slot("RW", "uncommon")                             # a new column
    assert "RW" in skeleton.columns
    session.delete_slot(slot)
    assert skeleton.counts["W"]["common"] == 1


def test_cycle_cards_land_in_matching_slots(session) -> None:
    cycle = session.new_cycle("Guardians")
    cycle.template.mana_cost = "{1}{c}"                            # each member in its color
    skeleton = make_skeleton(session, {c: {"common": 1} for c in "WUBRG"})
    made = session.generate_cycle(cycle)
    placed = [skeleton.slot_of(card.id) for card in made]
    assert all(placed) and {s.cycle for s in placed} == {cycle.id}

def test_slot_and_card_archetypes_stay_in_sync(session) -> None:
    from setdesigner.app.skeleton import slot_archetypes
    from setdesigner.model import Archetype, Slot
    for aid in ("flyers", "spells"):
        session.project.archetypes.append(Archetype(id=aid, name=aid, colors="WU"))
    skeleton = make_skeleton(session, {"W": {"common": 1}})
    slot = skeleton.slots[0]
    session.update_slot(slot, archetypes=["flyers"])               # an empty slot: its plan
    card = session.new_card("Gull")
    session.update(card, "archetypes", ["spells"])
    session.assign(slot, card)
    assert slot_archetypes(slot, session.project) == ["spells"]    # the card's tags win
    session.update(card, "archetypes", ["spells", "flyers"])       # editor -> skeleton
    assert slot_archetypes(slot, session.project) == ["spells", "flyers"]
    session.update_slot(slot, archetypes=["flyers"])               # skeleton -> editor
    assert card.archetypes == ["flyers"]
    session.assign(slot, None)
    session.update(card, "archetypes", [])
    assert slot_archetypes(slot, session.project) == ["flyers"]    # empty again: the plan
    assert Slot.model_validate({"id": "W-C01", "column": "W", "archetype": "flyers"}).archetypes == ["flyers"]
    assert Slot.model_validate({"id": "W-C01", "column": "W", "archetype": None}).archetypes == []
