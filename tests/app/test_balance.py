"""Balance: card scores against their cost, norms, archetype strength and its checks."""
from setdesigner.app.balance import archetype_strength, norms, score
from setdesigner.app.health.checks import off_curve, weak_archetype
from setdesigner.app.session import SetSession
from setdesigner.model import Card, Face, Rarity, load_project


def card(cost, type_line, text="", p=None, t=None, rarity=Rarity.COMMON, name="Test"):
    return Card(id=name.lower(), rarity=rarity, faces=[Face(name=name, mana_cost=cost, type_line=type_line,
                                                            rules_text=text, power=p, toughness=t)])


def made(s, name, cost, type_line, text="", p=None, t=None, rarity="common", archetypes=()):
    c = s.new_card(name)
    for field, value in [("mana_cost", cost), ("type_line", type_line), ("rules_text", text), ("power", p),
                         ("toughness", t), ("rarity", rarity), ("archetypes", list(archetypes))]:
        if value is not None:
            s.update(c, field, value)
    return c


def test_vanilla_bodies_are_on_curve():
    for cost, p in [("{1}{W}", "2"), ("{2}{G}", "3"), ("{3}{G}", "4")]:
        s = score(card(cost, "Creature — Bear", p=p, t=p))
        assert s.delta == 0 and s.verdict == "on" and s.unscored == []


def test_flying_adds_worth_scaled_by_power():
    two = score(card("{2}{U}", "Creature — Bird", "Flying", "2", "2"))
    one = score(card("{2}{U}", "Creature — Bird", "Flying", "1", "1"))
    assert ("Flying", 0.75) in two.parts and ("Flying", 0.5) in one.parts


def test_removal_and_card_draw_are_found():
    bolt = score(card("{R}", "Instant", "Test deals 3 damage to any target."))
    assert bolt.verdict == "above" and ("3 damage", 2.0) in bolt.parts
    murder = score(card("{1}{B}{B}", "Instant", "Destroy target creature."))
    assert ("Destroy a creature", 3.0) in murder.parts and murder.verdict == "on"
    elf = score(card("{3}{G}", "Creature — Elf", "When Test enters, draw a card.", "3", "3"))
    assert ("Draw 1", 1.0) in elf.parts and elf.delta == 0


def test_activated_and_unknown_lines():
    s = score(card("{2}{U}", "Creature — Wizard", "{2}, {T}: Surveil 2.\nYou may look at the top card of your library any time.", "1", "3"))
    assert any(label.startswith("Surveil 2 (×0.6)") for label, _ in s.parts)
    assert s.unscored == ["You may look at the top card of your library any time."]


def test_rarity_tolerances():
    big = card("{1}{G}", "Creature — Beast", "", "4", "4", rarity=Rarity.COMMON)
    assert score(big).verdict == "above"
    weak = card("{4}{W}", "Creature — Soldier", "", "1", "1", rarity=Rarity.RARE)
    assert score(weak).verdict == "on"                         # rares aren't flagged for being weak
    assert score(card("{4}{W}", "Creature — Soldier", "", "1", "1")).verdict == "below"
    assert score(card("", "Land")) is None


def test_overrides_and_adjustments(tmp_path):
    s = SetSession.create(tmp_path / "s", "Test", "TST")
    bird = made(s, "Gull", "{2}{U}", "Creature — Bird", "Flying", "2", "2")
    s.set_balance_norm("keyword.flying", 2.0)
    assert ("Flying", 1.5) in score(bird, s.project).parts
    assert load_project(s.folder).info.balance == {"keyword.flying": 2.0}
    s.set_balance_norm("keyword.flying", None)
    assert norms(s.project)["keyword.flying"] == 1.0
    s.update(bird, "balance_adjust", -0.5)
    s.update(bird, "balance_note", "can't block")
    assert ("Adjustment: can't block", -0.5) in score(bird, s.project).parts


def test_custom_mechanic_value(tmp_path):
    s = SetSession.create(tmp_path / "s", "Test", "TST")
    flurry = s.new_mechanic("Flurry")
    s.update_mechanic(flurry, value=1.25)
    c = made(s, "Gale Monk", "{1}{U}", "Creature — Monk", "Flurry", "1", "2")
    assert ("Flurry", 1.25) in score(c, s.project).parts


def test_archetype_strength_and_checks(tmp_path):
    s = SetSession.create(tmp_path / "s", "Test", "TST")
    fliers = s.new_archetype("Fliers", "WU")
    graveyard = s.new_archetype("Graveyard", "UB")
    made(s, "Gull", "{1}{U}", "Creature — Bird", "Flying", "2", "1", archetypes=[fliers.id])
    made(s, "Lancer", "{2}{W}", "Instant", "Destroy target creature.", archetypes=[fliers.id])
    made(s, "Seer", "{2}{U}", "Sorcery", "Draw two cards.", archetypes=[fliers.id])
    made(s, "Ghoul", "{4}{B}", "Creature — Zombie", "", "1", "1", archetypes=[graveyard.id])
    ranked = archetype_strength(s.project)
    assert [a.archetype.name for a in ranked] == ["Fliers", "Graveyard"]
    assert ranked[0].missing == [] and set(ranked[1].missing) == {"removal", "two_drop", "card_draw"}
    s.update_archetype(graveyard, key_roles=["removal"])
    assert archetype_strength(s.project)[1].missing == ["removal"]
    messages = [w.message for w in weak_archetype(s.project, 60)]
    assert messages and messages[0].startswith("Graveyard")
    assert any("below curve" in w.message for w in off_curve(s.project, None))
