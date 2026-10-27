"""The overview's grouping, matrix, filters, sorting and targets."""
from setdesigner.app.overview import (FACTORS, Filters, apply, card_type, color_key, group,
                                      mana_value, matrix, sort, target)
from setdesigner.model import Archetype, Card, Face, Rarity, SetInfo, SetProject, Status


def card(cid, cost="", types="", rarity=Rarity.COMMON, archetypes=(), number="", status=Status.IDEA,
         name=None, indicator=""):
    return Card(id=cid, rarity=rarity, collector_number=number, status=status,
                archetypes=list(archetypes),
                faces=[Face(name=name or cid, mana_cost=cost, type_line=types, color_indicator=indicator)])


def project(*cards, archetypes=(), slots=None):
    return SetProject(info=SetInfo(name="T", code="TST", rarity_slots=slots or {}),
                      archetypes=list(archetypes), cards=list(cards))


BEAR = card("bear", "{1}{G}", "Creature — Bear", number="3")
GOLEM = card("golem", "{4}", "Artifact Creature — Golem", Rarity.UNCOMMON, number="10")
CHARM = card("charm", "{W}{U}", "Instant", Rarity.RARE, number="1")
FOREST = card("forest", "", "Basic Land — Forest", number="2")
FIREBALL = card("fireball", "{X}{R}", "Sorcery", number="")


def test_card_facts() -> None:
    assert [color_key(c) for c in (BEAR, GOLEM, CHARM, FOREST)] == ["G", "C", "M", "L"]
    assert color_key(card("back", types="Creature", indicator="blue")) == "U"
    assert card_type(GOLEM) == "Creature" and card_type(FOREST) == "Land"
    assert card_type(card("x", types="Kindred Enchantment")) == "Enchantment"
    assert card_type(card("y", types="Scheme")) == "Other"
    assert mana_value("{X}{R}") == 1
    assert mana_value("{2}{W/U}{W/P}") == 4
    assert mana_value("{2/W}{2/W}") == 4
    assert mana_value("") == 0


def test_groups_keep_empty_ones_in_order() -> None:
    p = project(BEAR, GOLEM, CHARM, FOREST)
    groups = group(p.cards, FACTORS["color"], p)
    assert [g.key for g in groups] == ["W", "U", "B", "R", "G", "M", "C", "L"]
    assert [c.id for c in groups[4].cards] == ["bear"]
    by_value = {g.key: [c.id for c in g.cards] for g in group(p.cards, FACTORS["mana_value"], p)}
    assert by_value["2"] == ["bear", "charm"] and by_value["7+"] == []
    types = [g.key for g in group(p.cards, FACTORS["type"], p)]
    assert "Other" not in types                         # hidden while empty


def test_archetype_groups() -> None:
    a, b = Archetype(id="ug", name="UG Ramp"), Archetype(id="wu", name="WU Fliers")
    both = card("both", archetypes=["ug", "wu", "deleted-one"])
    p = project(both, BEAR, archetypes=[a, b])
    groups = {g.key: [c.id for c in g.cards] for g in group(p.cards, FACTORS["archetype"], p)}
    assert groups == {"ug": ["both"], "wu": ["both"], "": ["bear"]}


def test_matrix() -> None:
    p = project(BEAR, GOLEM, CHARM, FOREST)
    m = matrix(p.cards, FACTORS["color"], FACTORS["rarity"], p)
    assert [c.id for c in m.cell("G", "common")] == ["bear"]
    assert [c.id for c in m.cell("C", "uncommon")] == ["golem"]
    assert m.cell("W", "mythic") == []
    assert [k for k, _ in m.columns] == ["common", "uncommon", "rare", "mythic", "special"]


def test_filters_and_sorting() -> None:
    cards = [BEAR, GOLEM, CHARM, FOREST, FIREBALL]
    assert [c.id for c in apply(Filters(text="bear"), cards)] == ["bear"]
    assert [c.id for c in apply(Filters(rarities={"common"}, colors={"G", "L"}), cards)] == ["bear", "forest"]
    assert apply(Filters(statuses={"final"}), cards) == []
    assert not Filters().active and Filters(text=" x").active
    assert [c.id for c in sort(cards)] == ["charm", "forest", "bear", "golem", "fireball"]
    assert [c.id for c in sort(cards, "mana_value")][:2] == ["forest", "fireball"]
    assert [c.id for c in sort(cards, "name")][0] == "bear"


def test_targets() -> None:
    ug = Archetype(id="ug", name="UG", targets={Rarity.COMMON: 8, Rarity.UNCOMMON: 3})
    p = project(archetypes=[ug, Archetype(id="none", name="No targets")],
                slots={Rarity.COMMON: 101})
    assert target(p, FACTORS["rarity"], "common") == 101
    assert target(p, FACTORS["rarity"], "rare") is None
    assert target(p, FACTORS["archetype"], "ug") == 11
    assert target(p, FACTORS["archetype"], "none") is None
    assert target(p, FACTORS["archetype"], "ug", FACTORS["rarity"], "common") == 8
    assert target(p, FACTORS["rarity"], "uncommon", FACTORS["archetype"], "ug") == 3
    assert target(p, FACTORS["color"], "G", FACTORS["rarity"], "common") is None
    assert target(p, FACTORS["color"], "G") is None
