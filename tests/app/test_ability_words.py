"""Ability words with template variants and shared phrases (Flurry, Renew, Settled)."""
import pytest

from setdesigner.app.ability_words import (build_line, definition_change_plan, expand, insertion,
                                           parse_line, slots, template_uses)
from setdesigner.app.session import SetSession
from setdesigner.app.text_input import apply, suggestions
from setdesigner.model import (AbilityTemplate, Card, Face, Mechanic, MechanicKind, SetInfo,
                               SetProject)
from setdesigner.mse.mechanics import reminder_choices

CONDITION = "you control four or more lands that share a land type"
SHARES = "it shares a land type with four or more other lands you control"


def settled() -> Mechanic:
    return Mechanic(id="settled", name="Settled", kind=MechanicKind.ABILITY_WORD,
                    phrases={"condition": CONDITION, "shares": SHARES},
                    templates=[AbilityTemplate(label="Activated",
                                               text="{cost}: {effect}. Activate only if {=condition}."),
                               AbilityTemplate(label="Landfall",
                                               text="Whenever a land you control enters, if {=shares}, {effect}"),
                               AbilityTemplate(label="Trigger", text="{trigger}, if {=condition}, {effect}")])


FLURRY = Mechanic(id="flurry", name="Flurry", kind=MechanicKind.ABILITY_WORD,
                  templates=[AbilityTemplate(label="Trigger",
                                             text="Whenever you cast your second spell each turn, {effect}")])
RENEW = Mechanic(id="renew", name="Renew", kind=MechanicKind.ABILITY_WORD,
                 templates=[AbilityTemplate(label="Graveyard", text="{cost}, Exile this card from your "
                                                                    "graveyard: {effect}. Activate only as a sorcery.")])

# the user's three Settled cards (typed with a hyphen)
ACTIVATED = ("Settled - {3}{G}, {T}: Put 3 +1/+1 counters on this creature. Activate only if you control "
             "four or more lands that share a land type.")
LANDFALL = ("Settled - Whenever a land you control enters, if it shares a land type with four or more "
            "other lands you control, draw a card.")
TRIGGER = ("Settled - When this creature dies, if you control four or more lands that share a land type, "
           "create a 1/1 white Soldier creature token.")


def test_expand_and_slots() -> None:
    m = settled()
    assert expand(m.templates[0].text, m.phrases) == f"{{cost}}: {{effect}}. Activate only if {CONDITION}."
    assert slots(m.templates[0].text) == ["cost", "effect"]
    assert slots("{T}: {effect}. {G}") == ["effect"]             # symbols aren't slots


def test_settled_lines_match_their_variants() -> None:
    m = settled()
    a, b, c = (parse_line(m, line) for line in (ACTIVATED, LANDFALL, TRIGGER))
    assert (a.label, a.values) == ("Activated", {"cost": "{3}{G}, {T}",
                                                 "effect": "Put 3 +1/+1 counters on this creature"})
    assert (b.label, b.values) == ("Landfall", {"effect": "draw a card."})
    assert (c.label, c.values) == ("Trigger", {"trigger": "When this creature dies",
                                               "effect": "create a 1/1 white Soldier creature token."})
    assert parse_line(m, "Settled — Draw a card.") is None       # starts with it, follows nothing
    assert parse_line(m, "Draw a card.") is None


def test_flurry_and_renew_tolerances_and_round_trip() -> None:
    line = "Flurry -- whenever you cast your second spell each turn, draw a card."
    match = parse_line(FLURRY, line)                              # typed dash, lower-case first letter
    assert match.values == {"effect": "draw a card."}
    rebuilt = build_line(FLURRY, FLURRY.templates[0].text, match.values)
    assert rebuilt == "Flurry — Whenever you cast your second spell each turn, draw a card."
    assert parse_line(FLURRY, rebuilt).values == match.values
    renew = "Renew — {2}{G}, Exile this card from your graveyard: Put a +1/+1 counter on target creature. " \
            "Activate only as a sorcery."
    assert parse_line(RENEW, renew).values == {"cost": "{2}{G}", "effect": "Put a +1/+1 counter on target creature"}


def project(*lines, mechanic=None) -> SetProject:
    cards = [Card(id=f"c{i}", collector_number=str(i), faces=[Face(name=f"Card {i}", rules_text=line)])
             for i, line in enumerate(lines, 1)]
    return SetProject(info=SetInfo(name="T", code="T"), mechanics=[mechanic or settled()], cards=cards)


