"""Set-health statistics on a small set."""
import pytest

from setdesigner.app.health import stats
from setdesigner.model import Archetype, Card, Face, Mechanic, Rarity, SetInfo, SetProject


def make(name, cost, types, text="", rarity=Rarity.COMMON, power=None, toughness=None, **extra) -> Card:
    return Card(id=name.lower().replace(" ", "-"), rarity=rarity,
                faces=[Face(name=name, mana_cost=cost, type_line=types, rules_text=text,
                            power=power, toughness=toughness)], **extra)


@pytest.fixture
def project() -> SetProject:
    cards = [
        make("Bear", "{1}{G}", "Creature — Bear", power="2", toughness="2"),
        make("Elf", "{G}", "Creature — Elf", "{T}: Add {G}.", power="1", toughness="1"),
        make("Growth", "{G}", "Instant", "Target creature gets +3/+3 until end of turn."),
        make("Shock", "{R}", "Instant", "Shock deals 2 damage to any target.", archetypes=["rg"]),
        make("Ogre", "{1}{R}", "Creature — Ogre", "Hunt", power="3", toughness="1", archetypes=["rg"]),
        make("Duo", "{R}{G}", "Creature — Beast", "Trample", rarity=Rarity.UNCOMMON, power="4", toughness="4",
             archetypes=["rg"]),
        make("Grove", "", "Land", "{T}: Add {R} or {G}."),
    ]
    return SetProject(info=SetInfo(name="T", code="T"), cards=cards,
                      archetypes=[Archetype(id="rg", name="RG Beasts", colors="RG",
                                            targets={Rarity.COMMON: 3, Rarity.UNCOMMON: 1})],
                      mechanics=[Mechanic(id="hunt", name="Hunt")])


def test_curve_and_counts(project) -> None:
    curve = stats.curve(project)
    assert curve["G"]["1"] == [1, 1] and curve["G"]["2"] == [1, 0]
    assert curve["M"]["2"] == [1, 0] and "L" not in curve
    assert stats.curve(project, "uncommon")["G"]["2"] == [0, 0]
    counts = stats.color_rarity_counts(project)
    assert counts["G"]["common"] == 3 and counts["L"]["common"] == 1 and counts["M"]["uncommon"] == 1


def test_creatures(project) -> None:
    assert stats.creature_ratio(project, "common")["G"] == (2, 3)
    size = stats.creature_size(project)
    assert size["2"] == (2.5, 1.5, 2) and size["1"] == (1.0, 1.0, 1)


def test_role_table(project) -> None:
    table = stats.role_table(project, "common")
    assert [c.faces[0].name for c in table["R"]["removal"]] == ["Shock"]
    assert [c.faces[0].name for c in table["G"]["ramp"]] == ["Elf"]
    assert [c.faces[0].name for c in table["G"]["combat_trick"]] == ["Growth"]
    assert [c.faces[0].name for c in table["L"]["fixing"]] == ["Grove"]
    assert table["M"]["evasion"] == []                               # Duo is uncommon


def test_mechanics_and_archetypes(project) -> None:
    project.cards[4].mechanics = ["hunt"]
    spread = stats.mechanic_spread(project)[0]
    assert spread.cards == 1 and spread.commons == 1 and spread.by_color.get("R") == 1
    coverage = stats.archetype_coverage(project)[0]
    assert coverage.counts["common"] == 2 and coverage.counts["uncommon"] == 1
    assert coverage.targets == {"common": 3, "uncommon": 1}


def test_complexity(project) -> None:
    cx = stats.complexity(make("X", "{1}", "Creature", "Flying, vigilance\nWhen X enters, draw a card. "
                                                       "(Reminder text here.)"))
    assert cx.abilities == 2 and cx.keywords == 2
    assert cx.words == 2 + 6                             # "When this enters, draw a card."
    by_rarity = stats.complexity_by_rarity(project)
    assert by_rarity["uncommon"] == (1.0, 1.0, 1) and by_rarity["common"][2] == 6
