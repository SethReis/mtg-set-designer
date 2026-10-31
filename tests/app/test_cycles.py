"""Cycles: groupings, color tokens, generating members, keeping them in step."""
import json

import pytest

from setdesigner.app.cycles import (GROUPINGS, member_fields, members_for, render, status,
                                    template_change_plan)
from setdesigner.app.overview import FACTORS, group
from setdesigner.app.session import SetSession
from setdesigner.model import Archetype, Cycle, CycleMember, CycleTemplate, load_project


def test_groupings() -> None:
    assert [m.colors for m in members_for("mono")] == ["W", "U", "B", "R", "G"]
    assert [m.colors for m in members_for("allied_pairs")] == ["WU", "UB", "BR", "RG", "GW"]
    assert [m.colors for m in members_for("enemy_pairs")] == ["WB", "UR", "BG", "RW", "GU"]
    assert len(members_for("pairs")) == 10 and len(members_for("triads")) == 10
    assert [m.colors for m in members_for("shards")] == ["GWU", "WUB", "UBR", "BRG", "RGW"]
    assert [m.colors for m in members_for("custom", ["WU", "WUBRG"])] == ["WU", "WUBRG"]
    assert [m.colors for m in members_for("numbered", count=3)] == ["", "", ""]
    assert all(key in GROUPINGS for key in ("wedges", "four_color"))


def test_members_keep_their_card_and_overrides_when_regrouped() -> None:
    old = [CycleMember(colors="WU", card_id="a", overrides={"name": "X"}), CycleMember(colors="W")]
    new = members_for("pairs", old=old)
    assert new[0].card_id == "a" and new[0].overrides == {"name": "X"}


@pytest.mark.parametrize("colors, expected", [
    ("W", "{W} | {W}  | white | White | Plains | Plains | White | 2"),
    ("WU", "{W}{U} | {W} {U} | white and blue | White and blue | Plains or Island | Plains | Azorius | 2"),
    ("WUB", "{W}{U}{B} | {W} {U} | white, blue, and black | White, blue, and black | "
            "Plains, Island, or Swamp | Plains | Esper | 2"),
])
def test_tokens(colors, expected) -> None:
    text = "{c} | {c1} {c2} | {color} | {Color} | {basic} | {basic1} | {group} | {n}"
    assert render(text, colors, 2) == expected


def test_symbols_and_unknown_tokens_stay() -> None:
    assert render("{T}, {2}{W}: {effect}", "G") == "{T}, {2}{W}: {effect}"


def cycle(**template) -> Cycle:
    return Cycle(id="duals", name="Duals", grouping="allied_pairs", members=members_for("allied_pairs"),
                 template=CycleTemplate(**{"name": "{group} Sanctum", "type_line": "Land",
                                           "rules_text": "{T}: Add {c1} or {c2}.", "rarity": "uncommon",
                                           **template}))


def test_member_fields_and_overrides() -> None:
    c = cycle()
    assert member_fields(c, c.members[1], 2)["rules_text"] == "{T}: Add {U} or {B}."
    c.members[1].overrides["name"] = "Underground {basic2} Hideout"
    assert member_fields(c, c.members[1], 2)["name"] == "Underground Swamp Hideout"


def builtin(project):
    from setdesigner.render import CardRenderer
    return CardRenderer(project, use_mse=False)


@pytest.fixture
def session(tmp_path):
    s = SetSession.create(tmp_path / "set", "My Set", "mys", "m15", renderer_factory=builtin,
                          thumbnail_dir=tmp_path / "thumbs")
    yield s
    s.close()


def test_generate_link_and_regenerate_missing(session) -> None:
    session.new_card("Already Here")                              # takes collector number 1
    session.project.archetypes.append(Archetype(id="wu-fliers", name="WU Fliers", colors="WU"))
    c = session.new_cycle("Duals", "allied_pairs")
    session.update_cycle(c, template={**cycle().template.model_dump(), "tag_archetypes": True})
    made = session.generate_cycle(c)
    assert [card.faces[0].name for card in made] == ["Azorius Sanctum", "Dimir Sanctum", "Rakdos Sanctum",
                                                     "Gruul Sanctum", "Selesnya Sanctum"]
    assert [card.collector_number for card in made] == ["2", "3", "4", "5", "6"]
    assert all(card.cycle == c.id for card in made) and made[0].rarity.value == "uncommon"
    assert made[0].archetypes == ["wu-fliers"] and made[1].archetypes == []
    assert [m.card_id for m in c.members] == [card.id for card in made]

    session.delete(made[2])                                      # its member is now missing
    assert c.members[2].card_id is None
    assert [st.card is None for st in status(c, session.project)] == [False, False, True, False, False]
    again = session.generate_cycle(c)
    assert [card.faces[0].name for card in again] == ["Rakdos Sanctum"]

    saved = json.loads((session.folder / "cycles.json").read_text(encoding="utf-8"))
    assert saved[0]["members"][0]["card_id"] == made[0].id
    reloaded = load_project(session.folder)
    assert reloaded.cycles[0].template.name == "{group} Sanctum"
    assert reloaded.card(made[0].id).cycle == c.id


def test_template_change_keeps_edited_fields(session) -> None:
    c = session.new_cycle("Duals", "allied_pairs")
    session.update_cycle(c, template=cycle().template)
    cards = session.generate_cycle(c)
    session.update(cards[0], "name", "Hand-made Name")
    new = cycle(name="{group} Haven", rules_text="{T}: Add {c1} or {c2}. It enters tapped.").template
    plan = template_change_plan(c, session.project, new)
    assert plan.kept == {cards[0].id: ["name"]}
    assert set(plan.changes[0].fields) == {"rules_text"}           # the edited name isn't offered
    assert set(plan.changes[1].fields) == {"name", "rules_text"}
    done = session.update_cycle(c, update_cards=True, template=new)
    assert len(done) == 5
    assert cards[0].faces[0].name == "Hand-made Name" and cards[1].faces[0].name == "Dimir Haven"
    assert cards[0].faces[0].rules_text.endswith("It enters tapped.")
    assert status(c, session.project)[0].edited == ["name"]


def test_delete_cycle_and_regroup_unlink_cards(session) -> None:
    c = session.new_cycle("Mono", "mono")
    cards = session.generate_cycle(c)
    session.set_cycle_grouping(c, "custom", ["W", "U"])            # B, R, G dropped
    assert [m.colors for m in c.members] == ["W", "U"]
    assert [card.cycle for card in cards] == [c.id, c.id, None, None, None]
    session.delete_cycle(c)
    assert all(card.cycle is None for card in cards) and session.project.cycles == []
    assert len(session.project.cards) == 5                          # cards stay


def test_cycle_factor(session) -> None:
    c = session.new_cycle("Mono", "mono")
    session.generate_cycle(c)
    session.new_card("Loner")
    groups = {g.key: len(g.cards) for g in group(session.project.cards, FACTORS["cycle"], session.project)}
    assert groups == {c.id: 5, "-": 1}
