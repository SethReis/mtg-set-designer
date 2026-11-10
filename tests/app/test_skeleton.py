"""The set skeleton without UI: presets, columns, generating, adjusting and filling."""
import pytest

from setdesigner.app import skeleton as sk
from setdesigner.model import Archetype, Card, Face, Rarity, SetInfo, SetProject, Skeleton
from setdesigner.model.skeleton import ANY


def card(card_id, cost="", rarity=Rarity.COMMON, types="Creature", **kw) -> Card:
    return Card(id=card_id, rarity=rarity, collector_number=str(abs(hash(card_id)) % 100),
                faces=[Face(name=card_id.title(), mana_cost=cost, type_line=types)], **kw)


def project(*cards, archetypes=()) -> SetProject:
    return SetProject(info=SetInfo(name="Test", code="TST"), cards=list(cards), archetypes=list(archetypes))


ARCHETYPES = [Archetype(id="flyers", name="WU flyers", colors="UW"),       # any order
              Archetype(id="graveyard", name="BG graveyard", colors="GB"),
              Archetype(id="mono-red", name="Red aggro", colors="R"),        # mono: no column of its own
              Archetype(id="esper", name="Esper control", colors="WUB")]


def test_columns_follow_the_archetypes_color_sets() -> None:
    columns = sk.default_columns(project(archetypes=ARCHETYPES))
    assert columns == ["W", "U", "B", "R", "G", "WU", "BG", "WUB", "C", "L"]
    assert sk.canonical("wg") == "GW" and sk.canonical("BUW") == "WUB"


@pytest.mark.parametrize("preset", ["play_booster", "classic"])
def test_default_counts_add_up_to_the_preset(preset) -> None:
    columns = sk.default_columns(project(archetypes=ARCHETYPES))
    counts = sk.default_counts(preset, columns)
    assert sk.totals(counts) == sk.PRESETS[preset].totals
    assert counts["WU"]["uncommon"] == 2 and counts["WU"]["rare"] == 1     # signposts
    assert counts["W"]["common"] >= counts["WU"]["common"]


def test_a_cube_has_counts_per_column_only() -> None:
    counts = sk.default_counts("cube", ["W", "U", "B", "R", "G", "WU", "C", "L"])
    assert counts["W"] == {ANY: 45} and counts["WU"] == {ANY: 4}
    slots = sk.generate(["W"], {"W": {ANY: 3}}, [])
    assert [s.id for s in slots] == ["W-01", "W-02", "W-03"] and slots[0].rarity is None


def test_generated_labels_are_unique_and_archetype_columns_are_tagged() -> None:
    columns = sk.default_columns(project(archetypes=ARCHETYPES))
    slots = sk.generate(columns, sk.default_counts("play_booster", columns), ARCHETYPES)
    assert len({s.id for s in slots}) == len(slots) == 261
    assert slots[0].id == "W-C01"
    assert {tuple(s.archetypes) for s in slots if s.column == "WU"} == {("flyers",)}
    assert {tuple(s.archetypes) for s in slots if s.column == "W"} == {()}


def skeleton_with(counts, columns=None) -> Skeleton:
    columns = columns or list(counts)
    return Skeleton(columns=columns, counts=counts, slots=sk.generate(columns, counts, []))


def test_adjust_keeps_annotations_and_cards() -> None:
    s = skeleton_with({"W": {"common": 4}})
    first, second, third, fourth = sk.cell(s, "W", "common")
    second.note = "2-drop flyer"
    fourth.card_id = "bear"
    assert sk.adjust(s, ["W"], {"W": {"common": 2}}, []) == []
    assert sk.cell(s, "W", "common") == [second, fourth]               # plain empty slots went first
    blocked = sk.adjust(s, ["W"], {"W": {"common": 0}}, [])
    assert blocked == [fourth] and sk.cell(s, "W", "common") == [fourth]   # filled: asked about, kept
    sk.adjust(s, ["W"], {"W": {"common": 3}}, [])
    ids = [x.id for x in sk.cell(s, "W", "common")]
    assert ids[0] == "W-C04" and len(ids) == 3 and len(set(ids)) == 3  # new labels don't clash


def test_adjust_removes_filled_slots_only_when_told() -> None:
    s = skeleton_with({"W": {"common": 1}})
    s.slots[0].card_id = "bear"
    assert sk.adjust(s, ["W"], {"W": {"common": 0}}, [], remove_filled=True) == []
    assert s.slots == []


@pytest.mark.parametrize("cost, types, column", [
    ("{1}{W}", "Creature", "W"),
    ("{2}", "Artifact", "C"),
    ("", "Land", "L"),
    ("{W}{U}", "Creature", "WU"),
    ("{B}{G}", "Instant", "BG"),
    ("{R}{W}", "Creature", "WU"),            # no RW column: the closest (shares W)
    ("{W}{U}{B}", "Sorcery", "WUB"),
])
def test_column_of(cost, types, column) -> None:
    columns = ["W", "U", "B", "R", "G", "WU", "BG", "WUB", "C", "L"]
    assert sk.column_of(card("x", cost, types=types), columns) == column


def test_two_faced_cards_go_by_their_front() -> None:
    from setdesigner.model import FaceRole, Layout
    dfc = Card(id="dfc", layout=Layout.TRANSFORM, faces=[
        Face(name="Front", mana_cost="{G}", type_line="Creature"),
        Face(name="Back", role=FaceRole.BACK, color_indicator="B", type_line="Creature")])
    assert sk.column_of(dfc, ["W", "U", "B", "R", "G", "C", "L"]) == "G"


def test_place_cards_prefers_better_fits_and_returns_the_rest() -> None:
    s = skeleton_with({"W": {"common": 2}, "U": {"uncommon": 1}})
    flyer_slot, plain = sk.cell(s, "W", "common")
    flyer_slot.mana_value, flyer_slot.types = 3, "Creature"
    two, three, other = (card("two", "{1}{W}"), card("three", "{2}{W}"),
                         card("blue-rare", "{U}", rarity=Rarity.RARE))
    loose = sk.place_cards(s, project(two, three, other))
    assert flyer_slot.card_id == "three" and plain.card_id == "two"
    assert loose == [other]                                            # no blue rare slot


def test_suggest_ranks_fitting_cards_outside_the_skeleton() -> None:
    s = skeleton_with({"W": {"common": 2}})
    target, taken = sk.cell(s, "W", "common")
    target.mana_value = 1
    one, two, red = card("one", "{W}"), card("two", "{1}{W}"), card("red", "{R}")
    taken.card_id = "two"
    assert sk.suggest(s, target, project(one, two, red)) == [one]


def test_targets_count_slots_by_rarity() -> None:
    s = skeleton_with({"W": {"common": 3, "rare": 1}, "U": {"common": 2}})
    assert sk.targets(s) == {Rarity.COMMON: 5, Rarity.RARE: 1}