def test_uses_and_badges() -> None:
    p = project(ACTIVATED, "Flying\nSettled — Draw a card.", "Settled — [cost]: [effect]. Activate only if "
                + CONDITION + ".")
    uses = template_uses(p, p.mechanics[0])
    assert [(u.card.id, u.match is not None, u.unfinished) for u in uses] == [
        ("c1", True, False), ("c2", False, False), ("c3", True, True)]
    assert uses[1].line_index == 1


def test_phrase_edit_rewrites_every_variant_using_it() -> None:
    p = project(ACTIVATED, LANDFALL, TRIGGER, "Settled — something else entirely.")
    m = p.mechanics[0]
    new = "you control four or more lands that share a basic land type"
    plan = definition_change_plan(p, m, phrases={**m.phrases, "condition": new})
    assert [c.card.id for c in plan.changes] == ["c1", "c3"]      # Landfall uses {=shares}
    assert plan.changes[0].after.endswith(new + ".")
    assert plan.changes[1].after.startswith("Settled — When this creature dies, if " + new)
    assert [u.card.id for u in plan.unmatched] == ["c4"]


def test_variant_edit_keeps_drops_and_adds_slots() -> None:
    p = project(ACTIVATED, TRIGGER)
    m = p.mechanics[0]
    templates = [AbilityTemplate(label="Activated", text="{cost}: {effect}. Activate only as a sorcery and only "
                                                          "if {=condition}."),
                 AbilityTemplate(label="Landfall", text=m.templates[1].text),
                 AbilityTemplate(label="Trigger", text="{trigger}, if {=condition}, {bonus} and {effect}")]
    plan = definition_change_plan(p, m, templates=templates)
    after = {c.card.id: c.after for c in plan.changes}
    assert after["c1"] == ("Settled — {3}{G}, {T}: Put 3 +1/+1 counters on this creature. Activate only as a "
                           "sorcery and only if " + CONDITION + ".")
    assert "[bonus] and create a 1/1" in after["c2"]               # a new slot shows as a placeholder
    dropped = definition_change_plan(p, m, templates=[AbilityTemplate(label="Activated",
                                                                      text="{effect}. Activate only if "
                                                                           "{=condition}.")]
                                     + m.templates[1:])
    assert dropped.dropped == {"Activated": ["cost"]}


def test_insertion_and_suggestions_select_the_first_placeholder() -> None:
    m = settled()
    text, start, length = insertion(m, 0)
    assert text == f"Settled — [cost]: [effect]. Activate only if {CONDITION}."
    assert text[start:start + length] == "[cost]"
    options = suggestions("Sett", 4, [m])
    assert [o.label for o in options] == ["Settled — Activated", "Settled — Landfall", "Settled — Trigger"]
    new_text, caret = apply("Sett", 4, options[2])
    assert new_text[caret:caret + options[2].select] == "[trigger]"
    assert [o.label for o in suggestions("Flu", 3, [FLURRY])] == ["Flurry"]


def test_ability_words_get_no_reminder_tags() -> None:
    p = project(ACTIVATED)
    assert reminder_choices(p) == {"c1": {"Settled": False}}


@pytest.fixture
def session(tmp_path):
    from setdesigner.render import CardRenderer
    s = SetSession.create(tmp_path / "set", "My Set", "mys", "m15",
                          renderer_factory=lambda p: CardRenderer(p, use_mse=False),
                          thumbnail_dir=tmp_path / "thumbs")
    yield s
    s.close()


def test_session_definition_changes_with_and_without_cards(session) -> None:
    card = session.new_card("Grazer")
    session.update(card, "rules_text", "Trample\n" + TRIGGER)
    m = session.new_mechanic("Settled")
    template_data = [t.model_dump() for t in settled().templates]
    session.update_mechanic(m, kind="ability_word", phrases=settled().phrases, templates=template_data)
    assert card.mechanics == [m.id] and m.templates[2].label == "Trigger"

    new = "you control lands of four or more types"
    kept = session.update_mechanic(m, phrases={**m.phrases, "condition": new})
    assert kept == [] and CONDITION in card.faces[0].rules_text            # cards left alone
    session.update_mechanic(m, phrases={**m.phrases, "condition": CONDITION})
    done = session.update_mechanic(m, update_cards=True, phrases={**m.phrases, "condition": new})
    assert len(done) == 1
    assert card.faces[0].rules_text == ("Trample\nSettled — When this creature dies, if " + new
                                        + ", create a 1/1 white Soldier creature token.")


def test_old_mechanics_load_without_templates() -> None:
    old = Mechanic.model_validate({"id": "x", "name": "Want", "kind": "keyword"})
    assert old.phrases == {} and old.templates == []
