"""The design notebook: ideas, lanes, promoting to cards, slots and mechanics."""
import json

from setdesigner.app.session import SetSession
from setdesigner.model import Rarity, Status, load_project


def session(tmp_path):
    return SetSession.create(tmp_path / "s", "Test", "TST")


def test_ideas_round_trip_and_old_sets(tmp_path):
    s = session(tmp_path)
    assert load_project(s.folder).notebook == []                 # no notebook.json yet
    idea = s.new_idea("problem", "Blue needs an answer to fliers", author="Sam", tags=["blue", " "])
    s.update_idea(idea, colors="ub", sketch={"name": "Gale Snare", "type_line": "Instant"})
    loaded = load_project(s.folder).notebook
    assert [(i.title, i.kind, i.tags, i.colors, i.sketch.name, i.author) for i in loaded] == \
        [("Blue needs an answer to fliers", "problem", ["blue"], "UB", "Gale Snare", "Sam")]
    assert json.loads((s.folder / "notebook.json").read_text(encoding="utf-8"))[0]["lane"] == "inbox"


def test_move_between_lanes_keeps_order(tmp_path):
    s = session(tmp_path)
    a, b, c = s.new_idea(title="a"), s.new_idea(title="b"), s.new_idea(title="c")
    s.move_idea(a, "promising")
    s.move_idea(c, "promising", 0)
    assert [i.title for i in s.project.notebook if i.lane == "promising"] == ["c", "a"]
    assert [i.title for i in s.project.notebook if i.lane == "inbox"] == ["b"]
    s.delete_idea(b)
    assert [i.title for i in load_project(s.folder).notebook] == ["c", "a"]


def test_promote_to_card(tmp_path):
    s = session(tmp_path)
    idea = s.new_idea("card", "A flier that surveils", body="Common, blue",
                      sketch={"name": "Mistwing Scout", "mana_cost": "{1}{U}", "type_line": "Creature — Bird",
                              "rules_text": "Flying", "power": "1", "toughness": "2"})
    card = s.promote_to_card(idea)
    face = card.faces[0]
    assert (face.name, face.mana_cost, face.type_line, face.rules_text, face.power) == \
        ("Mistwing Scout", "{1}{U}", "Creature — Bird", "Flying", "1")
    assert card.status == Status.IDEA and "Common, blue" in card.notes
    assert idea.lane == "used" and [(l.kind, l.id) for l in idea.links] == [("card", card.id)]
    s.delete(card)
    assert idea.links == []


def test_promote_to_slot_and_mechanic(tmp_path):
    s = session(tmp_path)
    s.create_skeleton("play_booster", ["W", "U"], {"W": {"common": 2}, "U": {"common": 2, "uncommon": 1}})
    idea = s.new_idea("card", "Blue removal", colors="U", sketch={"type_line": "Instant"})
    slots = s.slots_for_idea(idea)
    assert slots and slots[0].column == "U"
    card = s.promote_to_card(idea, slots[0])
    assert s.project.skeleton.slot_of(card.id) is slots[0]
    assert card.rarity == slots[0].rarity or slots[0].rarity is None
    assert {l.kind for l in idea.links} == {"card", "slot"}

    mech = s.new_idea("mechanic", "Flurry", body="When you cast your second spell each turn, ...")
    mechanic = s.promote_to_mechanic(mech)
    assert mechanic.name == "Flurry" and mechanic.reminder_text.startswith("When you cast")
    s.delete_mechanic(mechanic)
    assert mech.links == []
